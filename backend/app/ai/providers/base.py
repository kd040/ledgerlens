"""Provider-agnostic seam behind the AI Investigator's model layer.
investigator.py, tools.py, and schemas.py never import a concrete
provider directly -- they depend only on this contract, so Anthropic and
Gemini (or any future provider) are interchangeable via the AI_PROVIDER
setting, with zero change to the tool set, the structured-output schema,
the financial validation, or the persistence logic.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


# HTTP statuses that mean "the provider is momentarily unwell, the same
# request may well succeed shortly" -- as opposed to a request or
# configuration this provider will reject identically every time.
# Deliberately an allow-list: an unrecognised status is NOT retried, so a
# new permanent-failure code can never be mistaken for a transient one.
# 498 is Groq's own "flex tier capacity exceeded"; 529 is Anthropic's
# "overloaded".
RETRYABLE_STATUS_CODES = frozenset({408, 429, 498, 500, 502, 503, 504, 529})


class AIProviderError(Exception):
    """Raised by any provider for any failure -- missing/invalid key,
    timeout, rate limit, malformed function call, no structured
    conclusion produced, tool-call limit exceeded. investigator.py
    catches this and re-raises it as the same AiInvestigationError it
    already uses for every other failure mode (preserving status_code),
    so callers never need to know which provider ran.

    `retryable` says whether the SAME request is worth attempting again
    (on this provider or another one) -- see failover.py. It is False by
    default on purpose: a bad API key, an invalid model name, a malformed
    schema or an outright bug must surface as itself rather than being
    laundered into "temporarily unavailable" by a pointless retry. Only a
    provider that has positively identified a transient condition sets it
    True.

    `retry_after` is the provider's own Retry-After hint in seconds,
    when it sent one (a 429 usually does). It is a request, not an
    obligation -- failover.py honours it only if it is short enough to
    fit the remaining time budget.

    `provider_status` is the status the upstream provider actually
    returned (Gemini's 503, Groq's 429, ...), kept separate from
    `status_code`, which is what LedgerLens's own API returns to the
    caller. The two genuinely differ -- a Gemini 503 surfaces as a 502
    from this API -- and an operator reading the log needs the upstream
    number, not the translated one.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        *,
        retryable: bool = False,
        provider_status: int | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.provider_status = provider_status
        self.retry_after = retry_after


class AIUnavailableError(AIProviderError):
    """Terminal state of the failover chain: every provider was tried and
    every one of them failed transiently. Carries the clean, user-facing
    message -- the raw provider diagnostics stay in the server log (see
    failover.py), never in the API response."""


class AIProvider(ABC):
    @abstractmethod
    def run_investigation(
        self,
        *,
        system_prompt: str,
        user_message: str,
        tool_definitions: list[dict[str, Any]],
        submit_tool_name: str,
        submit_tool_schema: dict[str, Any],
        dispatch: dict[str, Callable[[dict[str, Any]], Any]],
        cur,
        conn,
        investigation_id: str,
    ) -> dict[str, Any]:
        """Runs the full tool-calling loop and returns the raw structured
        payload from the model's terminal submit-tool call -- NOT yet
        Pydantic-validated; the caller (investigator.py) does that plus
        the financial cross-check. Every tool call the model makes must
        be executed through tools.execute_tool (which enforces the
        read-only dispatch and records the call via the existing
        record_tool_call, success or failure) -- never any other way.
        Unknown tool names must never be executed."""
        raise NotImplementedError
