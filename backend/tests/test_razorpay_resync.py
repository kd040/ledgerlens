"""Re-sync safety for the Razorpay datasource.

A payment's status is not fixed at Razorpay: one synced while still
`created` becomes `captured` later. These tests drive the real
`run_razorpay_source` with a stubbed client -- no HTTP, no live API
calls -- and assert that a second sync updates the payment in place
rather than duplicating it or freezing the first status it ever saw.

Throwaway pay_TESTRESYNC* rows only, deleted by exact id in a finally
block. Nothing here touches the demo dataset or the real Razorpay rows.

Run directly: python backend/tests/test_razorpay_resync.py
"""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasources.razorpay import source as razorpay_source
from app.investigation.runners.deterministic import connect
from app.reconciliation.engine import reconcile_payments

RESYNC_ID = "pay_TESTRESYNC0001"

# Captured five days ago, so it is comfortably past a 2-banking-day
# settlement window once it is captured -- that is what lets the
# reconciliation assertion below distinguish the two states.
CREATED_AT = datetime.now(timezone.utc) - timedelta(days=5)


def _raw_payment(status: str) -> dict:
    """A Razorpay payments-API payload, in the provider's own shape and
    units (paise, unix seconds) -- fed through the real normalizer."""
    return {
        "id": RESYNC_ID,
        "entity": "payment",
        "amount": 10000,
        "currency": "INR",
        "status": status,
        "method": "card",
        "created_at": int(CREATED_AT.timestamp()),
    }


class _StubClient:
    """Stands in for RazorpayClient. Returns one payment with whatever
    status the test asked for, and no settlement recon lines."""

    def __init__(self, status: str):
        self._status = status

    def list_payments(self, from_ts, to_ts, count, skip):
        if skip:
            return {"items": []}
        return {"items": [_raw_payment(self._status)]}

    def list_settlement_recon(self, year, month, day, count, skip):
        return {"items": []}


def _sync(status: str) -> dict:
    window_start = CREATED_AT - timedelta(days=1)
    window_end = datetime.now(timezone.utc)
    with patch.object(
        razorpay_source, "RazorpayClient", lambda: _StubClient(status)
    ):
        return razorpay_source.run_razorpay_source(window_start, window_end)


def _payment_rows(cur) -> list[tuple]:
    cur.execute(
        "select external_payment_id, amount, status, method from payments "
        "where external_payment_id = %s",
        (RESYNC_ID,),
    )
    return cur.fetchall()


def _cleanup(cur) -> None:
    cur.execute(
        "delete from exceptions where description like %s", (f"%{RESYNC_ID}%",)
    )
    cur.execute(
        "delete from reconciliation_links where source_id in "
        "(select id from payments where external_payment_id = %s)",
        (RESYNC_ID,),
    )
    cur.execute("delete from payments where external_payment_id = %s", (RESYNC_ID,))


def test_resync_updates_status_without_duplicating_the_payment():
    """Covers the whole A-F sequence in one run, because the point is the
    transition: the same payment id, synced twice, must end up as one row
    that reflects the later status."""
    with connect() as conn:
        with conn.cursor() as cur:
            _cleanup(cur)
            conn.commit()
        try:
            # A + C: first sync inserts it, reported as created.
            first = _sync("created")
            assert first["payments_fetched"] == 1
            assert first["payment_ids"] == [RESYNC_ID]

            with conn.cursor() as cur:
                rows = _payment_rows(cur)
            assert len(rows) == 1
            assert rows[0][2] == "created"

            # The database id must survive the update -- exceptions and
            # investigations reference payments by it.
            with conn.cursor() as cur:
                cur.execute(
                    "select id from payments where external_payment_id = %s",
                    (RESYNC_ID,),
                )
                original_id = cur.fetchone()[0]

            # Reconciliation on the pre-capture state: never captured, so
            # no settlement is owed and no exception is raised.
            before = reconcile_payments(
                payment_ids=[RESYNC_ID], settlement_pending_business_days=2
            )
            assert before[0]["status"] == "NOT_CAPTURED"

            # B + D: second sync, same payment, now captured.
            second = _sync("captured")
            assert second["payments_fetched"] == 1

            with conn.cursor() as cur:
                rows = _payment_rows(cur)
            # B: still exactly one row -- no duplicate.
            assert len(rows) == 1
            # E: the database now holds the updated status.
            assert rows[0][2] == "captured"

            with conn.cursor() as cur:
                cur.execute(
                    "select id from payments where external_payment_id = %s",
                    (RESYNC_ID,),
                )
                assert cur.fetchone()[0] == original_id, (
                    "the row's identity must be preserved across a re-sync"
                )

            # F: reconciliation now acts on the captured state -- past the
            # settlement window with no settlement, so a genuine EX02.
            after = reconcile_payments(
                payment_ids=[RESYNC_ID], settlement_pending_business_days=2
            )
            assert after[0]["status"] == "EX02"
            assert after[0]["payment_status"] == "captured"
        finally:
            with conn.cursor() as cur:
                _cleanup(cur)
            conn.commit()


def test_resync_with_identical_data_is_idempotent():
    """Two syncs of byte-identical Razorpay data must leave exactly one
    unchanged row -- re-running a sync is not supposed to churn data."""
    with connect() as conn:
        with conn.cursor() as cur:
            _cleanup(cur)
            conn.commit()
        try:
            _sync("captured")
            with conn.cursor() as cur:
                first_rows = _payment_rows(cur)

            _sync("captured")
            with conn.cursor() as cur:
                second_rows = _payment_rows(cur)

            assert len(second_rows) == 1
            assert first_rows == second_rows
            assert second_rows[0][1] == Decimal("100.00")
            assert second_rows[0][3] == "card"
        finally:
            with conn.cursor() as cur:
                _cleanup(cur)
            conn.commit()


def test_resync_does_not_touch_unrelated_payments():
    """The upsert is keyed on external_payment_id, so a sync must leave
    the deterministic benchmark completely alone."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*), coalesce(sum(amount), 0) from payments "
                "where external_payment_id like 'PAY-%'"
            )
            before = cur.fetchone()
            _cleanup(cur)
            conn.commit()
        try:
            _sync("captured")
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*), coalesce(sum(amount), 0) from payments "
                    "where external_payment_id like 'PAY-%'"
                )
                assert cur.fetchone() == before
        finally:
            with conn.cursor() as cur:
                _cleanup(cur)
            conn.commit()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
