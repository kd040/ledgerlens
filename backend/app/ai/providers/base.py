"""Provider-agnostic seam behind the AI Investigator's model layer.
investigator.py, tools.py, and schemas.py never import a concrete
provider directly -- they depend only on this contract, so Anthropic and
Gemini (or any future provider) are interchangeable via the AI_PROVIDER
setting, with zero change to the tool set, the structured-output schema,
the financial validation, or the persistence logic.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable


class AIProviderError(Exception):
    """Raised by any provider for any failure -- missing/invalid key,
    timeout, rate limit, malformed function call, no structured
    conclusion produced, tool-call limit exceeded. investigator.py
    catches this and re-raises it as the same AiInvestigationError it
    already uses for every other failure mode (preserving status_code),
    so callers never need to know which provider ran."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


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
