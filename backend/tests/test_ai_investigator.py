"""DB-integration + mocked-Anthropic checks for the AI Investigator.
No live Anthropic API call is ever made -- every test either calls a
pure function directly or injects a FakeAnthropicClient via
run_ai_investigation's `client=` parameter. Throwaway TEST-AI-* rows
only; cleans up after itself (investigation_evidence/hypotheses/
contradictions/tool_calls cascade-delete with their investigation).

Run directly: python backend/tests/test_ai_investigator.py
"""

import os
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic
import psycopg
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.investigator import (
    AiInvestigationError,
    _map_recommendation,
    _validate_financial_values,
    run_ai_investigation,
)
from app.ai.schemas import AiInvestigationResult
from app.ai.tools import build_tool_dispatch, execute_tool
from app.auth.security import hash_password
from app.investigation.runners.deterministic import connect
from app.investigation.services.investigation_store import get_investigation
from app.main import app


# ------------------------------------------------------------------
# Fixtures / helpers
# ------------------------------------------------------------------

FINANCIAL_ANALYSIS = {
    "gross_amount": "1700.00",
    "fee_amount": "50.00",
    "tax_amount": "6.95",
    "adjustment_amount": "0.00",
    "expected_amount": "1643.05",
    "observed_amount": "1063.73",
    "difference": "579.32",
}


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


def _insert_investigation(
    cur,
    exception_id: str,
    status: str = "COMPLETED",
    recommendation: str = "HUMAN_REVIEW",
    financial_analysis: dict | None = FINANCIAL_ANALYSIS,
) -> str:
    cur.execute(
        """
        insert into investigations (
            exception_id, status, recommendation, financial_analysis, completed_at
        )
        values (%s, %s, %s, %s, now())
        returning id
        """,
        (
            exception_id,
            status,
            recommendation,
            psycopg.types.json.Jsonb(financial_analysis) if financial_analysis else None,
        ),
    )
    return str(cur.fetchone()[0])


def _cleanup(cur, conn, exception_id: str) -> None:
    cur.execute("delete from investigations where exception_id = %s", (exception_id,))
    cur.execute("delete from exceptions where id = %s", (exception_id,))
    conn.commit()


def _insert_payment(cur, payment_ref: str, amount: str = "1700.00") -> str:
    cur.execute(
        "insert into payments (external_payment_id, amount, currency, status, method) "
        "values (%s, %s, 'INR', 'captured', 'card') returning id",
        (payment_ref, amount),
    )
    return str(cur.fetchone()[0])


def _cleanup_payment(cur, conn, payment_id: str) -> None:
    cur.execute("delete from payments where id = %s", (payment_id,))
    conn.commit()


def _tool_use(id_: str, name: str, input_: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def _valid_ai_payload(payment_reference: str, exception_code: str = "EX01") -> dict:
    return {
        "summary": {
            "exception_code": exception_code,
            "payment_reference": payment_reference,
            "financial_gap": "579.32",
        },
        "financial_analysis": {
            "expected_amount": "1643.05",
            "observed_amount": "1063.73",
            "difference": "579.32",
        },
        "evidence_reviewed": [
            {"record_type": "settlement", "record_id": None, "summary": "Settlement checked."}
        ],
        "hypotheses": [
            {
                "title": "Settlement amount is short of the expected net payout.",
                "status": "SUPPORTED",
                "confidence": 82,
                "supporting_evidence": ["Expected 1643.05, observed 1063.73"],
                "contradicting_evidence": [],
            }
        ],
        "contradictions": [],
        "root_cause_assessment": {
            "known": "The observed settlement is 579.32 less than the expected net amount.",
            "likely": "An additional deduction not captured in fees/tax/adjustments.",
            "not_proven": "The exact source of the remaining 579.32 cannot be confirmed from available records.",
        },
        "confidence": 60,
        "recommendation": "HUMAN_REVIEW",
    }


class FakeMessagesResource:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessagesResource exhausted -- too many model turns")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeAnthropicClient:
    def __init__(self, responses: list):
        self.messages = FakeMessagesResource(responses)


def _fake_message(stop_reason: str, content: list) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def _happy_path_client(payment_reference: str, exception_code: str = "EX01") -> FakeAnthropicClient:
    return FakeAnthropicClient(
        [
            _fake_message(
                "tool_use",
                [_tool_use("t1", "get_payment", {"payment_reference": payment_reference})],
            ),
            _fake_message(
                "tool_use",
                [
                    _tool_use(
                        "t2",
                        "submit_investigation_findings",
                        _valid_ai_payload(payment_reference, exception_code),
                    )
                ],
            ),
        ]
    )


# ------------------------------------------------------------------
# Tool wrappers -- correct retrieval against real throwaway rows
# ------------------------------------------------------------------

def test_tool_wrappers_retrieve_payment_settlements_fees_taxes():
    payment_ref = "TEST-AI-TOOLS-001"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into payments (external_payment_id, amount, currency, status, method) "
                "values (%s, 1700.00, 'INR', 'captured', 'card') returning id",
                (payment_ref,),
            )
            payment_id = str(cur.fetchone()[0])
            cur.execute(
                "insert into settlements (external_settlement_id, settlement_amount, currency, status, settlement_date, reference) "
                "values ('TEST-AI-TOOLS-SETL', 1063.73, 'INR', 'SETTLED', now(), %s) returning id",
                (payment_ref,),
            )
            settlement_id = str(cur.fetchone()[0])
            cur.execute(
                "insert into fees (settlement_id, amount, currency, fee_type) values (%s, 50.00, 'INR', 'RAZORPAY_FEE')",
                (settlement_id,),
            )
            cur.execute(
                "insert into taxes (settlement_id, amount, currency, tax_type) values (%s, 6.95, 'INR', 'GST')",
                (settlement_id,),
            )
            conn.commit()

            try:
                dispatch = build_tool_dispatch(cur, "unused-investigation-id", "unused-exception-id")

                payment = dispatch["get_payment"]({"payment_reference": payment_ref})
                assert payment["external_payment_id"] == payment_ref
                assert payment["amount"] == "1700.00"

                settlements = dispatch["get_settlements"]({"payment_reference": payment_ref})
                assert len(settlements) == 1
                assert settlements[0]["external_settlement_id"] == "TEST-AI-TOOLS-SETL"

                fees = dispatch["get_fees"]({"settlement_id": settlement_id})
                assert len(fees) == 1 and fees[0]["amount"] == "50.00"

                taxes = dispatch["get_taxes"]({"settlement_id": settlement_id})
                assert len(taxes) == 1 and taxes[0]["amount"] == "6.95"
            finally:
                cur.execute("delete from fees where settlement_id = %s", (settlement_id,))
                cur.execute("delete from taxes where settlement_id = %s", (settlement_id,))
                cur.execute("delete from settlements where id = %s", (settlement_id,))
                cur.execute("delete from payments where id = %s", (payment_id,))
                conn.commit()


def test_tool_wrapper_retrieves_all_duplicate_settlements_not_just_two():
    payment_ref = "TEST-AI-TOOLS-DUP"
    settlement_refs = ["TEST-AI-DUP-A", "TEST-AI-DUP-B", "TEST-AI-DUP-C"]
    with connect() as conn:
        with conn.cursor() as cur:
            for ref in settlement_refs:
                cur.execute(
                    "insert into settlements (external_settlement_id, settlement_amount, currency, status, settlement_date, reference) "
                    "values (%s, 500.00, 'INR', 'SETTLED', now(), %s)",
                    (ref, payment_ref),
                )
            conn.commit()

            try:
                dispatch = build_tool_dispatch(cur, "unused-investigation-id", "unused-exception-id")
                settlements = dispatch["get_settlements"]({"payment_reference": payment_ref})
                assert len(settlements) == 3
                assert {s["external_settlement_id"] for s in settlements} == set(settlement_refs)
            finally:
                cur.execute(
                    "delete from settlements where external_settlement_id = any(%s)",
                    (settlement_refs,),
                )
                conn.commit()


# ------------------------------------------------------------------
# Structured output validation
# ------------------------------------------------------------------

def test_valid_ai_response_is_accepted():
    payload = _valid_ai_payload("pay_test123")
    result = AiInvestigationResult.model_validate(payload)
    assert result.recommendation == "HUMAN_REVIEW"
    assert result.hypotheses[0].status == "SUPPORTED"


def test_malformed_ai_response_is_rejected():
    payload = _valid_ai_payload("pay_test123")
    del payload["root_cause_assessment"]
    try:
        AiInvestigationResult.model_validate(payload)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_invalid_recommendation_is_rejected():
    payload = _valid_ai_payload("pay_test123")
    payload["recommendation"] = "MAYBE"
    try:
        AiInvestigationResult.model_validate(payload)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_invalid_hypothesis_status_is_rejected():
    payload = _valid_ai_payload("pay_test123")
    payload["hypotheses"][0]["status"] = "MAYBE"
    try:
        AiInvestigationResult.model_validate(payload)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


# ------------------------------------------------------------------
# Financial safety
# ------------------------------------------------------------------

def _fake_investigation(exception_code="EX01") -> dict:
    return {"exception_code": exception_code, "financial_analysis": FINANCIAL_ANALYSIS}


def test_matching_financial_values_are_accepted():
    result = AiInvestigationResult.model_validate(_valid_ai_payload("pay_ok"))
    _validate_financial_values(result, _fake_investigation(), "pay_ok")  # must not raise


def test_fabricated_expected_amount_is_rejected():
    payload = _valid_ai_payload("pay_ok")
    payload["financial_analysis"]["expected_amount"] = "1600.00"
    result = AiInvestigationResult.model_validate(payload)
    try:
        _validate_financial_values(result, _fake_investigation(), "pay_ok")
        raise AssertionError("expected AiInvestigationError")
    except AiInvestigationError:
        pass


def test_mismatched_observed_amount_is_rejected():
    payload = _valid_ai_payload("pay_ok")
    payload["financial_analysis"]["observed_amount"] = "999.99"
    result = AiInvestigationResult.model_validate(payload)
    try:
        _validate_financial_values(result, _fake_investigation(), "pay_ok")
        raise AssertionError("expected AiInvestigationError")
    except AiInvestigationError:
        pass


def test_mismatched_difference_is_rejected():
    payload = _valid_ai_payload("pay_ok")
    payload["financial_analysis"]["difference"] = "1.00"
    result = AiInvestigationResult.model_validate(payload)
    try:
        _validate_financial_values(result, _fake_investigation(), "pay_ok")
        raise AssertionError("expected AiInvestigationError")
    except AiInvestigationError:
        pass


def test_mismatched_payment_reference_is_rejected():
    result = AiInvestigationResult.model_validate(_valid_ai_payload("pay_wrong"))
    try:
        _validate_financial_values(result, _fake_investigation(), "pay_correct")
        raise AssertionError("expected AiInvestigationError")
    except AiInvestigationError:
        pass


def test_mismatched_exception_code_is_rejected():
    result = AiInvestigationResult.model_validate(_valid_ai_payload("pay_ok", exception_code="EX02"))
    try:
        _validate_financial_values(result, _fake_investigation("EX01"), "pay_ok")
        raise AssertionError("expected AiInvestigationError")
    except AiInvestigationError:
        pass


def test_recommendation_mapping_preserves_gate_contract():
    assert _map_recommendation("NO_ACTION") == "NO_ACTION"
    assert _map_recommendation("HUMAN_REVIEW") == "HUMAN_REVIEW"
    # ESCALATE must map onto the one value _assert_eligible_for_human_decision
    # (resolution.py) actually understands -- never the literal "ESCALATE".
    assert _map_recommendation("ESCALATE") == "HUMAN_REVIEW"


# ------------------------------------------------------------------
# End-to-end with a fake Anthropic client (no live API calls)
# ------------------------------------------------------------------

def test_end_to_end_happy_path_persists_results_and_records_tool_calls():
    payment_ref = "pay_testaie2e001"
    with connect() as conn:
        with conn.cursor() as cur:
            payment_id = _insert_payment(cur, payment_ref)
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                fake_client = _happy_path_client(payment_ref)
                result = run_ai_investigation(investigation_id, exception_id, client=fake_client)

                updated = result["investigation"]
                assert updated["root_cause_assessment"] is not None
                assert updated["root_cause_assessment"]["known"].startswith("The observed settlement")
                assert updated["recommendation"] == "HUMAN_REVIEW"
                assert Decimal(updated["confidence"]) == Decimal("60")
                # AI never touches these -- Human Review remains untouched.
                assert updated["human_decision"] is None
                assert updated["status"] == "COMPLETED"

                cur.execute(
                    "select tool_name, result from investigation_tool_calls where investigation_id = %s order by called_at",
                    (investigation_id,),
                )
                rows = cur.fetchall()
                tool_names = [row[0] for row in rows]
                assert "get_payment" in tool_names
                get_payment_result = next(r[1] for r in rows if r[0] == "get_payment")
                assert "error" not in get_payment_result  # the tool call actually succeeded

                cur.execute(
                    "select evidence_type from investigation_evidence where investigation_id = %s",
                    (investigation_id,),
                )
                evidence_types = {row[0] for row in cur.fetchall()}
                assert evidence_types == {"AI_ANALYSIS"}

                cur.execute(
                    "select status from exceptions where id = %s", (exception_id,)
                )
                assert cur.fetchone()[0] == "OPEN"  # AI never resolves the exception
            finally:
                _cleanup(cur, conn, exception_id)
                _cleanup_payment(cur, conn, payment_id)


def test_no_partial_persistence_on_financial_mismatch_but_tool_calls_survive():
    payment_ref = "pay_testaie2e002"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                bad_payload = _valid_ai_payload(payment_ref)
                bad_payload["financial_analysis"]["expected_amount"] = "1.00"  # fabricated
                fake_client = FakeAnthropicClient(
                    [
                        _fake_message(
                            "tool_use",
                            [_tool_use("t1", "get_payment", {"payment_reference": payment_ref})],
                        ),
                        _fake_message(
                            "tool_use",
                            [_tool_use("t2", "submit_investigation_findings", bad_payload)],
                        ),
                    ]
                )

                try:
                    run_ai_investigation(investigation_id, exception_id, client=fake_client)
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass

                # The tool call that happened before the failure survives --
                # it's a real read that occurred, and is legitimate audit trail.
                cur.execute(
                    "select count(*) from investigation_tool_calls where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 1

                # But nothing from the rejected final response was persisted.
                cur.execute(
                    "select count(*) from investigation_evidence where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 0

                updated = get_investigation(cur, investigation_id)
                assert updated["root_cause_assessment"] is None
                assert updated["recommendation"] == "HUMAN_REVIEW"  # untouched, original value
                assert updated["human_decision"] is None
            finally:
                _cleanup(cur, conn, exception_id)


def test_api_timeout_raises_ai_investigation_error_without_persisting():
    payment_ref = "pay_testaie2e003"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                timeout_error = anthropic.APITimeoutError(request=SimpleNamespace())
                fake_client = FakeAnthropicClient([timeout_error])

                try:
                    run_ai_investigation(investigation_id, exception_id, client=fake_client)
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass

                cur.execute(
                    "select count(*) from investigation_tool_calls where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 0
                cur.execute(
                    "select count(*) from investigation_evidence where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 0
            finally:
                _cleanup(cur, conn, exception_id)


def test_model_response_without_tool_use_raises_ai_investigation_error():
    payment_ref = "pay_testaie2e004"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                fake_client = FakeAnthropicClient(
                    [_fake_message("end_turn", [SimpleNamespace(type="text", text="I'm not sure.")])]
                )
                try:
                    run_ai_investigation(investigation_id, exception_id, client=fake_client)
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass
            finally:
                _cleanup(cur, conn, exception_id)


def test_requires_deterministic_financial_analysis_first():
    payment_ref = "pay_testaie2e005"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id, financial_analysis=None)
            conn.commit()

            try:
                try:
                    run_ai_investigation(investigation_id, exception_id, client=FakeAnthropicClient([]))
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError as error:
                    assert error.status_code == 400
            finally:
                _cleanup(cur, conn, exception_id)


def test_requires_human_review_recommendation():
    payment_ref = "pay_testaie2e006"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id, recommendation="NO_ACTION")
            conn.commit()

            try:
                try:
                    run_ai_investigation(investigation_id, exception_id, client=FakeAnthropicClient([]))
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError as error:
                    assert error.status_code == 400
            finally:
                _cleanup(cur, conn, exception_id)


# ------------------------------------------------------------------
# Authentication / authorization at the HTTP layer
#
# No ANTHROPIC_API_KEY is set in this environment, so an authenticated
# request always reaches run_ai_investigation's own 503 (misconfigured)
# rather than a live call -- that 503 (not a 401/403) is exactly what
# proves the request got PAST auth and role checks: only an
# authenticated Analyst-or-Reviewer can reach the point of failing on
# a missing API key at all.
# ------------------------------------------------------------------

class _no_provider_key:
    """Temporarily hides whichever provider key is actually configured
    in this environment (this repo's .env may have a real
    GEMINI_API_KEY -- see the Phase 3 report), forcing a deterministic
    "not configured" 503 without ever making a live API call."""

    _NAMES = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY")

    def __enter__(self):
        self._saved = {name: os.environ.pop(name, None) for name in self._NAMES}
        return self

    def __exit__(self, *exc_info):
        for name, value in self._saved.items():
            if value is not None:
                os.environ[name] = value


def _create_user(cur, email: str, role: str, password: str) -> str:
    salt, password_hash = hash_password(password)
    cur.execute(
        "insert into users (email, password_hash, password_salt, role) "
        "values (%s, %s, %s, %s) returning id",
        (email, password_hash, salt, role),
    )
    return str(cur.fetchone()[0])


def test_ai_investigate_requires_authentication():
    payment_ref = "pay_testaiauth001"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                client = TestClient(app)
                response = client.post(f"/investigations/{investigation_id}/ai-investigate")
                assert response.status_code == 401
            finally:
                _cleanup(cur, conn, exception_id)


def test_analyst_can_trigger_ai_investigation_endpoint():
    payment_ref = "pay_testaiauth002"
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, "test-ai-analyst@ledgerlens.dev", "analyst", "Test-Pw-1")
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                client = TestClient(app)
                client.post(
                    "/auth/login",
                    json={"email": "test-ai-analyst@ledgerlens.dev", "password": "Test-Pw-1"},
                )
                with _no_provider_key():
                    response = client.post(f"/investigations/{investigation_id}/ai-investigate")
                # Not 401 (authenticated) and not 403 (Analyst is allowed to run
                # AI investigation, unlike resolve/escalate) -- 503 because no
                # provider key is configured for the duration of this request.
                assert response.status_code == 503
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                _cleanup(cur, conn, exception_id)


def test_reviewer_can_trigger_ai_investigation_endpoint():
    payment_ref = "pay_testaiauth003"
    with connect() as conn:
        with conn.cursor() as cur:
            user_id = _create_user(cur, "test-ai-reviewer@ledgerlens.dev", "reviewer", "Test-Pw-1")
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                client = TestClient(app)
                client.post(
                    "/auth/login",
                    json={"email": "test-ai-reviewer@ledgerlens.dev", "password": "Test-Pw-1"},
                )
                with _no_provider_key():
                    response = client.post(f"/investigations/{investigation_id}/ai-investigate")
                assert response.status_code == 503
            finally:
                cur.execute("delete from sessions where user_id = %s", (user_id,))
                cur.execute("delete from users where id = %s", (user_id,))
                _cleanup(cur, conn, exception_id)


def test_ai_investigation_cannot_resolve_or_escalate():
    """Structural guarantee, not just a happy-path observation: run a
    full successful AI investigation and confirm exceptions.status and
    investigations.human_decision -- the only two fields Human Review
    owns -- are untouched. Resolve/escalate stay reviewer-only actions
    the AI never performs itself."""
    payment_ref = "pay_testaiauth004"
    with connect() as conn:
        with conn.cursor() as cur:
            payment_id = _insert_payment(cur, payment_ref)
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                run_ai_investigation(
                    investigation_id, exception_id, client=_happy_path_client(payment_ref)
                )

                cur.execute("select status from exceptions where id = %s", (exception_id,))
                assert cur.fetchone()[0] == "OPEN"

                updated = get_investigation(cur, investigation_id)
                assert updated["human_decision"] is None
                assert updated["status"] == "COMPLETED"  # unchanged from the deterministic pass
            finally:
                _cleanup(cur, conn, exception_id)
                _cleanup_payment(cur, conn, payment_id)


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
