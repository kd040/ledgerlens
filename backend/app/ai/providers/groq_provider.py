"""Groq implementation of the AI provider seam (see base.py), used as the
transient-failure fallback behind Gemini (see failover.py).

Groq serves an OpenAI-compatible Chat Completions API, so this is a plain
HTTP client built on httpx -- already a pinned dependency -- rather than a
new SDK for a single endpoint. The tool-calling loop is deliberately the
same shape as the Anthropic and Gemini providers: same system prompt, same
user message, same 11 read-only tool definitions, same submit-tool schema,
same turn/tool-call ceilings. Nothing about the investigation is
re-worded for Groq, because a fallback that asked a different question
could produce a different answer.

As with the other providers, this module executes every tool call itself
through tools.execute_tool (read-only dispatch + audit recording). Groq
never runs code, never touches the database, and never sees a credential.
"""

import json
import os
from typing import Any

import httpx

from app.ai.config import (
    GROQ_BASE_URL,
    GROQ_MAX_COMPLETION_TOKENS,
    GROQ_MODEL,
    GROQ_REASONING_EFFORT,
    GROQ_REQUEST_TIMEOUT_SECONDS,
    GROQ_TOOL_CHOICE,
    MAX_TOOL_TURNS,
    MAX_TOTAL_TOOL_CALLS,
)
from app.ai.providers.base import RETRYABLE_STATUS_CODES, AIProvider, AIProviderError
from app.ai.tools import execute_tool


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Groq sends Retry-After on a 429. Only a plain numeric seconds value
    is honoured -- the HTTP-date form is not used by this API, and an
    unparseable header must never become a wait of unknown length."""
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def _openai_tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


class GroqProvider(AIProvider):
    """`client` is an httpx.Client and exists so tests can inject a
    transport without a live key or a network call -- the same injection
    seam GeminiProvider(client=...) and AnthropicProvider(client=...)
    already provide."""

    def __init__(
        self,
        *,
        client: "httpx.Client | None" = None,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self._client = client
        self._model = model or GROQ_MODEL
        self._api_key = api_key

    @staticmethod
    def is_configured() -> bool:
        return bool(os.getenv("GROQ_API_KEY"))

    def _resolve_api_key(self) -> str:
        api_key = self._api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise AIProviderError(
                "Groq is not configured (GROQ_API_KEY is not set).", status_code=503
            )
        return api_key

    def _post(self, client: httpx.Client, payload: dict[str, Any]) -> dict[str, Any]:
        """One Chat Completions round trip, with every failure mode
        classified as transient or not (see AIProviderError.retryable).
        The Authorization header is built here and never stored on the
        instance beyond the call, and is never logged or returned."""
        try:
            response = client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._resolve_api_key()}"},
                timeout=GROQ_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException as error:
            raise AIProviderError(f"Groq request timed out: {error}", retryable=True) from error
        except httpx.HTTPError as error:  # connection/transport failures
            raise AIProviderError(f"Could not reach Groq: {error}", retryable=True) from error

        if response.status_code >= 400:
            # Body is Groq's own error JSON -- kept for the server log, not
            # for the API response (failover.py replaces it with the clean
            # user-facing message).
            raise AIProviderError(
                f"Groq returned {response.status_code}: {response.text[:500]}",
                retryable=response.status_code in RETRYABLE_STATUS_CODES,
                provider_status=response.status_code,
                retry_after=_retry_after_seconds(response),
            )

        try:
            return response.json()
        except ValueError as error:
            raise AIProviderError(f"Groq returned a non-JSON response: {error}") from error

    def run_investigation(
        self,
        *,
        system_prompt,
        user_message,
        tool_definitions,
        submit_tool_name,
        submit_tool_schema,
        dispatch,
        cur,
        conn,
        investigation_id,
    ) -> dict[str, Any]:
        tools = [
            _openai_tool(
                tool_def["name"], tool_def["description"], tool_def["input_schema"]
            )
            for tool_def in tool_definitions
        ]
        tools.append(
            _openai_tool(
                submit_tool_name,
                "Submit your complete, final investigation findings. Call this exactly once, "
                "only after you have gathered enough evidence with the other tools. This ends "
                "the investigation.",
                submit_tool_schema,
            )
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        total_tool_calls = 0

        client = self._client or httpx.Client()
        owns_client = self._client is None

        try:
            for _turn in range(MAX_TOOL_TURNS):
                body = self._post(
                    client,
                    {
                        "model": self._model,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": GROQ_TOOL_CHOICE,
                        "max_completion_tokens": GROQ_MAX_COMPLETION_TOKENS,
                        # Reasoning tokens bill against max_completion_tokens
                        # but never appear in AiInvestigationResult -- see
                        # config.GROQ_REASONING_EFFORT.
                        "reasoning_effort": GROQ_REASONING_EFFORT,
                    },
                )

                choices = body.get("choices") or []
                if not choices:
                    raise AIProviderError("Groq returned no choices.")

                message = choices[0].get("message") or {}
                tool_calls = message.get("tool_calls") or []

                if not tool_calls:
                    raise AIProviderError(
                        "Groq did not produce a tool call "
                        f"(finish_reason={choices[0].get('finish_reason')!r})."
                    )

                submission = next(
                    (
                        call
                        for call in tool_calls
                        if (call.get("function") or {}).get("name") == submit_tool_name
                    ),
                    None,
                )
                if submission is not None:
                    return self._parse_submission(submission)

                total_tool_calls += len(tool_calls)
                if total_tool_calls > MAX_TOTAL_TOOL_CALLS:
                    raise AIProviderError(
                        f"Exceeded the maximum of {MAX_TOTAL_TOOL_CALLS} tool calls for one "
                        "investigation."
                    )

                messages.append(message)

                for call in tool_calls:
                    function = call.get("function") or {}
                    name = function.get("name") or ""
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                        if not isinstance(arguments, dict):
                            raise ValueError("tool arguments were not a JSON object")
                        # execute_tool enforces the read-only dispatch and
                        # rejects any name that is not a known tool.
                        content = json.dumps(
                            execute_tool(cur, investigation_id, dispatch, name, arguments)
                        )
                    except Exception as error:  # noqa: BLE001 -- surfaced to the model
                        content = str(error)
                    finally:
                        # Same durability rule as the other two providers:
                        # a tool call that was actually attempted is
                        # recorded and committed regardless of outcome, so
                        # the audit trail survives a later failure.
                        conn.commit()

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "name": name,
                            "content": content,
                        }
                    )

            raise AIProviderError(
                f"Groq did not reach a conclusion within {MAX_TOOL_TURNS} tool-call turns."
            )
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _parse_submission(submission: dict[str, Any]) -> dict[str, Any]:
        """OpenAI-compatible tool arguments arrive as a JSON *string*,
        unlike Gemini's already-parsed dict. Anything that is not a JSON
        object is a provider failure, never something to repair -- the
        caller must not be handed a half-valid payload it might persist."""
        raw = (submission.get("function") or {}).get("arguments")
        try:
            parsed = json.loads(raw or "")
        except (TypeError, ValueError) as error:
            raise AIProviderError(
                f"Groq returned malformed structured output: {error}"
            ) from error

        if not isinstance(parsed, dict):
            raise AIProviderError(
                "Groq returned structured output that was not a JSON object."
            )
        return parsed
