"""Sequential provider failover for the AI Investigator.

    primary (Gemini)
        |- transient failure -> one bounded retry
        |                           |- transient failure -> fallback (Groq)
        |                                                       |- failure -> AIUnavailableError
        |- permanent failure -> raised as itself, immediately

Providers are tried strictly one at a time -- never concurrently -- so a
fallback only ever costs anything when the primary has actually failed.

Two rules do the real work here:

1. Only a *transient* failure moves the chain forward. A bad API key, an
   unknown model, a malformed schema or a plain bug is permanent: it is
   re-raised unchanged so it stays visible instead of being laundered
   into "temporarily unavailable" by a fallback that would fail the same
   way tomorrow.

2. Once every provider has been tried, the caller gets a clean
   application-level message and the raw provider diagnostics stay in the
   server log. The frontend renders the API's `detail` verbatim, so
   "Gemini provider error: 503 UNAVAILABLE ..." must never reach it.

Nothing here fabricates a result. If no provider produced a validated
structured conclusion, the chain raises -- it never invents one, and
because it raises before investigator.py's persist step, nothing is
written to the investigation either.
"""

import logging
import random
import time
from typing import Any

from app.ai.config import (
    AI_FALLBACK_RETRY_BUDGET_SECONDS,
    FALLBACK_RETRY_AFTER_MAX_SECONDS,
    PRIMARY_RETRY_ATTEMPTS,
    RETRY_BACKOFF_JITTER_SECONDS,
    RETRY_BACKOFF_SECONDS,
)
from app.ai.providers.base import AIProvider, AIProviderError, AIUnavailableError

logger = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE = "AI Investigator is temporarily unavailable. Please try again in a moment."


def _status_of(error: AIProviderError) -> str:
    """Prefer the status the provider itself returned -- a Gemini 503 must
    read as 503 in the log even though this API translates it to a 502."""
    upstream = getattr(error, "provider_status", None)
    return str(upstream if upstream is not None else getattr(error, "status_code", "unknown"))


class FailoverProvider(AIProvider):
    """Wraps an ordered primary/fallback pair. Implements AIProvider
    itself, so investigator.py, the tool set, the submit schema and the
    financial validation are all completely unaware that failover exists.

    `fallback=None` is a supported configuration (no GROQ_API_KEY set): the
    chain then degrades to "primary, with one retry on transient failure"
    and re-raises the primary's own error, preserving the exact behaviour
    this system had before Groq was added.
    """

    def __init__(
        self,
        primary: AIProvider,
        fallback: AIProvider | None = None,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name
        self._sleep = sleep
        self._clock = clock

    def _backoff(self, attempt: int) -> None:
        """Short exponential backoff with jitter. Bounded on purpose: the
        whole point is to ride out a momentary spike without turning a
        failing request into a gateway timeout."""
        delay = RETRY_BACKOFF_SECONDS * (2**attempt)
        self._sleep(delay + random.uniform(0, RETRY_BACKOFF_JITTER_SECONDS))

    def run_investigation(self, **kwargs):
        deadline = self._clock() + AI_FALLBACK_RETRY_BUDGET_SECONDS
        result, primary_error = self._run_primary(**kwargs)

        if primary_error is None:  # primary succeeded; fallback never runs
            return result

        if self._fallback is None:
            # No fallback configured (no GROQ_API_KEY): behave exactly as
            # this system did before Groq existed and surface the
            # primary's own error.
            logger.error(
                "AI investigation: provider=%s status=%s action=no_fallback_configured",
                self._primary_name,
                _status_of(primary_error),
            )
            raise primary_error

        logger.warning(
            "AI investigation: provider=%s retry=failed action=fallback",
            self._primary_name,
        )

        try:
            result = self._run_fallback(deadline, **kwargs)
        except AIProviderError as error:
            # Every provider is now exhausted. Log the real cause -- which
            # may well be a *permanent* Groq misconfiguration an operator
            # needs to fix -- but tell the user only that the feature is
            # unavailable, because from their side it genuinely is.
            logger.error(
                "AI investigation: provider=%s status=%s action=failed detail=%s",
                self._fallback_name,
                _status_of(error),
                error,
            )
            raise AIUnavailableError(UNAVAILABLE_MESSAGE, status_code=503) from error

        logger.info("AI investigation: provider=%s status=success", self._fallback_name)
        return result

    def _run_fallback(self, deadline: float, **kwargs):
        """The fallback, plus at most ONE extra attempt when the provider
        itself says a short wait would help.

        A 429 from Groq means the TPM window is momentarily full, not that
        the request is wrong -- but the advertised wait is only worth
        taking if it fits the time this request has left. Free-tier Groq
        typically advertises ~21s, which does NOT fit, so that case still
        fails fast into the clean 503 rather than risking a gateway
        timeout."""
        try:
            return self._fallback.run_investigation(**kwargs)
        except AIProviderError as error:
            wait = self._honourable_wait(error, deadline)
            if wait is None:
                raise

            logger.warning(
                "AI investigation: provider=%s status=%s retry_after=%.1fs action=retry",
                self._fallback_name,
                _status_of(error),
                wait,
            )
            self._sleep(wait)
            return self._fallback.run_investigation(**kwargs)

    def _honourable_wait(self, error: AIProviderError, deadline: float) -> float | None:
        """The provider's Retry-After, or None if it must not be honoured.

        Every condition has to hold: the failure is transient, the
        provider actually named a delay, that delay is short, and waiting
        it out still leaves time to make the call before the budget runs
        out. Anything else fails fast."""
        wait = getattr(error, "retry_after", None)

        if not error.retryable or wait is None:
            return None
        if wait > FALLBACK_RETRY_AFTER_MAX_SECONDS:
            logger.warning(
                "AI investigation: provider=%s status=%s retry_after=%.1fs "
                "action=abort reason=retry_after_exceeds_cap",
                self._fallback_name,
                _status_of(error),
                wait,
            )
            return None
        if self._clock() + wait >= deadline:
            logger.warning(
                "AI investigation: provider=%s status=%s retry_after=%.1fs "
                "action=abort reason=exceeds_time_budget",
                self._fallback_name,
                _status_of(error),
                wait,
            )
            return None
        return wait

    def _run_primary(self, **kwargs) -> tuple[Any, AIProviderError | None]:
        """Runs the primary up to 1 + PRIMARY_RETRY_ATTEMPTS times.

        Returns (payload, None) when the primary succeeds and
        (None, error) with the final transient error when it is exhausted.
        A permanent error is re-raised from here and never reaches the
        fallback. Returned rather than stashed on self so one provider
        instance carries no per-request state.
        """
        for attempt in range(PRIMARY_RETRY_ATTEMPTS + 1):
            try:
                result = self._primary.run_investigation(**kwargs)
            except AIProviderError as error:
                if not error.retryable:
                    # Configuration or programming fault: surface it as
                    # itself. Switching providers would only hide it.
                    logger.error(
                        "AI investigation: provider=%s status=%s action=abort detail=%s",
                        self._primary_name,
                        _status_of(error),
                        error,
                    )
                    raise

                is_last_attempt = attempt == PRIMARY_RETRY_ATTEMPTS
                logger.warning(
                    "AI investigation: provider=%s status=%s action=%s",
                    self._primary_name,
                    _status_of(error),
                    "fallback" if is_last_attempt else "retry",
                )
                if is_last_attempt:
                    return None, error
                self._backoff(attempt)
                continue

            logger.info("AI investigation: provider=%s status=success", self._primary_name)
            return result, None

        raise AssertionError("unreachable: the loop always returns")
