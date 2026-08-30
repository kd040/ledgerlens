"""DB-integration checks for the human-review resolution workflow and
the investigation daily-financials breakdown added in this checkpoint.
Throwaway TEST-RESOLVE-*/TEST-DAILY-* rows only; cleans up after itself.

Run directly: python backend/tests/test_resolution_and_daily_financials.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.investigation.runners.deterministic import connect
from app.investigation.services.audit import list_evidence
from app.investigation.services.daily_financials import (
    get_daily_financials,
    list_available_dates,
)
from app.investigation.services.investigation_store import get_investigation
from app.investigation.services.resolution import (
    ResolutionError,
    escalate_investigation,
    resolve_investigation,
)
from app.investigation.tools.payments import get_payment


def _insert_exception(cur, code: str, category: str, description: str) -> str:
    cur.execute(
        """
        insert into exceptions (exception_code, category, description, financial_impact, status)
        values (%s, %s, %s, 50.00, 'OPEN')
        returning id
        """,
        (code, category, description),
    )
    return str(cur.fetchone()[0])


def _insert_investigation(cur, exception_id: str, status: str, recommendation: str) -> str:
    cur.execute(
        """
        insert into investigations (exception_id, status, recommendation, completed_at)
        values (%s, %s, %s, now())
        returning id
        """,
        (exception_id, status, recommendation),
    )
    return str(cur.fetchone()[0])


def test_resolve_requires_human_review_recommendation():
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                "Payment TEST-RESOLVE-A expected 100.00 but settlement contains 50.00. Difference: 50.00.",
            )
            investigation_id = _insert_investigation(cur, exception_id, "COMPLETED", "NO_ACTION")
            conn.commit()

            try:
                investigation = get_investigation(cur, investigation_id)
                try:
                    resolve_investigation(
                        cur, investigation_id, investigation, "note", "reviewer@ledgerlens.dev"
                    )
                    raise AssertionError("expected ResolutionError")
                except ResolutionError:
                    pass
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                conn.commit()


def test_resolve_requires_nonempty_note():
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                "Payment TEST-RESOLVE-B expected 100.00 but settlement contains 50.00. Difference: 50.00.",
            )
            investigation_id = _insert_investigation(cur, exception_id, "ESCALATED", "HUMAN_REVIEW")
            conn.commit()

            try:
                investigation = get_investigation(cur, investigation_id)
                try:
                    resolve_investigation(
                        cur, investigation_id, investigation, "   ", "reviewer@ledgerlens.dev"
                    )
                    raise AssertionError("expected ResolutionError")
                except ResolutionError:
                    pass
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                conn.commit()


def test_resolve_updates_investigation_exception_and_records_evidence():
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                "Payment TEST-RESOLVE-C expected 100.00 but settlement contains 50.00. Difference: 50.00.",
            )
            investigation_id = _insert_investigation(cur, exception_id, "ESCALATED", "HUMAN_REVIEW")
            conn.commit()

            try:
                investigation = get_investigation(cur, investigation_id)
                resolve_investigation(
                    cur,
                    investigation_id,
                    investigation,
                    "Confirmed with merchant, closing out.",
                    "reviewer@ledgerlens.dev",
                )
                conn.commit()

                updated = get_investigation(cur, investigation_id)
                assert updated["status"] == "COMPLETED"
                assert updated["recommendation"] == "RESOLVED"
                assert updated["human_decision"] == "RESOLVED"

                cur.execute("select status from exceptions where id = %s", (exception_id,))
                assert cur.fetchone()[0] == "RESOLVED"

                evidence = list_evidence(cur, investigation_id)
                human_decisions = [e for e in evidence if e["evidence_type"] == "HUMAN_DECISION"]
                assert len(human_decisions) == 1
                assert "Confirmed with merchant, closing out." in human_decisions[0]["description"]
                assert "ESCALATED" in human_decisions[0]["description"]
                assert "reviewer@ledgerlens.dev" in human_decisions[0]["description"]
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                conn.commit()


def test_escalate_updates_investigation_exception_and_records_evidence():
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                "Payment TEST-RESOLVE-D expected 100.00 but settlement contains 50.00. Difference: 50.00.",
            )
            investigation_id = _insert_investigation(cur, exception_id, "COMPLETED", "HUMAN_REVIEW")
            conn.commit()

            try:
                investigation = get_investigation(cur, investigation_id)
                escalate_investigation(
                    cur,
                    investigation_id,
                    investigation,
                    "Needs a second opinion from the payments team.",
                    "reviewer@ledgerlens.dev",
                )
                conn.commit()

                updated = get_investigation(cur, investigation_id)
                assert updated["status"] == "ESCALATED"
                # Escalation is a human_decision, not an AI recommendation --
                # recommendation stays exactly what the AI produced.
                assert updated["recommendation"] == "HUMAN_REVIEW"
                assert updated["human_decision"] == "ESCALATED"

                cur.execute("select status from exceptions where id = %s", (exception_id,))
                assert cur.fetchone()[0] == "ESCALATED"

                evidence = list_evidence(cur, investigation_id)
                human_decisions = [e for e in evidence if e["evidence_type"] == "HUMAN_DECISION"]
                assert len(human_decisions) == 1
                assert "Escalated by human review" in human_decisions[0]["description"]
                assert "reviewer@ledgerlens.dev" in human_decisions[0]["description"]
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                conn.commit()


def test_cannot_resolve_and_escalate_the_same_investigation():
    with connect() as conn:
        with conn.cursor() as cur:
            exception_id = _insert_exception(
                cur, "EX01", "Amount Mismatch",
                "Payment TEST-RESOLVE-E expected 100.00 but settlement contains 50.00. Difference: 50.00.",
            )
            investigation_id = _insert_investigation(cur, exception_id, "COMPLETED", "HUMAN_REVIEW")
            conn.commit()

            try:
                investigation = get_investigation(cur, investigation_id)
                resolve_investigation(
                    cur, investigation_id, investigation, "Closing this out.", "reviewer@ledgerlens.dev"
                )
                conn.commit()

                already_decided = get_investigation(cur, investigation_id)
                try:
                    escalate_investigation(
                        cur, investigation_id, already_decided, "Actually, escalate it.", "reviewer@ledgerlens.dev"
                    )
                    raise AssertionError("expected ResolutionError")
                except ResolutionError:
                    pass
            finally:
                cur.execute("delete from investigations where exception_id = %s", (exception_id,))
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                conn.commit()


def test_daily_financials_single_settlement_day():
    payment_ref = "TEST-DAILY-SINGLE"
    settlement_ref = "TEST-DAILY-SINGLE-S"
    settlement_date = date.today() - timedelta(days=1)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into payments (external_payment_id, amount, currency, status, method) "
                "values (%s, 1000.00, 'INR', 'captured', 'card') returning id",
                (payment_ref,),
            )
            payment_id = str(cur.fetchone()[0])
            cur.execute(
                "insert into settlements (external_settlement_id, settlement_amount, currency, status, settlement_date, reference) "
                "values (%s, 950.00, 'INR', 'SETTLED', %s, %s) returning id",
                (settlement_ref, settlement_date, payment_ref),
            )
            settlement_id = str(cur.fetchone()[0])
            cur.execute(
                "insert into fees (settlement_id, amount, currency, fee_type) values (%s, 50.00, 'INR', 'RAZORPAY_FEE')",
                (settlement_id,),
            )
            conn.commit()

            try:
                payment = get_payment(cur, payment_id)
                dates = list_available_dates(cur, payment_ref)
                assert dates == [settlement_date.isoformat()]

                financials = get_daily_financials(cur, payment, payment_ref, dates[0])
                assert financials["gross_amount"] == "1000.00"
                assert financials["fee_amount"] == "50.00"
                assert financials["observed_amount"] == "950.00"
                assert financials["expected_amount"] == "950.00"
                assert financials["difference"] == "0.00"
            finally:
                cur.execute("delete from fees where settlement_id = %s", (settlement_id,))
                cur.execute("delete from settlements where id = %s", (settlement_id,))
                cur.execute("delete from payments where id = %s", (payment_id,))
                conn.commit()


def test_daily_financials_empty_when_no_settlements():
    payment_ref = "TEST-DAILY-NONE"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into payments (external_payment_id, amount, currency, status, method) "
                "values (%s, 500.00, 'INR', 'captured', 'card') returning id",
                (payment_ref,),
            )
            payment_id = str(cur.fetchone()[0])
            conn.commit()

            try:
                assert list_available_dates(cur, payment_ref) == []
            finally:
                cur.execute("delete from payments where id = %s", (payment_id,))
                conn.commit()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
