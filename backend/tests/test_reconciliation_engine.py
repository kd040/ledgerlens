"""DB-integration checks for reconcile_payments(), including the
settlement-lifecycle (SETTLEMENT_PENDING vs EX02) behavior added in this
checkpoint. Uses the real database (no test DB is configured for this
project) with throwaway TEST-ENGINE-* payment references, scoped via
payment_ids so nothing here can touch the demo/eval dataset or real
Razorpay rows. Cleans up after itself.

Run directly: python backend/tests/test_reconciliation_engine.py
"""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasources.demo import run_demo_source
from app.investigation.runners.deterministic import connect
from app.reconciliation.engine import reconcile_payments

PENDING_WINDOW = timedelta(days=2)


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


def test_recent_payment_no_settlement_is_pending():
    ref = "TEST-ENGINE-PENDING"
    created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, ref, Decimal("100.00"), created_at)
            conn.commit()
        try:
            results = reconcile_payments(payment_ids=[ref], settlement_pending_window=PENDING_WINDOW)
            assert results == [{
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
            results = reconcile_payments(payment_ids=[ref], settlement_pending_window=PENDING_WINDOW)
            assert results == [{
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
            assert results == [{
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
            results = reconcile_payments(payment_ids=[ref], settlement_pending_window=PENDING_WINDOW)
            assert results == [{
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
            results = reconcile_payments(payment_ids=[ref], settlement_pending_window=PENDING_WINDOW)
            assert results == [{
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
            results = reconcile_payments(payment_ids=[ref], settlement_pending_window=PENDING_WINDOW)
            assert results == [{
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


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
