"""Reporting aggregate + API checks against the real FastAPI app and the
live database -- same pattern as test_auth_register.py.

Strictly read-only: nothing here creates, mutates, or deletes financial
data, exceptions, or investigations. The one write is a throwaway
analyst user needed to exercise the authenticated endpoint, cleaned up
in a finally block.

The load-bearing assertions recompute every reported figure a second
way, independently of app/reports/store.py -- either in plain Python
over the source tables, or by cross-referencing the exceptions the
reconciliation engine itself persisted. Agreement between two unrelated
paths is what proves the report is reading real data rather than
inventing it.

Run directly: python backend/tests/test_reports.py
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.investigation.runners.deterministic import connect
from app.main import app
from app.reports.store import (
    EXCEPTION_WORKFLOW_STATUSES,
    get_available_period,
    get_report_summary,
)

REPORT_USER_EMAIL = "test-reports-analyst@ledgerlens.dev"
REPORT_USER_PASSWORD = "Correct-Horse-1"


def _cleanup_user(cur, email: str) -> None:
    cur.execute("select id from users where email = %s", (email,))
    row = cur.fetchone()
    if row is None:
        return
    cur.execute("delete from sessions where user_id = %s", (row[0],))
    cur.execute("delete from users where id = %s", (row[0],))


def _authenticated_client() -> TestClient:
    client = TestClient(app)
    client.post(
        "/auth/register",
        json={"email": REPORT_USER_EMAIL, "password": REPORT_USER_PASSWORD},
    )
    login = client.post(
        "/auth/login",
        json={"email": REPORT_USER_EMAIL, "password": REPORT_USER_PASSWORD},
    )
    assert login.status_code == 200
    return client


def _recompute_from_source(cur) -> dict:
    """The report's financial figures, derived again in plain Python
    straight from the source tables using the reconciliation engine's
    own formula (gross - fees - taxes + adjustments), with no reference
    to app/reports/store.py's SQL."""
    cur.execute(
        "select id, external_payment_id, amount from payments order by external_payment_id"
    )
    payments = cur.fetchall()

    totals = {
        "count": 0,
        "gross": Decimal("0.00"),
        "observed": Decimal("0.00"),
        "fees": Decimal("0.00"),
        "taxes": Decimal("0.00"),
        "adjustments": Decimal("0.00"),
        "expected_matched": Decimal("0.00"),
        "observed_matched": Decimal("0.00"),
        "reconciled_count": 0,
        "reconciled_amount": Decimal("0.00"),
        "duplicate_count": 0,
        "duplicate_amount": Decimal("0.00"),
        "unsettled_count": 0,
        "unsettled_amount": Decimal("0.00"),
    }

    for _payment_id, reference, gross in payments:
        cur.execute(
            "select id, settlement_amount from settlements where reference = %s",
            (reference,),
        )
        settlements = cur.fetchall()

        fee = tax = adjustment = observed = Decimal("0.00")
        for settlement_id, settlement_amount in settlements:
            for table, bucket in (("fees", "fee"), ("taxes", "tax"), ("adjustments", "adj")):
                cur.execute(
                    f"select coalesce(sum(amount), 0) from {table} where settlement_id = %s",
                    (settlement_id,),
                )
                value = cur.fetchone()[0]
                if bucket == "fee":
                    fee += value
                elif bucket == "tax":
                    tax += value
                else:
                    adjustment += value
            observed += settlement_amount

        expected = gross - fee - tax + adjustment

        totals["count"] += 1
        totals["gross"] += gross
        totals["observed"] += observed
        totals["fees"] += fee
        totals["taxes"] += tax
        totals["adjustments"] += adjustment

        if len(settlements) == 1:
            totals["expected_matched"] += expected
            totals["observed_matched"] += observed
            if expected == observed:
                totals["reconciled_count"] += 1
                totals["reconciled_amount"] += observed
        elif len(settlements) > 1:
            totals["duplicate_count"] += 1
            totals["duplicate_amount"] += observed
        else:
            totals["unsettled_count"] += 1
            totals["unsettled_amount"] += gross

    return totals


def test_financial_control_matches_independent_recomputation():
    with connect() as conn:
        with conn.cursor() as cur:
            report = get_report_summary(cur)["financial_control"]
            expected = _recompute_from_source(cur)

            assert report["total_payments"] == expected["count"]
            assert Decimal(report["total_payment_value"]) == expected["gross"]
            assert Decimal(report["total_settled_value"]) == expected["observed"]
            assert Decimal(report["total_fees"]) == expected["fees"]
            assert Decimal(report["total_taxes"]) == expected["taxes"]
            assert Decimal(report["total_adjustments"]) == expected["adjustments"]
            assert (
                Decimal(report["expected_settlement_value"])
                == expected["expected_matched"]
            )
            assert Decimal(report["total_financial_gap"]) == (
                expected["expected_matched"] - expected["observed_matched"]
            )
            assert report["reconciled_payments"] == expected["reconciled_count"]
            assert Decimal(report["reconciled_amount"]) == expected["reconciled_amount"]
            assert report["duplicate_settled_payments"] == expected["duplicate_count"]
            assert (
                Decimal(report["duplicate_settlement_value"])
                == expected["duplicate_amount"]
            )
            assert report["unsettled_payments"] == expected["unsettled_count"]
            assert (
                Decimal(report["unsettled_payment_value"]) == expected["unsettled_amount"]
            )


def test_financial_gap_equals_persisted_ex01_impact():
    """The gap is derived from payments/settlements/fees/taxes; each
    EX01 exception's financial_impact was written independently by
    reconciliation/engine.py as that payment's own difference. They must
    agree -- if they ever diverge, the report has drifted away from the
    engine."""
    with connect() as conn:
        with conn.cursor() as cur:
            summary = get_report_summary(cur)
            by_code = {
                item["code"]: Decimal(item["financial_impact"])
                for item in summary["exceptions"]["by_code"]
            }

            assert Decimal(summary["financial_control"]["total_financial_gap"]) == (
                by_code["EX01"]
            )


def test_unsettled_value_equals_persisted_ex02_impact():
    """Same cross-check on the other side: EX02's persisted impact is the
    full payment amount of every payment with no settlement."""
    with connect() as conn:
        with conn.cursor() as cur:
            summary = get_report_summary(cur)
            by_code = {
                item["code"]: Decimal(item["financial_impact"])
                for item in summary["exceptions"]["by_code"]
            }

            assert Decimal(
                summary["financial_control"]["unsettled_payment_value"]
            ) == by_code["EX02"]


def test_exception_counts_match_the_exceptions_table():
    with connect() as conn:
        with conn.cursor() as cur:
            report = get_report_summary(cur)["exceptions"]

            cur.execute(
                "select exception_code, count(*) from exceptions group by 1 order by 1"
            )
            actual = dict(cur.fetchall())

            assert {item["code"]: item["count"] for item in report["by_code"]} == actual
            assert report["total"] == sum(actual.values())


def test_deterministic_benchmark_is_intact():
    """The evaluation dataset must still be 100 PAY-* payments producing
    15 EX01 / 8 EX02 / 7 EX03. Scoped to PAY-* deliberately: live
    Razorpay Test Mode records are legitimate data that lives alongside
    the benchmark and must not be counted into it, nor deleted to make
    it match."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from payments where external_payment_id like 'PAY-%'"
            )
            assert cur.fetchone()[0] == 100

            cur.execute(
                """
                select exception_code, count(*)
                from exceptions
                where description like '%PAY-%'
                group by 1
                order by 1
                """
            )
            assert dict(cur.fetchall()) == {"EX01": 15, "EX02": 8, "EX03": 7}


def test_exception_status_breakdown_covers_every_exception():
    """The five workflow buckets are derived, so they must partition the
    exception set exactly -- no exception counted twice, none dropped."""
    with connect() as conn:
        with conn.cursor() as cur:
            report = get_report_summary(cur)["exceptions"]

            assert set(report["by_status"]) == set(EXCEPTION_WORKFLOW_STATUSES)
            assert sum(report["by_status"].values()) == report["total"]


def test_exception_exposure_equals_sum_of_persisted_impacts():
    with connect() as conn:
        with conn.cursor() as cur:
            report = get_report_summary(cur)["exceptions"]

            cur.execute("select coalesce(sum(financial_impact), 0) from exceptions")
            assert Decimal(report["exception_exposure"]) == cur.fetchone()[0]


def test_investigation_outcomes_partition_and_match_rates():
    with connect() as conn:
        with conn.cursor() as cur:
            report = get_report_summary(cur)["investigations"]

            cur.execute("select count(*) from investigations")
            assert report["total"] == cur.fetchone()[0]

            buckets = (
                report["resolved"]
                + report["escalated"]
                + report["awaiting_human_review"]
                + report["in_progress"]
            )
            assert buckets == report["total"]

            if report["total"]:
                assert report["resolution_rate"] == round(
                    report["resolved"] / report["total"] * 100, 1
                )
                assert report["escalation_rate"] == round(
                    report["escalated"] / report["total"] * 100, 1
                )
            else:
                assert report["resolution_rate"] == 0.0
                assert report["escalation_rate"] == 0.0


def test_ai_insights_count_only_ai_investigations():
    """root_cause_assessment is the AI-only column (migration 008), so
    the AI count and the average confidence must be scoped to rows that
    actually have one."""
    with connect() as conn:
        with conn.cursor() as cur:
            report = get_report_summary(cur)["ai"]

            cur.execute(
                "select count(*), avg(confidence) from investigations "
                "where root_cause_assessment is not null"
            )
            count, average = cur.fetchone()

            assert report["investigation_count"] == count
            if average is None:
                assert report["average_confidence"] is None
            else:
                assert Decimal(report["average_confidence"]) == round(average, 1)

            cur.execute(
                "select count(*) from investigations where human_decision = 'RESOLVED'"
            )
            assert report["human_decisions"]["RESOLVED"] == cur.fetchone()[0]

            cur.execute(
                "select count(*) from investigations where human_decision = 'ESCALATED'"
            )
            assert report["human_decisions"]["ESCALATED"] == cur.fetchone()[0]


def test_root_cause_categories_match_exception_categories():
    with connect() as conn:
        with conn.cursor() as cur:
            report = get_report_summary(cur)["ai"]

            cur.execute(
                """
                select e.category, count(*)
                from investigations i
                join exceptions e on e.id = i.exception_id
                group by 1
                """
            )
            assert {row["category"]: row["count"] for row in report["root_cause_categories"]} == (
                dict(cur.fetchall())
            )


def test_date_filter_narrows_every_section_consistently():
    """A scoped report must be a subset of the unscoped one on every
    section -- never larger, and never leaving one section unfiltered
    while another narrows."""
    with connect() as conn:
        with conn.cursor() as cur:
            period = get_available_period(cur)
            assert period["start"] is not None

            full = get_report_summary(cur)
            scoped = get_report_summary(cur, period["start"], period["start"])

            assert (
                scoped["financial_control"]["total_payments"]
                <= full["financial_control"]["total_payments"]
            )
            assert scoped["exceptions"]["total"] <= full["exceptions"]["total"]
            assert scoped["investigations"]["total"] <= full["investigations"]["total"]
            assert (
                scoped["ai"]["investigation_count"] <= full["ai"]["investigation_count"]
            )
            assert scoped["period"] == {
                "start": period["start"],
                "end": period["start"],
            }


def test_full_range_filter_equals_unfiltered_report():
    """Selecting the entire available span must reproduce the unscoped
    numbers exactly -- proof the filter is inclusive at both ends and
    silently drops nothing."""
    with connect() as conn:
        with conn.cursor() as cur:
            period = get_available_period(cur)
            full = get_report_summary(cur)
            scoped = get_report_summary(cur, period["start"], period["end"])

            assert scoped["financial_control"] == full["financial_control"]
            assert scoped["exceptions"] == full["exceptions"]
            assert scoped["investigations"] == full["investigations"]
            assert scoped["ai"] == full["ai"]


def test_reports_endpoint_requires_authentication():
    client = TestClient(app)
    assert client.get("/reports/summary").status_code == 401


def test_reports_endpoint_returns_the_same_payload_as_the_store():
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = _authenticated_client()
                response = client.get("/reports/summary")
                assert response.status_code == 200

                body = response.json()
                expected = get_report_summary(cur)

                assert body["financial_control"] == expected["financial_control"]
                assert body["exceptions"] == expected["exceptions"]
                assert body["investigations"] == expected["investigations"]
                assert body["ai"] == expected["ai"]
                assert "available_period" in body
            finally:
                _cleanup_user(cur, REPORT_USER_EMAIL)
                conn.commit()


def test_reports_endpoint_accepts_a_date_range():
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = _authenticated_client()
                response = client.get(
                    "/reports/summary", params={"start": "2026-08-24", "end": "2026-08-24"}
                )
                assert response.status_code == 200
                assert response.json()["period"] == {
                    "start": "2026-08-24",
                    "end": "2026-08-24",
                }
            finally:
                _cleanup_user(cur, REPORT_USER_EMAIL)
                conn.commit()


def test_reports_endpoint_rejects_bad_dates():
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = _authenticated_client()

                inverted = client.get(
                    "/reports/summary",
                    params={"start": "2026-08-26", "end": "2026-08-24"},
                )
                assert inverted.status_code == 400

                malformed = client.get(
                    "/reports/summary", params={"start": "not-a-date"}
                )
                assert malformed.status_code == 400
            finally:
                _cleanup_user(cur, REPORT_USER_EMAIL)
                conn.commit()


def test_report_never_exposes_credentials():
    """A reporting payload has no business carrying anything from the
    users/sessions tables."""
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                client = _authenticated_client()
                body = client.get("/reports/summary").text.lower()

                for forbidden in ("password", "password_hash", "password_salt", "token"):
                    assert forbidden not in body
            finally:
                _cleanup_user(cur, REPORT_USER_EMAIL)
                conn.commit()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
