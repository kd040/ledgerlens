"""Provider failover for the AI Investigator: Gemini primary -> one
bounded retry -> Groq fallback -> clean AI-unavailable error.

No live API call is made anywhere in this file. Both providers are the
REAL provider classes -- GeminiProvider(client=FakeGeminiClient) and
GroqProvider(client=httpx.Client(transport=MockTransport)) -- so the
transient/permanent classification, the HTTP status handling and the
JSON-argument parsing are all genuinely exercised rather than mocked
away. Only the network is faked.

Throwaway TEST-FAILOVER-* rows only; cleans up after itself.

Run directly: python backend/tests/test_ai_failover.py
"""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import psycopg
from google.genai import errors as genai_errors

from app.ai.config import PRIMARY_RETRY_ATTEMPTS
from app.ai.investigator import AiInvestigationError, run_ai_investigation
from app.ai.providers.base import AIProviderError, AIUnavailableError
from app.ai.providers.failover import UNAVAILABLE_MESSAGE, FailoverProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.groq_provider import GroqProvider
from app.investigation.runners.deterministic import connect

FINANCIAL_ANALYSIS = {
    "gross_amount": "1700.00",
    "fee_amount": "50.00",
    "tax_amount": "6.95",
    "adjustment_amount": "0.00",
    "expected_amount": "1643.05",
    "observed_amount": "1063.73",
    "difference": "579.32",
}

# Never a real credential: asserted absent from every API response below.
FAKE_GROQ_KEY = "gsk_TESTFAILOVER_not_a_real_key_0000000000"


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

def _insert_exception(cur, code: str, category: str, description: str) -> str:
    cur.execute(
        """
        insert into exceptions (exception_code, category, description, financial_impact, status)
        values (%s, %s, %s, 579.32, 'OPEN')
        returning id
        """,
        (code, category, description),
    )
    return str(cur.fetchone()[0])


def _insert_investigation(cur, exception_id: str) -> str:
    cur.execute(
        """
        insert into investigations (
            exception_id, status, recommendation, financial_analysis, completed_at
        )
        values (%s, 'COMPLETED', 'HUMAN_REVIEW', %s, now())
        returning id
        """,
        (exception_id, psycopg.types.json.Jsonb(FINANCIAL_ANALYSIS)),
    )
    return str(cur.fetchone()[0])


def _cleanup(cur, conn, exception_id: str) -> None:
    cur.execute("delete from investigations where exception_id = %s", (exception_id,))
    cur.execute("delete from exceptions where id = %s", (exception_id,))
    conn.commit()


class _Case:
    """One throwaway exception + investigation, torn down on exit."""

    def __init__(self, slug: str):
        self.payment_reference = f"pay_testfailover{slug}"
        self.description = (
            f"Payment {self.payment_reference} expected 1643.05 but settlement "
            "contains 1063.73. Difference: 579.32."
        )

    def __enter__(self):
        self._conn = connect().__enter__()
        self.conn = self._conn
        self.cur = self._conn.cursor().__enter__()
        self.exception_id = _insert_exception(
            self.cur, "EX01", "Amount Mismatch", self.description
        )
        self.investigation_id = _insert_investigation(self.cur, self.exception_id)
        self.conn.commit()
        return self

    def __exit__(self, *exc):
        # A failed assertion can leave the connection in an aborted
        # transaction; roll back first so the cleanup DELETEs still run and
        # no TEST-FAILOVER row survives a red test.
        self.conn.rollback()
        _cleanup(self.cur, self.conn, self.exception_id)
        self.cur.close()
        self._conn.close()
        return False

    def row(self, column: str):
        self.cur.execute(
            f"select {column} from investigations where id = %s", (self.investigation_id,)
        )
        return self.cur.fetchone()[0]

    def evidence_count(self) -> int:
        self.cur.execute(
            "select count(*) from investigation_evidence where investigation_id = %s",
            (self.investigation_id,),
        )
        return self.cur.fetchone()[0]


def _valid_ai_payload(payment_reference: str, root_cause: str) -> dict:
    """`root_cause` distinguishes which provider produced the result, so a
    test can prove WHICH one the returned findings came from."""
    return {
        "summary": {
            "exception_code": "EX01",
            "payment_reference": payment_reference,
            "financial_gap": "579.32",
        },
        "financial_analysis": {
            "expected_amount": "1643.05",
            "observed_amount": "1063.73",
            "difference": "579.32",
        },
        "evidence_reviewed": [
            {"record_type": "payment", "record_id": None, "summary": "Payment checked."}
        ],
        "hypotheses": [
            {
                "title": "Settlement is short of the expected net payout.",
                "status": "SUPPORTED",
                "confidence": 75,
                "supporting_evidence": ["Expected 1643.05, observed 1063.73"],
                "contradicting_evidence": [],
            }
        ],
        "contradictions": [],
        "root_cause_assessment": {
            "known": root_cause,
            "likely": "An additional deduction not captured in fees/tax/adjustments.",
            "not_proven": "The exact source of the remaining difference is unconfirmed.",
        },
        "confidence": 58,
        "recommendation": "HUMAN_REVIEW",
    }


# ------------------------------------------------------------------
# Fake Gemini transport
# ------------------------------------------------------------------

def _gemini_submission(payment_reference: str, root_cause: str):
    part = SimpleNamespace(
        function_call=SimpleNamespace(
            name="submit_investigation_findings",
            args=_valid_ai_payload(payment_reference, root_cause),
            id="c1",
        ),
        text=None,
    )
    candidate = SimpleNamespace(content=SimpleNamespace(parts=[part]), finish_reason=None)
    return SimpleNamespace(candidates=[candidate])


class _FakeGeminiModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    def generate_content(self, *, model, contents, config):
        self.call_count += 1
        if not self._responses:
            raise AssertionError("fake Gemini exhausted -- more turns than the test queued")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeGeminiClient:
    def __init__(self, responses):
        self.models = _FakeGeminiModels(responses)


def _gemini(responses) -> GeminiProvider:
    return GeminiProvider(client=_FakeGeminiClient(responses))


# ------------------------------------------------------------------
# Fake Groq transport (real GroqProvider over httpx.MockTransport)
# ------------------------------------------------------------------

class _GroqRecorder:
    """Captures every outbound Groq request so tests can assert on the
    payload actually sent -- model, tool_choice, prompt, and the absence
    of any credential in places it must not appear."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.payloads: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.payloads.append(json.loads(request.content))
        if not self._responses:
            raise AssertionError("fake Groq exhausted -- more turns than the test queued")
        queued = self._responses.pop(0)
        status, body = queued[0], queued[1]
        headers = queued[2] if len(queued) > 2 else None
        return httpx.Response(status, json=body, headers=headers)

    @property
    def call_count(self) -> int:
        return len(self.requests)


def _groq_submission_body(payment_reference: str, root_cause: str) -> dict:
    return _groq_tool_call_body(
        "submit_investigation_findings", _valid_ai_payload(payment_reference, root_cause)
    )


def _groq_tool_call_body(name: str, arguments, call_id: str = "gcall_1") -> dict:
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": arguments
                                if isinstance(arguments, str)
                                else json.dumps(arguments),
                            },
                        }
                    ],
                },
            }
        ]
    }


def _groq(responses) -> tuple[GroqProvider, _GroqRecorder]:
    recorder = _GroqRecorder(responses)
    client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    return GroqProvider(client=client, api_key=FAKE_GROQ_KEY), recorder


class _CountingProvider:
    """Stands in for a provider that must never be reached."""

    def __init__(self):
        self.call_count = 0

    def run_investigation(self, **kwargs):
        self.call_count += 1
        raise AssertionError("this provider should not have been called")


def _chain(primary, fallback):
    sleeps: list[float] = []
    provider = FailoverProvider(
        primary,
        fallback,
        primary_name="gemini",
        fallback_name="groq",
        sleep=sleeps.append,
    )
    return provider, sleeps


def _server_error(code: int, status: str):
    return genai_errors.ServerError(code, {"error": {"message": "overloaded", "status": status}})


def _client_error(code: int, status: str):
    return genai_errors.ClientError(code, {"error": {"message": status, "status": status}})


# ------------------------------------------------------------------
# 1. Gemini succeeds immediately -> Groq is never called
# ------------------------------------------------------------------

def test_gemini_success_never_calls_groq():
    with _Case("001") as case:
        groq = _CountingProvider()
        provider, sleeps = _chain(
            _gemini([_gemini_submission(case.payment_reference, "Gemini reached this.")]), groq
        )

        result = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

        assert groq.call_count == 0, "fallback ran even though the primary succeeded"
        assert sleeps == [], "backed off despite there being no failure"
        assert (
            result["ai_result"]["root_cause_assessment"]["known"] == "Gemini reached this."
        )


# ------------------------------------------------------------------
# 2. Gemini 503 -> one retry -> retry succeeds -> Groq is never called
# ------------------------------------------------------------------

def test_transient_503_retries_once_and_succeeds_without_fallback():
    with _Case("002") as case:
        groq = _CountingProvider()
        gemini = _gemini(
            [
                _server_error(503, "UNAVAILABLE"),
                _gemini_submission(case.payment_reference, "Gemini reached this on retry."),
            ]
        )
        provider, sleeps = _chain(gemini, groq)

        result = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

        assert gemini._client.models.call_count == 2, "the primary was not retried exactly once"
        assert groq.call_count == 0, "fell back even though the retry succeeded"
        assert len(sleeps) == 1 and 0 < sleeps[0] < 2, f"unbounded or absent backoff: {sleeps}"
        assert (
            result["ai_result"]["root_cause_assessment"]["known"]
            == "Gemini reached this on retry."
        )


# ------------------------------------------------------------------
# 3. Gemini 503 -> retry fails -> Groq succeeds -> Groq's result wins
# ------------------------------------------------------------------

def test_falls_back_to_groq_after_retry_fails():
    with _Case("003") as case:
        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        groq, recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq reached this."))]
        )
        provider, sleeps = _chain(gemini, groq)

        result = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

        assert gemini._client.models.call_count == 1 + PRIMARY_RETRY_ATTEMPTS
        assert recorder.call_count == 1, "the fallback did not run exactly once"
        assert len(sleeps) == PRIMARY_RETRY_ATTEMPTS
        assert (
            result["ai_result"]["root_cause_assessment"]["known"] == "Groq reached this."
        ), "the persisted findings did not come from the fallback"
        # The fallback really did write through the normal pipeline.
        assert case.row("confidence") == Decimal("58")
        assert case.row("recommendation") == "HUMAN_REVIEW"


# ------------------------------------------------------------------
# 4. Gemini 429 rate limit is transient too
# ------------------------------------------------------------------

def test_rate_limit_429_retries_then_falls_back():
    with _Case("004") as case:
        gemini = _gemini(
            [_client_error(429, "RESOURCE_EXHAUSTED"), _client_error(429, "RESOURCE_EXHAUSTED")]
        )
        groq, recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq handled the 429."))]
        )
        provider, _sleeps = _chain(gemini, groq)

        result = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

        assert gemini._client.models.call_count == 1 + PRIMARY_RETRY_ATTEMPTS
        assert recorder.call_count == 1
        assert (
            result["ai_result"]["root_cause_assessment"]["known"] == "Groq handled the 429."
        )


def test_network_timeout_is_transient():
    with _Case("005") as case:
        gemini = _gemini([TimeoutError("timed out"), TimeoutError("timed out")])
        groq, recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq handled the timeout."))]
        )
        provider, _sleeps = _chain(gemini, groq)

        run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
        assert recorder.call_count == 1


# ------------------------------------------------------------------
# 5. A permanent 401 is NOT retried and NOT hidden behind a fallback
# ------------------------------------------------------------------

def test_permanent_401_does_not_retry_or_fall_back():
    with _Case("006") as case:
        gemini = _gemini([_client_error(401, "UNAUTHENTICATED")])
        groq = _CountingProvider()
        provider, sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            # The real configuration fault must stay visible, not be
            # laundered into "temporarily unavailable".
            assert "UNAUTHENTICATED" in str(error), str(error)
            assert UNAVAILABLE_MESSAGE not in str(error)

        assert gemini._client.models.call_count == 1, "a permanent error was retried"
        assert groq.call_count == 0, "a permanent error was hidden by switching providers"
        assert sleeps == []


def test_permanent_400_bad_request_does_not_fall_back():
    with _Case("007") as case:
        gemini = _gemini([_client_error(400, "INVALID_ARGUMENT")])
        groq = _CountingProvider()
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert "INVALID_ARGUMENT" in str(error)
        assert groq.call_count == 0


def test_permanent_404_unknown_model_does_not_fall_back():
    with _Case("008") as case:
        gemini = _gemini([_client_error(404, "NOT_FOUND")])
        groq = _CountingProvider()
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError:
            pass
        assert groq.call_count == 0


# ------------------------------------------------------------------
# 6 + 12. Both providers fail -> clean error, and NO fabricated result
# ------------------------------------------------------------------

def test_both_providers_fail_returns_clean_error_and_persists_nothing():
    with _Case("009") as case:
        evidence_before = case.evidence_count()

        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        groq, recorder = _groq([(503, {"error": {"message": "over capacity"}})])
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert str(error) == UNAVAILABLE_MESSAGE, str(error)
            assert error.status_code == 503
            # No provider internals leak to the API response.
            for leak in ("Gemini", "Groq", "UNAVAILABLE", "503", "over capacity"):
                assert leak not in str(error), f"leaked {leak!r} to the user"

        assert recorder.call_count == 1

        # 12. Nothing fabricated: the investigation is untouched.
        assert case.row("root_cause") is None
        assert case.row("root_cause_assessment") is None
        assert case.row("confidence") is None
        assert case.evidence_count() == evidence_before


def test_groq_permanent_auth_failure_still_reads_as_unavailable_to_the_user():
    """Once the primary has failed transiently the feature IS unavailable,
    whatever the fallback's own reason -- but the operator still gets the
    real cause in the log (asserted separately in the log test below)."""
    with _Case("010") as case:
        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        groq, _recorder = _groq([(401, {"error": {"message": "Invalid API Key"}})])
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert str(error) == UNAVAILABLE_MESSAGE
            assert "Invalid API Key" not in str(error)


# ------------------------------------------------------------------
# 7. Malformed Groq structured output -> nothing invalid is persisted
# ------------------------------------------------------------------

def test_groq_non_json_arguments_persist_nothing():
    with _Case("011") as case:
        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        groq, _recorder = _groq(
            [(200, _groq_tool_call_body("submit_investigation_findings", "{not valid json"))]
        )
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert str(error) == UNAVAILABLE_MESSAGE

        assert case.row("confidence") is None
        assert case.row("root_cause_assessment") is None
        assert case.evidence_count() == 0


def test_groq_schema_violating_output_persists_nothing():
    """Valid JSON, wrong shape -- must be rejected by the same Pydantic
    contract that guards the Gemini path, not repaired."""
    with _Case("012") as case:
        broken = _valid_ai_payload(case.payment_reference, "Groq.")
        broken["recommendation"] = "DEFINITELY_RESOLVE_IT"  # not in the Literal

        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        groq, _recorder = _groq(
            [(200, _groq_tool_call_body("submit_investigation_findings", broken))]
        )
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert "did not match the required structure" in str(error)

        assert case.row("confidence") is None
        assert case.evidence_count() == 0


def test_groq_financial_mismatch_is_rejected_like_gemini():
    """The fallback gets no exemption from the financial cross-check."""
    with _Case("013") as case:
        tampered = _valid_ai_payload(case.payment_reference, "Groq.")
        tampered["financial_analysis"]["difference"] = "1.00"

        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        groq, _recorder = _groq(
            [(200, _groq_tool_call_body("submit_investigation_findings", tampered))]
        )
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert "does not match the verified" in str(error)

        assert case.row("confidence") is None


# ------------------------------------------------------------------
# 8. Identical output contract regardless of which provider ran
# ------------------------------------------------------------------

def test_both_providers_produce_the_same_output_schema():
    with _Case("014") as case:
        provider, _ = _chain(
            _gemini([_gemini_submission(case.payment_reference, "Via Gemini.")]), None
        )
        via_gemini = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

    with _Case("015") as case:
        groq, _recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Via Groq."))]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        via_groq = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

    assert via_gemini.keys() == via_groq.keys() == {"investigation", "ai_result"}
    assert via_gemini["ai_result"].keys() == via_groq["ai_result"].keys()
    assert via_gemini["investigation"].keys() == via_groq["investigation"].keys()
    for key in via_gemini["ai_result"]:
        assert type(via_gemini["ai_result"][key]) is type(via_groq["ai_result"][key]), key
    # No provider identifier was bolted onto the public contract.
    assert "provider" not in via_groq["ai_result"]
    assert "provider" not in via_groq["investigation"]


# ------------------------------------------------------------------
# 9. Human-review workflow is untouched by the fallback
# ------------------------------------------------------------------

def test_human_review_workflow_unchanged_after_fallback():
    with _Case("016") as case:
        assert case.row("human_decision") is None

        groq, _recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq ran it."))]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)

        # The AI still only ever recommends; it never decides. The
        # resolve/escalate gate keys off exactly this value.
        assert case.row("recommendation") == "HUMAN_REVIEW"
        assert case.row("human_decision") is None
        assert case.row("status") == "COMPLETED"


def test_escalate_still_maps_to_human_review_via_fallback():
    with _Case("017") as case:
        payload = _valid_ai_payload(case.payment_reference, "Groq escalated.")
        payload["recommendation"] = "ESCALATE"

        groq, _recorder = _groq(
            [(200, _groq_tool_call_body("submit_investigation_findings", payload))]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        result = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

        # Same mapping the Gemini path uses: the gate column says
        # HUMAN_REVIEW while the AI's literal recommendation is preserved.
        assert case.row("recommendation") == "HUMAN_REVIEW"
        assert result["ai_result"]["recommendation"] == "ESCALATE"
        assert case.row("human_decision") is None


# ------------------------------------------------------------------
# 10. Pre-existing investigation evidence is never disturbed
# ------------------------------------------------------------------

def test_existing_evidence_is_untouched_when_every_provider_fails():
    with _Case("018") as case:
        case.cur.execute(
            """
            insert into investigation_evidence
                (investigation_id, evidence_type, record_type, record_id, description)
            values (%s, 'DETERMINISTIC', 'settlement', null, 'Pre-existing deterministic row.')
            """,
            (case.investigation_id,),
        )
        case.conn.commit()

        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        groq, _recorder = _groq([(503, {"error": {"message": "busy"}})])
        provider, _sleeps = _chain(gemini, groq)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError:
            pass

        case.cur.execute(
            "select evidence_type, description from investigation_evidence "
            "where investigation_id = %s",
            (case.investigation_id,),
        )
        rows = case.cur.fetchall()
        assert rows == [("DETERMINISTIC", "Pre-existing deterministic row.")], rows


# ------------------------------------------------------------------
# 11. No credential ever reaches a response, and none is logged
# ------------------------------------------------------------------

def test_api_key_is_sent_only_as_a_groq_auth_header_and_never_returned():
    with _Case("019") as case:
        groq, recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq ran it."))]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        result = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

        request = recorder.requests[0]
        assert request.headers["Authorization"] == f"Bearer {FAKE_GROQ_KEY}"
        # ... and nowhere else: not in the body, not in the URL.
        assert FAKE_GROQ_KEY not in request.content.decode()
        assert FAKE_GROQ_KEY not in str(request.url)
        assert FAKE_GROQ_KEY not in json.dumps(result, default=str)


def test_failure_response_carries_no_credential_or_provider_internals():
    with _Case("020") as case:
        groq, _recorder = _groq(
            [(401, {"error": {"message": f"Invalid API Key: {FAKE_GROQ_KEY}"}})]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert FAKE_GROQ_KEY not in str(error)
            assert str(error) == UNAVAILABLE_MESSAGE


# ------------------------------------------------------------------
# Groq request shape + provider-level unit checks
# ------------------------------------------------------------------

def test_groq_request_uses_the_same_prompt_tools_and_schema_as_gemini():
    from app.ai.config import GROQ_MODEL, GROQ_TOOL_CHOICE
    from app.ai.investigator import SUBMIT_TOOL_NAME
    from app.ai.tools import TOOL_DEFINITIONS

    with _Case("021") as case:
        groq, recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq ran it."))]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)

        payload = recorder.payloads[0]
        assert payload["model"] == GROQ_MODEL
        assert payload["tool_choice"] == GROQ_TOOL_CHOICE
        assert str(recorder.requests[0].url).endswith("/chat/completions")

        names = [tool["function"]["name"] for tool in payload["tools"]]
        assert names == [t["name"] for t in TOOL_DEFINITIONS] + [SUBMIT_TOOL_NAME], names

        # Identical grounding: same system instructions, same known-facts
        # message, same submit schema Gemini is given.
        system = payload["messages"][0]
        assert system["role"] == "system"
        assert "LedgerLens's AI Investigator" in system["content"]
        assert "Never invent a transaction ID" in system["content"]
        assert payload["messages"][1]["role"] == "user"
        assert "KNOWN, VERIFIED FACTS" in payload["messages"][1]["content"]
        assert case.payment_reference in payload["messages"][1]["content"]

        submit_schema = payload["tools"][-1]["function"]["parameters"]
        from app.ai.schemas import AiInvestigationResult

        assert submit_schema == AiInvestigationResult.model_json_schema()


def test_groq_executes_tools_through_the_audited_dispatch():
    with _Case("022") as case:
        groq, recorder = _groq(
            [
                (
                    200,
                    _groq_tool_call_body(
                        "get_investigation_evidence", {}, call_id="gcall_tool"
                    ),
                ),
                (200, _groq_submission_body(case.payment_reference, "Groq used a tool.")),
            ]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)

        case.cur.execute(
            "select tool_name from investigation_tool_calls where investigation_id = %s",
            (case.investigation_id,),
        )
        assert case.cur.fetchall() == [("get_investigation_evidence",)]

        # The tool result was fed back in the OpenAI tool-message shape.
        second = recorder.payloads[1]["messages"]
        assert second[-1]["role"] == "tool"
        assert second[-1]["tool_call_id"] == "gcall_tool"


def test_groq_never_executes_an_unknown_tool():
    with _Case("023") as case:
        groq, _recorder = _groq(
            [
                (200, _groq_tool_call_body("drop_all_tables", {}, call_id="gcall_evil")),
                (200, _groq_submission_body(case.payment_reference, "Groq recovered.")),
            ]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)

        case.cur.execute(
            "select tool_name, result from investigation_tool_calls "
            "where investigation_id = %s",
            (case.investigation_id,),
        )
        rows = case.cur.fetchall()
        # Recorded as attempted, but rejected -- never dispatched.
        assert len(rows) == 1 and rows[0][0] == "drop_all_tables", rows
        assert "Unknown tool" in rows[0][1]["error"]


def test_groq_http_status_classification():
    """Transient statuses are retryable; everything else is not."""
    for status in (408, 429, 498, 500, 502, 503, 504):
        groq, _ = _groq([(status, {"error": {"message": "x"}})])
        try:
            groq._post(groq._client, {"model": "m"})
            raise AssertionError(f"{status} should have raised")
        except AIProviderError as error:
            assert error.retryable is True, f"{status} was not treated as transient"

    for status in (400, 401, 403, 404, 422):
        groq, _ = _groq([(status, {"error": {"message": "x"}})])
        try:
            groq._post(groq._client, {"model": "m"})
            raise AssertionError(f"{status} should have raised")
        except AIProviderError as error:
            assert error.retryable is False, f"{status} was wrongly treated as transient"


def test_groq_missing_api_key_raises_503():
    saved = os.environ.pop("GROQ_API_KEY", None)
    try:
        assert GroqProvider.is_configured() is False
        try:
            GroqProvider()._resolve_api_key()
            raise AssertionError("expected AIProviderError")
        except AIProviderError as error:
            assert error.status_code == 503
            assert "GROQ_API_KEY" in str(error)
    finally:
        if saved is not None:
            os.environ["GROQ_API_KEY"] = saved


def test_no_fallback_configured_surfaces_the_primary_error():
    """Without GROQ_API_KEY the chain must behave exactly as it did before
    Groq existed -- one retry, then the primary's own error, NOT a
    misleading 'temporarily unavailable'."""
    with _Case("024") as case:
        gemini = _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")])
        provider, sleeps = _chain(gemini, None)

        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert "Gemini provider error" in str(error)
            assert str(error) != UNAVAILABLE_MESSAGE
        assert len(sleeps) == PRIMARY_RETRY_ATTEMPTS


def test_providers_are_never_called_concurrently():
    """The fallback must not start until the primary is fully exhausted."""
    order: list[str] = []

    class _Recorder:
        def __init__(self, name, error):
            self._name = name
            self._error = error

        def run_investigation(self, **kwargs):
            order.append(self._name)
            raise self._error

    provider = FailoverProvider(
        _Recorder("gemini", AIProviderError("busy", retryable=True)),
        _Recorder("groq", AIProviderError("busy", retryable=True)),
        sleep=lambda _seconds: None,
    )
    try:
        provider.run_investigation()
        raise AssertionError("expected AIUnavailableError")
    except AIUnavailableError:
        pass

    assert order == ["gemini"] * (1 + PRIMARY_RETRY_ATTEMPTS) + ["groq"], order


def test_failover_logs_make_the_sequence_observable_without_leaking_secrets():
    import logging

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("app.ai.providers.failover")
    handler = _Capture()
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        with _Case("025") as case:
            groq, _recorder = _groq(
                [(200, _groq_submission_body(case.payment_reference, "Groq ran it."))]
            )
            provider, _ = _chain(
                _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]),
                groq,
            )
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    # The UPSTREAM status, not the 502 this API translates it into.
    assert "AI investigation: provider=gemini status=503 action=retry" in records, records
    assert "AI investigation: provider=gemini status=503 action=fallback" in records, records
    assert "AI investigation: provider=gemini retry=failed action=fallback" in records, records
    assert "AI investigation: provider=groq status=success" in records, records
    for line in records:
        assert FAKE_GROQ_KEY not in line


def test_anthropic_transient_errors_are_classified_for_failover():
    """AI_PROVIDER=anthropic must get the same retry/fallback treatment as
    gemini -- an unclassified provider would silently disable failover."""
    import anthropic

    from app.ai.providers.anthropic_provider import AnthropicProvider

    class _Messages:
        def __init__(self, error):
            self._error = error

        def create(self, **kwargs):
            raise self._error

    class _Client:
        def __init__(self, error):
            self.messages = _Messages(error)

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    transient = [
        anthropic.RateLimitError(
            "rate limited",
            response=httpx.Response(429, request=request),
            body=None,
        ),
        anthropic.APITimeoutError(request=request),
        anthropic.APIConnectionError(request=request),
        anthropic.InternalServerError(
            "overloaded", response=httpx.Response(529, request=request), body=None
        ),
    ]
    for error in transient:
        try:
            AnthropicProvider(client=_Client(error)).run_investigation(
                system_prompt="", user_message="", tool_definitions=[],
                submit_tool_name="submit", submit_tool_schema={}, dispatch={},
                cur=None, conn=None, investigation_id="x",
            )
            raise AssertionError(f"{type(error).__name__} should have raised")
        except AIProviderError as mapped:
            assert mapped.retryable is True, type(error).__name__

    permanent = anthropic.AuthenticationError(
        "bad key", response=httpx.Response(401, request=request), body=None
    )
    try:
        AnthropicProvider(client=_Client(permanent)).run_investigation(
            system_prompt="", user_message="", tool_definitions=[],
            submit_tool_name="submit", submit_tool_schema={}, dispatch={},
            cur=None, conn=None, investigation_id="x",
        )
        raise AssertionError("should have raised")
    except AIProviderError as mapped:
        assert mapped.retryable is False
        assert mapped.provider_status == 401


# ------------------------------------------------------------------
# Token budget: the request must stay inside the Groq TPM window
# ------------------------------------------------------------------

def test_groq_request_declares_a_bounded_output_allowance():
    """Groq debits TPM as prompt + max_completion_tokens, reserved up
    front. At 4096 a single turn cost 5476 of an 8000 TPM budget and the
    second turn of the tool loop was always rate-limited."""
    from app.ai.config import GROQ_MAX_COMPLETION_TOKENS, GROQ_REASONING_EFFORT

    with _Case("030") as case:
        groq, recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq ran it."))]
        )
        provider, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)

        payload = recorder.payloads[0]
        assert payload["max_completion_tokens"] == GROQ_MAX_COMPLETION_TOKENS
        assert GROQ_MAX_COMPLETION_TOKENS == 2048, (
            "the measured bound changed -- re-measure before moving it"
        )
        # Reasoning tokens bill against the same ceiling but never appear
        # in AiInvestigationResult.
        assert payload["reasoning_effort"] == GROQ_REASONING_EFFORT == "low"

        # Turn-1 debit must leave real headroom in an 8000 TPM window.
        measured_prompt_tokens = 1380  # Groq's own accounting: 5476 - 4096
        debit = measured_prompt_tokens + GROQ_MAX_COMPLETION_TOKENS
        assert debit < 4000, f"turn-1 debit {debit} leaves too little TPM headroom"


def test_output_allowance_exceeds_the_largest_realistic_result():
    """The bound must not be so tight that a full result is truncated --
    a cut-off submit call is malformed JSON and fails the fallback."""
    import json

    from app.ai.config import GROQ_MAX_COMPLETION_TOKENS

    generous = _valid_ai_payload("pay_x", "k" * 400)
    generous["evidence_reviewed"] *= 6
    generous["hypotheses"] *= 3
    generous["contradictions"] = [{"description": "d" * 300}]
    # ~4 chars/token is the conservative direction for o200k on JSON.
    approx_tokens = len(json.dumps(generous)) / 4
    assert GROQ_MAX_COMPLETION_TOKENS > approx_tokens * 1.5, (
        f"only {GROQ_MAX_COMPLETION_TOKENS} tokens for a ~{approx_tokens:.0f}-token result"
    )


# ------------------------------------------------------------------
# 429 classification and provider-directed Retry-After
# ------------------------------------------------------------------

def test_groq_429_is_transient_and_carries_retry_after():
    groq, _ = _groq(
        [(429, {"error": {"code": "rate_limit_exceeded", "type": "tokens"}},
          {"retry-after": "21"})]
    )
    try:
        groq._post(groq._client, {"model": "m"})
        raise AssertionError("expected AIProviderError")
    except AIProviderError as error:
        assert error.retryable is True
        assert error.provider_status == 429
        assert error.retry_after == 21.0


def test_unparseable_retry_after_never_becomes_a_wait():
    for header in ({"retry-after": "Tue, 01 Sep 2026 12:00:00 GMT"}, {}, {"retry-after": "-3"}):
        groq, _ = _groq([(429, {"error": {"message": "slow down"}}, header)])
        try:
            groq._post(groq._client, {"model": "m"})
            raise AssertionError("expected AIProviderError")
        except AIProviderError as error:
            assert error.retry_after is None, header


def test_short_retry_after_is_honoured_exactly_once():
    with _Case("031") as case:
        groq, recorder = _groq(
            [
                (429, {"error": {"message": "tpm"}}, {"retry-after": "2"}),
                (200, _groq_submission_body(case.payment_reference, "Groq after waiting.")),
            ]
        )
        provider, sleeps = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        result = run_ai_investigation(
            case.investigation_id, case.exception_id, provider=provider
        )

        assert recorder.call_count == 2, "the fallback did not retry exactly once"
        assert 2.0 in sleeps, f"the provider's own delay was not used: {sleeps}"
        assert (
            result["ai_result"]["root_cause_assessment"]["known"] == "Groq after waiting."
        )


def test_long_retry_after_is_refused_and_fails_fast():
    """Free-tier Groq advertises ~21s. Waiting that out after two Gemini
    attempts would risk a gateway timeout, so it must fail fast."""
    with _Case("032") as case:
        groq, recorder = _groq(
            [(429, {"error": {"message": "tpm"}}, {"retry-after": "21"})]
        )
        provider, sleeps = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        try:
            run_ai_investigation(case.investigation_id, case.exception_id, provider=provider)
            raise AssertionError("expected AiInvestigationError")
        except AiInvestigationError as error:
            assert str(error) == UNAVAILABLE_MESSAGE

        assert recorder.call_count == 1, "waited out a delay that was too long"
        assert 21.0 not in sleeps
        assert case.row("confidence") is None


def test_retry_after_is_refused_when_the_time_budget_is_spent():
    """Even a short delay is refused if the chain has already used its
    budget -- the deadline, not just the cap, gates the wait."""
    from app.ai.providers.failover import FailoverProvider

    calls = {"n": 0}

    class _Groq429:
        def run_investigation(self, **kw):
            calls["n"] += 1
            raise AIProviderError("Groq returned 429", retryable=True,
                                  provider_status=429, retry_after=2.0)

    class _Boom:
        def run_investigation(self, **kw):
            raise AIProviderError("busy", retryable=True, provider_status=503)

    now = [0.0]
    provider = FailoverProvider(
        _Boom(), _Groq429(), sleep=lambda s: None,
        clock=lambda: now[0],
    )
    # Jump the clock past the budget while the primary is being attempted.
    original = provider._run_primary
    def _advance(**kwargs):
        now[0] = 10_000.0
        return original(**kwargs)
    provider._run_primary = _advance

    try:
        provider.run_investigation()
        raise AssertionError("expected AIUnavailableError")
    except AIUnavailableError:
        pass
    assert calls["n"] == 1, "retried despite the time budget being exhausted"


# ------------------------------------------------------------------
# Route level: what the FRONTEND actually receives
# ------------------------------------------------------------------

def _route_client():
    """The AI route is authenticated; override the dependency rather than
    creating a throwaway user, so no permanent QA account is left behind."""
    from fastapi.testclient import TestClient

    from app.auth.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "id": "00000000-0000-0000-0000-000000000000",
        "email": "route-test@example.com",
        "role": "ANALYST",
    }
    return TestClient(app), app


def test_route_returns_clean_503_with_no_provider_internals():
    """The end the user sees: AiInvestigationCard renders the API's
    `detail` verbatim, so `detail` must be the clean message and nothing
    else."""
    import app.ai.investigator as investigator_module

    client, fastapi_app = _route_client()
    with _Case("026") as case:
        groq, _recorder = _groq([(503, {"error": {"message": "Groq over capacity"}})])
        chain, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        original = investigator_module._build_provider
        investigator_module._build_provider = lambda: chain
        try:
            response = client.post(
                f"/investigations/{case.investigation_id}/ai-investigate"
            )
        finally:
            investigator_module._build_provider = original
            fastapi_app.dependency_overrides.clear()

        assert response.status_code == 503, response.status_code
        detail = response.json()["detail"]
        assert detail == UNAVAILABLE_MESSAGE, detail
        for leak in ("Gemini", "Groq", "UNAVAILABLE", "over capacity", "Traceback"):
            assert leak not in response.text, f"leaked {leak!r} to the browser"


def test_route_returns_the_same_investigation_shape_after_a_groq_fallback():
    """5. The investigation page still renders normally: the route's
    success payload is the same object the Gemini path returns."""
    import app.ai.investigator as investigator_module

    client, fastapi_app = _route_client()
    with _Case("027") as case:
        groq, _recorder = _groq(
            [(200, _groq_submission_body(case.payment_reference, "Groq ran it."))]
        )
        chain, _ = _chain(
            _gemini([_server_error(503, "UNAVAILABLE"), _server_error(503, "UNAVAILABLE")]), groq
        )
        original = investigator_module._build_provider
        investigator_module._build_provider = lambda: chain
        try:
            response = client.post(
                f"/investigations/{case.investigation_id}/ai-investigate"
            )
        finally:
            investigator_module._build_provider = original

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["recommendation"] == "HUMAN_REVIEW"
        # Serialized as a string by investigation_store, exactly as the
        # Gemini path already produces (Decimal -> str, scale preserved).
        assert body["confidence"] == "58.00", body["confidence"]
        assert body["root_cause_assessment"]["known"] == "Groq ran it."
        assert body["human_decision"] is None
        # The full contract the frontend maps from -- unchanged by failover.
        assert set(body) == {
            "id", "exception_id", "exception_code", "category", "description",
            "financial_impact", "root_cause", "confidence", "recommendation",
            "status", "financial_analysis", "started_at", "completed_at",
            "human_decision", "root_cause_assessment",
        }, sorted(body)

        # 6. Review & Decide is unaffected: the evidence, hypotheses and
        # tool-call feeds the drawer reads still respond normally.
        for suffix in ("evidence", "hypotheses", "tool-calls", "contradictions"):
            feed = client.get(f"/investigations/{case.investigation_id}/{suffix}")
            assert feed.status_code == 200, (suffix, feed.text)
            assert isinstance(feed.json(), list), suffix

        fastapi_app.dependency_overrides.clear()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
