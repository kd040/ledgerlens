"""Google Gemini implementation of the AI provider seam (see base.py).

Uses the current official `google-genai` SDK (not the deprecated
`google-generativeai` package). The existing 11 read-only tool
definitions (JSON Schema dicts, already provider-agnostic) are passed
straight through as `parameters_json_schema` on Gemini's
FunctionDeclaration -- no separate schema format or duplicated tool
logic. The model is forced into function-calling mode every turn
(FunctionCallingConfigMode.ANY), and a dedicated submit-tool call ends
the loop, exactly mirroring the Anthropic provider's design so both
providers share the same investigator.py contract.

automatic_function_calling is explicitly disabled: this module executes
every tool call itself, one at a time, through the existing
tools.execute_tool (read-only dispatch + audit recording) -- Gemini
never runs Python, never touches the database, and never sees a
credential.
"""

import os
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.config import (
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MODEL,
    GEMINI_REQUEST_TIMEOUT_MS,
    MAX_TOOL_TURNS,
    MAX_TOTAL_TOOL_CALLS,
)
from app.ai.providers.base import RETRYABLE_STATUS_CODES, AIProvider, AIProviderError
from app.ai.tools import execute_tool


def _is_transient(error: genai_errors.APIError) -> bool:
    """Gemini's own 503 UNAVAILABLE / "model is currently experiencing
    high demand" and 429 rate limits are worth another attempt; a 400
    bad request, a 401 bad key or a 404 unknown model are not, and must
    keep surfacing as themselves (see AIProviderError.retryable)."""
    return getattr(error, "code", None) in RETRYABLE_STATUS_CODES


class GeminiProvider(AIProvider):
    def __init__(self, *, client: "genai.Client | None" = None, model: str | None = None):
        self._client = client
        self._model = model or GEMINI_MODEL

    def _build_client(self) -> "genai.Client":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise AIProviderError(
                "Gemini is not configured (GEMINI_API_KEY is not set).", status_code=503
            )
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=GEMINI_REQUEST_TIMEOUT_MS),
        )

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

        function_declarations = [
            types.FunctionDeclaration(
                name=tool_def["name"],
                description=tool_def["description"],
                parameters_json_schema=tool_def["input_schema"],
            )
            for tool_def in tool_definitions
        ]
        function_declarations.append(
            types.FunctionDeclaration(
                name=submit_tool_name,
                description=(
                    "Submit your complete, final investigation findings. Call this exactly "
                    "once, only after you have gathered enough evidence with the other tools. "
                    "This ends the investigation."
                ),
                parameters_json_schema=submit_tool_schema,
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[types.Tool(function_declarations=function_declarations)],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY
                )
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        )

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        ]
        total_tool_calls = 0

        for _turn in range(MAX_TOOL_TURNS):
            try:
                response = client.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
            except genai_errors.ClientError as error:
                raise AIProviderError(
                    f"Gemini rejected the request: {error}",
                    retryable=_is_transient(error),
                    provider_status=getattr(error, "code", None),
                ) from error
            except genai_errors.ServerError as error:
                raise AIProviderError(
                    f"Gemini provider error: {error}",
                    retryable=_is_transient(error),
                    provider_status=getattr(error, "code", None),
                ) from error
            except genai_errors.APIError as error:
                raise AIProviderError(
                    f"Gemini returned an error: {error}",
                    retryable=_is_transient(error),
                    provider_status=getattr(error, "code", None),
                ) from error
            except Exception as error:  # covers HTTP-layer timeouts/connection errors
                # Never reached the model at all -- a timeout or a dropped
                # connection says nothing about whether the request itself
                # is valid, so it is always worth one more attempt.
                raise AIProviderError(
                    f"Could not reach Gemini: {error}", retryable=True
                ) from error

            if not response.candidates:
                raise AIProviderError("Gemini returned no candidates.")

            candidate = response.candidates[0]

            if candidate.finish_reason == types.FinishReason.MALFORMED_FUNCTION_CALL:
                raise AIProviderError("Gemini produced a malformed function call.")

            parts = candidate.content.parts if candidate.content else []
            function_call_parts = [part for part in parts if part.function_call is not None]

            if not function_call_parts:
                raise AIProviderError(
                    "Gemini did not produce a function call "
                    f"(finish_reason={candidate.finish_reason!r})."
                )

            submission = next(
                (
                    part
                    for part in function_call_parts
                    if part.function_call.name == submit_tool_name
                ),
                None,
            )
            if submission is not None:
                return dict(submission.function_call.args or {})

            total_tool_calls += len(function_call_parts)
            if total_tool_calls > MAX_TOTAL_TOOL_CALLS:
                raise AIProviderError(
                    f"Exceeded the maximum of {MAX_TOTAL_TOOL_CALLS} tool calls for one "
                    "investigation."
                )

            contents.append(candidate.content)

            response_parts = []
            for part in function_call_parts:
                function_call = part.function_call
                try:
                    result = execute_tool(
                        cur, investigation_id, dispatch, function_call.name,
                        dict(function_call.args or {}),
                    )
                    response_payload = {"result": result}
                except Exception as error:  # noqa: BLE001 -- surfaced back to the model
                    response_payload = {"error": str(error)}
                finally:
                    # Same durability rule as the Anthropic provider: a
                    # tool call that was actually attempted is recorded
                    # and committed regardless of outcome, so the audit
                    # trail survives even if the run fails later.
                    conn.commit()

                response_parts.append(
                    types.Part.from_function_response(
                        name=function_call.name, response=response_payload
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))

        raise AIProviderError(
            f"Gemini did not reach a conclusion within {MAX_TOOL_TURNS} tool-call turns."
        )
