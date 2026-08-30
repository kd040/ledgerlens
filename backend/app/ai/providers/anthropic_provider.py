"""Anthropic implementation of the AI provider seam (see base.py). This
is the same tool-calling loop investigator.py used to own directly --
moved here unchanged in behavior, just behind the provider interface, so
Gemini can sit alongside it without investigator.py knowing which one is
running. `client=` (injected in tests) keeps working exactly as before.
"""

import json
import os
from typing import Any

import anthropic

from app.ai.config import (
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_MODEL,
    ANTHROPIC_REQUEST_TIMEOUT_SECONDS,
    MAX_TOOL_TURNS,
    MAX_TOTAL_TOOL_CALLS,
)
from app.ai.providers.base import AIProvider, AIProviderError
from app.ai.tools import execute_tool


class AnthropicProvider(AIProvider):
    def __init__(self, *, client: "anthropic.Anthropic | None" = None, model: str | None = None):
        self._client = client
        self._model = model or ANTHROPIC_MODEL

    def _build_client(self) -> anthropic.Anthropic:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AIProviderError(
                "Anthropic is not configured (ANTHROPIC_API_KEY is not set).", status_code=503
            )
        return anthropic.Anthropic(api_key=api_key, timeout=ANTHROPIC_REQUEST_TIMEOUT_SECONDS)

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
        client = self._client or self._build_client()

        submit_tool = {
            "name": submit_tool_name,
            "description": (
                "Submit your complete, final investigation findings. Call this exactly once, "
                "only after you have gathered enough evidence with the other tools. This ends "
                "the investigation."
            ),
            "input_schema": submit_tool_schema,
        }
        tools = [*tool_definitions, submit_tool]

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        total_tool_calls = 0

        for _turn in range(MAX_TOOL_TURNS):
            try:
                response = client.messages.create(
                    model=self._model,
                    max_tokens=ANTHROPIC_MAX_TOKENS,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                )
            except anthropic.RateLimitError as error:
                raise AIProviderError(f"Anthropic rate limit reached: {error}") from error
            except anthropic.APITimeoutError as error:
                raise AIProviderError(f"Anthropic request timed out: {error}") from error
            except anthropic.APIConnectionError as error:
                raise AIProviderError(f"Could not reach Anthropic: {error}") from error
            except anthropic.APIStatusError as error:
                raise AIProviderError(f"Anthropic returned an error: {error}") from error

            if response.stop_reason != "tool_use":
                raise AIProviderError(
                    "Anthropic did not produce structured findings "
                    f"(stop_reason={response.stop_reason!r})."
                )

            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

            submission = next(
                (block for block in tool_use_blocks if block.name == submit_tool_name), None
            )
            if submission is not None:
                return submission.input

            total_tool_calls += len(tool_use_blocks)
            if total_tool_calls > MAX_TOTAL_TOOL_CALLS:
                raise AIProviderError(
                    f"Exceeded the maximum of {MAX_TOTAL_TOOL_CALLS} tool calls for one "
                    "investigation."
                )

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_use_blocks:
                try:
                    result = execute_tool(cur, investigation_id, dispatch, block.name, block.input)
                    content = json.dumps(result)
                    is_error = False
                except Exception as error:  # noqa: BLE001 -- surfaced to the model as a tool error
                    content = str(error)
                    is_error = True
                finally:
                    # execute_tool always records the attempt (success or
                    # failure) -- commit either way so the audit trail
                    # survives even if the run fails later.
                    conn.commit()

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        raise AIProviderError(
            f"Anthropic did not reach a conclusion within {MAX_TOOL_TURNS} tool-call turns."
        )
