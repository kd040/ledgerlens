"""Mocked-Gemini checks for the AI Investigator's Gemini provider
(backend/app/ai/providers/gemini_provider.py). No live Gemini API call
is made anywhere in this file -- every test injects a FakeGeminiClient
via GeminiProvider(client=...) / run_ai_investigation(provider=...).
Throwaway TEST-GEMINI-* rows only; cleans up after itself.

A live check against the real, configured GEMINI_API_KEY -- when one
is present -- is run separately (see the Phase 3 report); it is
intentionally NOT part of this file, so the normal test suite never
needs a live key.

Run directly: python backend/tests/test_gemini_provider.py
"""

import os
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from google.genai import errors as genai_errors
from google.genai import types

from app.ai.investigator import AiInvestigationError, run_ai_investigation
from app.ai.providers.base import AIProviderError
from app.ai.providers.gemini_provider import GeminiProvider
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
    financial_analysis: dict | None = FINANCIAL_ANALYSIS,
    recommendation: str = "HUMAN_REVIEW",
) -> str:
    cur.execute(
        """
        insert into investigations (
            exception_id, status, recommendation, financial_analysis, completed_at
        )
        values (%s, 'COMPLETED', %s, %s, now())
        returning id
        """,
        (
            exception_id,
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
            {"record_type": "payment", "record_id": None, "summary": "Payment checked."}
        ],
        "hypotheses": [
            {
                "title": "Settlement amount is short of the expected net payout.",
                "status": "SUPPORTED",
                "confidence": 75,
                "supporting_evidence": ["Expected 1643.05, observed 1063.73"],
                "contradicting_evidence": [],
            }
        ],
        "contradictions": [],
        "root_cause_assessment": {
            "known": "The observed settlement is 579.32 less than the expected net amount.",
            "likely": "An additional deduction not fully captured in fees/tax/adjustments.",
            "not_proven": "The exact source of the remaining difference cannot be confirmed.",
        },
        "confidence": 58,
        "recommendation": "HUMAN_REVIEW",
    }


# ------------------------------------------------------------------
# Fake google-genai client -- mirrors client.models.generate_content(...)
# ------------------------------------------------------------------

def _function_call_part(name: str, args: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        function_call=SimpleNamespace(name=name, args=args, id=call_id), text=None
    )


def _text_only_part(text: str):
    return SimpleNamespace(function_call=None, text=text)


def _gemini_response(parts: list, finish_reason=types.FinishReason.STOP):
    content = SimpleNamespace(parts=parts)
    candidate = SimpleNamespace(content=content, finish_reason=finish_reason)
    return SimpleNamespace(candidates=[candidate])


class FakeGeminiModels:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if not self._responses:
            raise AssertionError("FakeGeminiModels exhausted -- too many model turns")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeGeminiClient:
    def __init__(self, responses: list):
        self.models = FakeGeminiModels(responses)


def _happy_path_client(payment_reference: str, exception_code: str = "EX01") -> FakeGeminiClient:
    return FakeGeminiClient(
        [
            _gemini_response(
                [_function_call_part("get_payment", {"payment_reference": payment_reference}, "c1")]
            ),
            _gemini_response(
                [
                    _function_call_part(
                        "submit_investigation_findings",
                        _valid_ai_payload(payment_reference, exception_code),
                        "c2",
                    )
                ]
            ),
        ]
    )


# ------------------------------------------------------------------
# 1. Provider initialization
# ------------------------------------------------------------------

def test_gemini_provider_initializes_with_default_model():
    provider = GeminiProvider()
    assert provider._model  # picks up config.GEMINI_MODEL, never empty


def test_gemini_provider_accepts_explicit_model_override():
    provider = GeminiProvider(model="gemini-flash-lite-latest")
    assert provider._model == "gemini-flash-lite-latest"


# ------------------------------------------------------------------
# 2. Missing key
# ------------------------------------------------------------------

def test_gemini_missing_api_key_raises_503():
    saved = os.environ.pop("GEMINI_API_KEY", None)
    try:
        provider = GeminiProvider()
        try:
            provider._build_client()
            raise AssertionError("expected AIProviderError")
        except AIProviderError as error:
            assert error.status_code == 503
    finally:
        if saved is not None:
            os.environ["GEMINI_API_KEY"] = saved


# ------------------------------------------------------------------
# 3/4/5/6. Function-call conversion, tool execution, sequential calls,
#          final structured output -- one full happy-path run.
# ------------------------------------------------------------------

def test_end_to_end_happy_path_with_sequential_tool_calls():
    payment_ref = "pay_testgemini001"
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
                result = run_ai_investigation(
                    investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                )

                updated = result["investigation"]
                assert updated["root_cause_assessment"] is not None
                assert updated["recommendation"] == "HUMAN_REVIEW"
                assert Decimal(updated["confidence"]) == Decimal("58")

                # Function-call conversion: the fake client actually received
                # FunctionDeclaration-based tools built from TOOL_DEFINITIONS.
                first_call = fake_client.models.calls[0]
                tool_names = {
                    decl.name for decl in first_call["config"].tools[0].function_declarations
                }
                assert "get_payment" in tool_names
                assert "submit_investigation_findings" in tool_names

                cur.execute(
                    "select tool_name, result from investigation_tool_calls "
                    "where investigation_id = %s order by called_at",
                    (investigation_id,),
                )
                rows = cur.fetchall()
                assert [r[0] for r in rows] == ["get_payment"]
                assert "error" not in rows[0][1]  # tool execution actually succeeded

                cur.execute(
                    "select evidence_type from investigation_evidence where investigation_id = %s",
                    (investigation_id,),
                )
                assert {r[0] for r in cur.fetchall()} == {"AI_ANALYSIS"}
            finally:
                _cleanup(cur, conn, exception_id)
                _cleanup_payment(cur, conn, payment_id)


# ------------------------------------------------------------------
# 7/8/9. Malformed structured output / invalid hypothesis status /
#        invalid recommendation -- rejected, nothing persisted.
# ------------------------------------------------------------------

def test_malformed_structured_output_is_rejected():
    payment_ref = "pay_testgemini002"
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
                del bad_payload["root_cause_assessment"]
                fake_client = FakeGeminiClient(
                    [
                        _gemini_response(
                            [_function_call_part("submit_investigation_findings", bad_payload)]
                        )
                    ]
                )
                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass

                cur.execute(
                    "select count(*) from investigation_evidence where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 0
            finally:
                _cleanup(cur, conn, exception_id)


def test_invalid_hypothesis_status_is_rejected():
    payment_ref = "pay_testgemini003"
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
                bad_payload["hypotheses"][0]["status"] = "MAYBE"
                fake_client = FakeGeminiClient(
                    [
                        _gemini_response(
                            [_function_call_part("submit_investigation_findings", bad_payload)]
                        )
                    ]
                )
                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass
            finally:
                _cleanup(cur, conn, exception_id)


def test_invalid_recommendation_is_rejected():
    payment_ref = "pay_testgemini004"
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
                bad_payload["recommendation"] = "MAYBE"
                fake_client = FakeGeminiClient(
                    [
                        _gemini_response(
                            [_function_call_part("submit_investigation_findings", bad_payload)]
                        )
                    ]
                )
                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass
            finally:
                _cleanup(cur, conn, exception_id)


# ------------------------------------------------------------------
# 10. Financial-value mismatch
# ------------------------------------------------------------------

def test_financial_value_mismatch_is_rejected():
    payment_ref = "pay_testgemini005"
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
                fake_client = FakeGeminiClient(
                    [
                        _gemini_response(
                            [_function_call_part("submit_investigation_findings", bad_payload)]
                        )
                    ]
                )
                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass

                cur.execute(
                    "select count(*) from investigation_evidence where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 0
            finally:
                _cleanup(cur, conn, exception_id)


# ------------------------------------------------------------------
# 11. Unknown tool -- recorded as a failed attempt, never executed
# ------------------------------------------------------------------

def test_unknown_tool_is_never_executed_but_is_recorded():
    payment_ref = "pay_testgemini006"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                fake_client = FakeGeminiClient(
                    [
                        _gemini_response(
                            [_function_call_part("delete_all_payments", {"confirm": True}, "c1")]
                        ),
                        _gemini_response(
                            [
                                _function_call_part(
                                    "submit_investigation_findings",
                                    _valid_ai_payload(payment_ref),
                                    "c2",
                                )
                            ]
                        ),
                    ]
                )
                result = run_ai_investigation(
                    investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                )
                assert result["investigation"]["recommendation"] == "HUMAN_REVIEW"

                cur.execute(
                    "select tool_name, result from investigation_tool_calls "
                    "where investigation_id = %s",
                    (investigation_id,),
                )
                rows = cur.fetchall()
                assert rows[0][0] == "delete_all_payments"
                assert "Unknown tool" in rows[0][1]["error"]
            finally:
                _cleanup(cur, conn, exception_id)


# ------------------------------------------------------------------
# 12. Tool-call limit -- fails safely, nothing persisted
# ------------------------------------------------------------------

def test_tool_call_round_limit_fails_safely_without_persisting():
    payment_ref = "pay_testgemini007"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                # Never submits -- one more response than MAX_TOOL_TURNS (12),
                # so the round limit trips before the fake client is exhausted.
                never_submits = [
                    _gemini_response(
                        [_function_call_part("get_payment", {"payment_reference": payment_ref}, f"c{i}")]
                    )
                    for i in range(13)
                ]
                fake_client = FakeGeminiClient(never_submits)

                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError as error:
                    assert "tool-call turns" in str(error)

                # Tool-call audit rows from the attempted turns remain (real
                # reads that happened); nothing else was persisted.
                cur.execute(
                    "select count(*) from investigation_tool_calls where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 12  # exactly MAX_TOOL_TURNS attempts

                cur.execute(
                    "select count(*) from investigation_evidence where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 0
            finally:
                _cleanup(cur, conn, exception_id)


def test_total_tool_call_limit_trips_before_round_limit():
    payment_ref = "pay_testgemini008"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                # 3 parallel tool calls per turn; MAX_TOTAL_TOOL_CALLS is 20,
                # so this trips on turn 7 (21 total) -- well before the
                # MAX_TOOL_TURNS=12 round limit would.
                three_parallel_calls = [
                    _gemini_response(
                        [
                            _function_call_part("get_payment", {"payment_reference": payment_ref}, f"c{i}a"),
                            _function_call_part("get_payment", {"payment_reference": payment_ref}, f"c{i}b"),
                            _function_call_part("get_payment", {"payment_reference": payment_ref}, f"c{i}c"),
                        ]
                    )
                    for i in range(8)
                ]
                fake_client = FakeGeminiClient(three_parallel_calls)

                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError as error:
                    assert "maximum of 20 tool calls" in str(error)
            finally:
                _cleanup(cur, conn, exception_id)


# ------------------------------------------------------------------
# 13/14. Provider timeout / provider error
# ------------------------------------------------------------------

def test_provider_timeout_is_mapped_to_ai_investigation_error():
    payment_ref = "pay_testgemini009"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                timeout_error = TimeoutError("Request timed out after 60000ms")
                fake_client = FakeGeminiClient([timeout_error])

                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass

                cur.execute(
                    "select count(*) from investigation_tool_calls where investigation_id = %s",
                    (investigation_id,),
                )
                assert cur.fetchone()[0] == 0
            finally:
                _cleanup(cur, conn, exception_id)


def test_provider_server_error_is_mapped_to_ai_investigation_error():
    payment_ref = "pay_testgemini010"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                server_error = genai_errors.ServerError(
                    503, {"error": {"message": "model overloaded", "status": "UNAVAILABLE"}}
                )
                fake_client = FakeGeminiClient([server_error])

                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError as error:
                    assert error.status_code == 502
            finally:
                _cleanup(cur, conn, exception_id)


def test_provider_client_error_invalid_key_is_mapped_to_ai_investigation_error():
    payment_ref = "pay_testgemini011"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                client_error = genai_errors.ClientError(
                    401, {"error": {"message": "API key not valid", "status": "UNAUTHENTICATED"}}
                )
                fake_client = FakeGeminiClient([client_error])

                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError:
                    pass
            finally:
                _cleanup(cur, conn, exception_id)


def test_malformed_function_call_finish_reason_is_mapped_to_ai_investigation_error():
    payment_ref = "pay_testgemini012"
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                f"Payment {payment_ref} expected 1643.05 but settlement contains 1063.73. Difference: 579.32.",
            )
            investigation_id = _insert_investigation(cur, exception_id)
            conn.commit()

            try:
                fake_client = FakeGeminiClient(
                    [
                        _gemini_response(
                            [_text_only_part("")],
                            finish_reason=types.FinishReason.MALFORMED_FUNCTION_CALL,
                        )
                    ]
                )
                try:
                    run_ai_investigation(
                        investigation_id, exception_id, provider=GeminiProvider(client=fake_client)
                    )
                    raise AssertionError("expected AiInvestigationError")
                except AiInvestigationError as error:
                    assert "malformed function call" in str(error)
            finally:
                _cleanup(cur, conn, exception_id)


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
