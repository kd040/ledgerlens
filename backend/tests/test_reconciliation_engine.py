"""DB-integration checks for reconcile_payments(), including the
settlement-lifecycle (SETTLEMENT_PENDING vs EX02) behavior added in this
checkpoint. Uses the real database (no test DB is configured for this
project) with throwaway TEST-ENGINE-* payment references, scoped via
payment_ids so nothing here can touch the demo/eval dataset or real
Razorpay rows. Cleans up after itself.

Run directly: python backend/tests/test_reconciliation_engine.py
"""

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasources.demo import run_demo_source
from app.investigation.runners.deterministic import connect
from app.reconciliation.engine import (
    NON_SETTLEABLE_PAYMENT_STATUSES,
    SETTLEABLE_PAYMENT_STATUSES,
    add_business_days,
    reconcile_payments,
)

PENDING_BUSINESS_DAYS = 2


def _insert_payment(cur, ref: str, amount: Decimal, created_at: datetime) -> None:
    cur.execute(
        """
        insert into payments (external_payment_id, amount, currency, status, method, created_at)
        values (%s, %s, 'INR', 'captured', 'card', %s)
        """,
        (ref, amount, created_at),
    )


def _insert_settlement(cur, settlement_ref: str, amount: Decimal, payment_ref: str) -> None:
    cur.execute(
        """
        insert into settlements (external_settlement_id, settlement_amount, currency, status, settlement_date, reference)
        values (%s, %s, 'INR', 'SETTLED', now(), %s)
        """,
        (settlement_ref, amount, payment_ref),
    )


def _cleanup(cur, payment_refs: list[str], settlement_refs: list[str]) -> None:
    cur.execute(
        "delete from reconciliation_links where source_id in (select id from payments where external_payment_id = any(%s))",
        (payment_refs,),
    )
    cur.execute(
        "delete from exceptions where description like 'No settlement found for payment TEST-ENGINE-%' "
        "or description like 'Payment TEST-ENGINE-%'"
    )
    cur.execute(
        "delete from fees where settlement_id in (select id from settlements where external_settlement_id = any(%s))",
        (settlement_refs,),
    )
    cur.execute("delete from settlements where external_settlement_id = any(%s)", (settlement_refs,))
    cur.execute("delete from payments where external_payment_id = any(%s)", (payment_refs,))


def _take_payment_context(results, created_at, status="captured"):
    """Pops the payment-context fields off each result row, asserting
    they carry the payment's real instant and provider status, so the
    per-status assertions below can stay exact-equality on the
    reconciliation fields alone.

    The timestamp is compared as a parsed instant, not as a string: the
    engine renders whatever offset the DB session hands back, and only
    the instant is the actual contract.
    """
    for row in results:
        assert datetime.fromisoformat(row.pop("payment_created_at")) == created_at
        assert row.pop("payment_status") == status
    return results


def test_recent_payment_no_settlement_is_pending():
    ref = "TEST-ENGINE-PENDING"
    created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), created_at)
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref], settlement_pending_business_days=PENDING_BUSINESS_DAYS)
            assert _take_payment_context(results, created_at) == [{
                "payment": ref, "status": "SETTLEMENT_PENDING", "category": "Settlement Pending",
                "gross_amount": "100.00", "payment_date": created_at.date().isoformat(),
            }]
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [])
            conn.commit()


def test_old_payment_no_settlement_is_ex02():
    ref = "TEST-ENGINE-OVERDUE"
    created_at = datetime.now(timezone.utc) - timedelta(days=5)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), created_at)
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref], settlement_pending_business_days=PENDING_BUSINESS_DAYS)
            assert _take_payment_context(results, created_at) == [{
                "payment": ref, "status": "EX02", "category": "Missing Record",
                "gross_amount": "100.00", "payment_date": created_at.date().isoformat(),
            }]
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [])
            conn.commit()


def test_no_pending_window_is_ex02_immediately():
    """Default/no-window behavior must be exactly what it always was --
    this is what the demo/eval dataset and the unscoped endpoint call
    with, so a brand-new payment must still be EX02, not PENDING."""
    ref = "TEST-ENGINE-NOWINDOW"
    created_at = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), created_at)
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref])
            assert _take_payment_context(results, created_at) == [{
                "payment": ref, "status": "EX02", "category": "Missing Record",
                "gross_amount": "100.00", "payment_date": created_at.date().isoformat(),
            }]
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [])
            conn.commit()


def test_matching_settlement_is_reconciled():
    ref = "TEST-ENGINE-RECONCILED"
    settlement_ref = "TEST-ENGINE-SETL-RECONCILED"
    created_at = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), created_at)
            _insert_settlement(cur, settlement_ref, Decimal("100.00"), ref)
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref], settlement_pending_business_days=PENDING_BUSINESS_DAYS)
            assert _take_payment_context(results, created_at) == [{
                "payment": ref, "status": "RECONCILED",
                "gross_amount": "100.00", "fee_amount": "0", "tax_amount": "0",
                "adjustment_amount": "0",
                "expected_amount": "100.00", "observed_amount": "100.00", "difference": "0.00",
                "payment_date": created_at.date().isoformat(),
            }]
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [settlement_ref])
            conn.commit()


def test_mismatched_settlement_amount_is_ex01():
    ref = "TEST-ENGINE-MISMATCH"
    settlement_ref = "TEST-ENGINE-SETL-MISMATCH"
    created_at = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), created_at)
            _insert_settlement(cur, settlement_ref, Decimal("80.00"), ref)
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref], settlement_pending_business_days=PENDING_BUSINESS_DAYS)
            assert _take_payment_context(results, created_at) == [{
                "payment": ref, "status": "EX01", "category": "Amount Mismatch",
                "gross_amount": "100.00", "fee_amount": "0", "tax_amount": "0",
                "adjustment_amount": "0",
                "expected_amount": "100.00", "observed_amount": "80.00", "difference": "20.00",
                "payment_date": created_at.date().isoformat(),
            }]
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [settlement_ref])
            conn.commit()


def test_two_settlements_is_ex03():
    ref = "TEST-ENGINE-DUP"
    settlement_refs = ["TEST-ENGINE-SETL-DUP-1", "TEST-ENGINE-SETL-DUP-2"]
    created_at = datetime.now(timezone.utc)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), created_at)
            for settlement_ref in settlement_refs:
                _insert_settlement(cur, settlement_ref, Decimal("100.00"), ref)
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref], settlement_pending_business_days=PENDING_BUSINESS_DAYS)
            assert _take_payment_context(results, created_at) == [{
                "payment": ref, "status": "EX03", "category": "Duplicate Record", "settlement_count": 2,
                "gross_amount": "100.00", "fee_amount": "0.00", "tax_amount": "0.00",
                "adjustment_amount": "0.00", "observed_amount": "200.00",
                "payment_date": created_at.date().isoformat(),
            }]
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], settlement_refs)
            conn.commit()


def test_demo_source_is_scoped_to_pay_rows_and_ignores_range():
    """run_demo_source must stay an isolated 100-record benchmark even
    though other sources (e.g. razorpay_test) write unrelated rows into
    the same shared payments table -- payment_ids must be the actual
    PAY-* set, never None/unrestricted. The date range is accepted but
    has no effect: two different ranges must return the same set."""
    now = datetime.now(timezone.utc)
    result_a = run_demo_source(now - timedelta(days=1), now)
    result_b = run_demo_source(now - timedelta(days=365), now - timedelta(days=200))

    assert result_a["payment_ids"] is not None
    assert result_a["payment_ids"] == result_b["payment_ids"]
    assert result_a["payments_fetched"] == len(result_a["payment_ids"])
    assert all(ref.startswith("PAY-") for ref in result_a["payment_ids"])
    assert "TEST-ENGINE-PENDING" not in result_a["payment_ids"]


# ------------------------------------------------------------------
# Never-captured payments (NOT_CAPTURED)
# ------------------------------------------------------------------


def _insert_payment_with_status(cur, ref, amount, created_at, status):
    cur.execute(
        """
        insert into payments (external_payment_id, amount, currency, status, method, created_at)
        values (%s, %s, 'INR', %s, 'card', %s)
        """,
        (ref, amount, status, created_at),
    )


def test_uncaptured_payment_is_not_captured_not_an_exception():
    """A payment the provider never captured is not money owed, so an
    absent settlement is not EX02. Aged well past the pending window so
    the only thing that can spare it from EX02 is the status check."""
    for status in ("created", "authorized", "failed"):
        ref = f"TEST-ENGINE-UNCAPTURED-{status.upper()}"
        created_at = datetime.now(timezone.utc) - timedelta(days=30)
        with connect() as conn:
            with conn.cursor() as cur:
                _insert_payment_with_status(cur, ref, Decimal("100.00"), created_at, status)
                conn.commit()
            try:
                results = reconcile_payments(
                    payment_ids=[ref], settlement_pending_business_days=PENDING_BUSINESS_DAYS
                )
                assert _take_payment_context(results, created_at, status) == [{
                    "payment": ref, "status": "NOT_CAPTURED", "category": "Not Captured",
                    "gross_amount": "100.00",
                    "payment_date": created_at.date().isoformat(),
                }]

                with conn.cursor() as cur:
                    cur.execute(
                        "select count(*) from exceptions where description like %s",
                        (f"%{ref}%",),
                    )
                    assert cur.fetchone()[0] == 0, (
                        f"a {status!r} payment must never create an exception row"
                    )
            finally:
                with conn.cursor() as cur:
                    _cleanup(cur, [ref], [])
                conn.commit()


def test_uncaptured_check_applies_without_a_pending_window_too():
    """The demo source passes no pending window; an uncaptured payment
    must still not become EX02 on that path."""
    ref = "TEST-ENGINE-UNCAPTURED-NOWINDOW"
    created_at = datetime.now(timezone.utc) - timedelta(days=30)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment_with_status(cur, ref, Decimal("100.00"), created_at, "failed")
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref])
            assert results[0]["status"] == "NOT_CAPTURED"
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [])
            conn.commit()


def test_captured_payment_is_unaffected_by_the_status_check():
    """The deny-list must not accidentally catch a settleable payment --
    including the demo dataset's own uppercase 'CAPTURED'."""
    for status in ("captured", "CAPTURED", "refunded"):
        ref = f"TEST-ENGINE-SETTLEABLE-{status}"
        created_at = datetime.now(timezone.utc) - timedelta(days=30)
        with connect() as conn:
            with conn.cursor() as cur:
                _insert_payment_with_status(cur, ref, Decimal("100.00"), created_at, status)
                conn.commit()
            try:
                results = reconcile_payments(
                    payment_ids=[ref], settlement_pending_business_days=PENDING_BUSINESS_DAYS
                )
                assert results[0]["status"] == "EX02", (
                    f"{status!r} is settleable and must still raise EX02"
                )
            finally:
                with conn.cursor() as cur:
                    _cleanup(cur, [ref], [])
                conn.commit()


def test_deterministic_benchmark_is_unchanged_by_the_status_check():
    """The load-bearing guard: the full 100-record evaluation dataset must
    still produce exactly 70 RECONCILED / 15 EX01 / 8 EX02 / 7 EX03."""
    payment_ids = run_demo_source(
        datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc)
    )["payment_ids"]
    assert len(payment_ids) == 100

    results = reconcile_payments(payment_ids=payment_ids)
    counts = Counter(row["status"] for row in results)

    assert counts == {"RECONCILED": 70, "EX01": 15, "EX02": 8, "EX03": 7}
    assert all(row["payment_status"] == "CAPTURED" for row in results)


def test_every_result_row_carries_the_payment_instant_and_status():
    """Task-1 contract: the UI can only show a real payment date/time if
    every row carries one, whatever its reconciliation outcome."""
    payment_ids = run_demo_source(
        datetime.now(timezone.utc) - timedelta(days=1), datetime.now(timezone.utc)
    )["payment_ids"]
    results = reconcile_payments(payment_ids=payment_ids)

    for row in results:
        assert row["payment_created_at"] is not None
        assert row["payment_status"] is not None
        # A full instant, not just the day label.
        assert datetime.fromisoformat(row["payment_created_at"]).tzinfo is not None
        assert row["payment_created_at"].startswith(row["payment_date"])

# ------------------------------------------------------------------
# Banking-day settlement window
# ------------------------------------------------------------------

# 2026-08-24 is a Monday, so this week runs Mon..Sun over the 24th-30th.
_MONDAY = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _plus_two_business_days(offset_days: int) -> datetime:
    return add_business_days(_MONDAY + timedelta(days=offset_days), 2)


def test_business_days_skip_the_weekend():
    """T+2 means two banking days: Friday lands on Tuesday, not Sunday."""
    cases = {
        0: datetime(2026, 8, 26),   # Mon -> Wed
        1: datetime(2026, 8, 27),   # Tue -> Thu
        2: datetime(2026, 8, 28),   # Wed -> Fri
        3: datetime(2026, 8, 31),   # Thu -> Mon (skips Sat/Sun)
        4: datetime(2026, 9, 1),    # Fri -> Tue
        5: datetime(2026, 9, 1),    # Sat -> Tue
        6: datetime(2026, 9, 1),    # Sun -> Tue
    }
    for offset, expected in cases.items():
        assert _plus_two_business_days(offset).date() == expected.date(), (
            f"offset {offset} landed wrong"
        )


def test_business_days_never_land_on_a_weekend():
    for offset in range(14):
        landed = _plus_two_business_days(offset)
        assert landed.weekday() < 5, f"offset {offset} landed on a weekend"


def test_zero_or_negative_business_days_is_the_start_instant():
    assert add_business_days(_MONDAY, 0) == _MONDAY
    assert add_business_days(_MONDAY, -1) == _MONDAY


def test_weekend_payment_is_still_pending_on_monday():
    """A payment captured on Saturday has a Tuesday deadline, so on the
    Monday in between it is normal lag -- not a Missing Record. Under
    calendar days it would already have been EX02."""
    saturday = datetime.now(timezone.utc) - timedelta(days=2)
    while saturday.weekday() != 5:
        saturday -= timedelta(days=1)
    # Only meaningful if "now" is still inside the banking deadline.
    if datetime.now(timezone.utc) >= add_business_days(saturday, 2):
        return

    ref = "TEST-ENGINE-WEEKEND"
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), saturday)
            conn.commit()
        try:
            results = reconcile_payments(
                payment_ids=[ref], settlement_pending_business_days=2
            )
            assert results[0]["status"] == "SETTLEMENT_PENDING"
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [])
            conn.commit()


# ------------------------------------------------------------------
# Unknown / unsupported provider statuses
# ------------------------------------------------------------------


def test_unknown_status_is_never_ex02():
    """The invariant: a provider status the engine does not recognise
    must not be guessed into an exception. Aged far past the window so
    only the status check can stop it becoming EX02."""
    for status in ("disputed", "on_hold", "some_future_razorpay_state", ""):
        ref = f"TEST-ENGINE-UNKNOWN-{status or 'EMPTY'}"
        created_at = datetime.now(timezone.utc) - timedelta(days=30)
        with connect() as conn:
            with conn.cursor() as cur:
                _insert_payment_with_status(
                    cur, ref, Decimal("100.00"), created_at, status
                )
                conn.commit()
            try:
                results = reconcile_payments(
                    payment_ids=[ref], settlement_pending_business_days=2
                )
                assert results[0]["status"] == "UNKNOWN_STATUS", (
                    f"{status!r} must not be silently reconciled"
                )
                assert results[0]["category"] == "Unsupported Payment Status"

                with conn.cursor() as cur:
                    cur.execute(
                        "select count(*) from exceptions where description like %s",
                        (f"%{ref}%",),
                    )
                    assert cur.fetchone()[0] == 0, (
                        f"{status!r} must not create an exception row"
                    )
            finally:
                with conn.cursor() as cur:
                    _cleanup(cur, [ref], [])
                conn.commit()


def test_unknown_status_is_not_counted_as_captured():
    """It must not be mistaken for processed value either -- an unknown
    status is neither settleable nor known-non-settleable."""
    assert "disputed" not in SETTLEABLE_PAYMENT_STATUSES
    assert "disputed" not in NON_SETTLEABLE_PAYMENT_STATUSES
    assert not (SETTLEABLE_PAYMENT_STATUSES & NON_SETTLEABLE_PAYMENT_STATUSES)

    ref = "TEST-ENGINE-UNKNOWN-NOTCAPTURED"
    created_at = datetime.now(timezone.utc) - timedelta(days=30)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment_with_status(
                cur, ref, Decimal("100.00"), created_at, "disputed"
            )
            conn.commit()
        try:
            results = reconcile_payments(
                payment_ids=[ref], settlement_pending_business_days=2
            )
            assert results[0]["status"] != "RECONCILED"
            assert results[0]["status"] != "NOT_CAPTURED"
            # No settlement arithmetic is attempted at all.
            assert "expected_amount" not in results[0]
            assert "observed_amount" not in results[0]
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [ref], [])
            conn.commit()


def test_supported_statuses_keep_their_existing_behaviour():
    """Regression fence around the allow-list: every status the engine
    claims to support must still reach its established outcome."""
    created_at = datetime.now(timezone.utc) - timedelta(days=30)
    expected = {
        "captured": "EX02",
        "CAPTURED": "EX02",
        "refunded": "EX02",
        "created": "NOT_CAPTURED",
        "authorized": "NOT_CAPTURED",
        "failed": "NOT_CAPTURED",
    }
    for status, outcome in expected.items():
        ref = f"TEST-ENGINE-SUPPORTED-{status}"
        with connect() as conn:
            with conn.cursor() as cur:
                _insert_payment_with_status(
                    cur, ref, Decimal("100.00"), created_at, status
                )
                conn.commit()
            try:
                results = reconcile_payments(
                    payment_ids=[ref], settlement_pending_business_days=2
                )
                assert results[0]["status"] == outcome, (
                    f"{status!r} expected {outcome}, got {results[0]['status']}"
                )
            finally:
                with conn.cursor() as cur:
                    _cleanup(cur, [ref], [])
                conn.commit()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
