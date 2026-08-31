"""Proves a Razorpay-sourced payment travels the full LedgerLens chain:

    Razorpay-shaped payment -> reconciliation -> exception -> investigation
    -> evidence -> reviewer decision

and, just as importantly, that the payments which are NOT financial
exceptions (normal settlement lag, and payments the provider never
captured) never enter that chain at all.

Throwaway pay_TESTFLOW* rows only, always deleted by exact id in a
finally block -- nothing here can touch the real Razorpay records, the
100-payment evaluation dataset, or any existing investigation decision.
The one user created is a temporary analyst, removed in the same block.

Run directly: python backend/tests/test_razorpay_investigation_flow.py
"""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.investigation.runners.deterministic import (
    connect,
    extract_payment_reference,
)
from app.investigation.services.audit import list_evidence
from app.investigation.services.investigation_store import (
    create_investigation,
    get_investigation,
)
from app.investigation.services.resolution import (
    ResolutionError,
    escalate_investigation,
    resolve_investigation,
)
from app.main import app
from app.reconciliation.engine import reconcile_payments

PENDING_BUSINESS_DAYS = 2

# Razorpay-shaped ids, distinct enough that cleanup can never collide
# with a real pay_* record.
OVERDUE = "pay_TESTFLOWoverdue01"
PENDING = "pay_TESTFLOWpending01"
UNCAPTURED = "pay_TESTFLOWcreated01"

ANALYST_EMAIL = "test-rzpflow-analyst@ledgerlens.dev"
ANALYST_PASSWORD = "Correct-Horse-1"


def _insert_payment(cur, ref, amount, created_at, status="captured"):
    cur.execute(
        """
        insert into payments (external_payment_id, amount, currency, status, method, created_at)
        values (%s, %s, 'INR', %s, 'card', %s)
        """,
        (ref, amount, status, created_at),
    )


def _cleanup(cur, refs):
    """Deletes by exact payment reference only. Investigations cascade
    from exceptions (migration 002), so removing the exception removes
    its investigation, evidence, hypotheses, and tool calls with it."""
    for ref in refs:
        cur.execute("delete from exceptions where description like %s", (f"%{ref}%",))
        cur.execute(
            "delete from reconciliation_links where source_id in "
            "(select id from payments where external_payment_id = %s)",
            (ref,),
        )
        cur.execute("delete from payments where external_payment_id = %s", (ref,))


def _cleanup_user(cur, email):
    cur.execute("select id from users where email = %s", (email,))
    row = cur.fetchone()
    if row is None:
        return
    cur.execute("delete from sessions where user_id = %s", (row[0],))
    cur.execute("delete from users where id = %s", (row[0],))


def _exception_for(cur, ref):
    cur.execute(
        "select id, exception_code from exceptions where description like %s",
        (f"%{ref}%",),
    )
    return cur.fetchone()


# ------------------------------------------------------------------
# What must NOT become an investigation
# ------------------------------------------------------------------


def test_settlement_pending_razorpay_payment_creates_no_exception():
    """Ordinary settlement latency is not a financial exception, so there
    is nothing for an investigation to attach to. This is the exact
    reason a freshly-synced Razorpay payment cannot be investigated --
    and it is correct behaviour, not a gap."""
    created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, PENDING, Decimal("100.00"), created_at)
            conn.commit()
        try:
            results = reconcile_payments(
                payment_ids=[PENDING], settlement_pending_business_days=PENDING_BUSINESS_DAYS
            )
            assert results[0]["status"] == "SETTLEMENT_PENDING"

            with conn.cursor() as cur:
                assert _exception_for(cur, PENDING) is None
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [PENDING])
            conn.commit()


def test_uncaptured_razorpay_payment_creates_no_exception():
    """A payment stuck in 'created' was never money owed, so it must not
    age into a false EX02 Missing Record."""
    created_at = datetime.now(timezone.utc) - timedelta(days=30)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, UNCAPTURED, Decimal("100.00"), created_at, "created")
            conn.commit()
        try:
            results = reconcile_payments(
                payment_ids=[UNCAPTURED], settlement_pending_business_days=PENDING_BUSINESS_DAYS
            )
            assert results[0]["status"] == "NOT_CAPTURED"

            with conn.cursor() as cur:
                assert _exception_for(cur, UNCAPTURED) is None
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [UNCAPTURED])
            conn.commit()


# ------------------------------------------------------------------
# What must become a fully investigable exception
# ------------------------------------------------------------------


def test_razorpay_payment_reference_is_extractable_from_the_exception():
    """The investigation runners locate a payment by parsing the
    reference out of the exception description. If pay_* ids were not
    recognised, every Razorpay investigation would fail at step one."""
    assert (
        extract_payment_reference(f"No settlement found for payment {OVERDUE}.")
        == OVERDUE
    )


def test_overdue_razorpay_payment_becomes_an_investigable_exception():
    """The full chain on a genuine Razorpay EX02: exception is raised,
    an investigation can be created and run against it, and the
    deterministic runner records real evidence."""
    created_at = datetime.now(timezone.utc) - timedelta(days=10)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, OVERDUE, Decimal("100.00"), created_at)
            conn.commit()
        try:
            results = reconcile_payments(
                payment_ids=[OVERDUE], settlement_pending_business_days=PENDING_BUSINESS_DAYS
            )
            assert results[0]["status"] == "EX02"
            assert results[0]["payment_status"] == "captured"
            assert results[0]["payment_created_at"] is not None

            with conn.cursor() as cur:
                row = _exception_for(cur, OVERDUE)
                assert row is not None, "a genuine EX02 must persist an exception"
                exception_id, code = str(row[0]), row[1]
                assert code == "EX02"

                investigation = create_investigation(cur, exception_id)
                conn.commit()

            from app.investigation.runners.deterministic import (
                run_missing_record_investigation,
            )

            outcome = run_missing_record_investigation(
                investigation["id"], exception_id
            )
            assert outcome["payment"] == OVERDUE

            with conn.cursor() as cur:
                evidence = list_evidence(cur, investigation["id"])
                assert evidence, "the runner must record evidence for a pay_* payment"

                detail = get_investigation(cur, investigation["id"])
                assert detail["exception_code"] == "EX02"
                assert detail["root_cause"] is not None
                assert detail["human_decision"] is None
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [OVERDUE])
            conn.commit()


def test_razorpay_investigation_honours_the_reviewer_only_decision():
    """Authorization is unchanged for Razorpay-sourced work: the decision
    services still refuse anything not awaiting human review, and a
    reviewer's resolve/escalate still writes human_decision."""
    created_at = datetime.now(timezone.utc) - timedelta(days=10)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, OVERDUE, Decimal("100.00"), created_at)
            conn.commit()
        try:
            reconcile_payments(
                payment_ids=[OVERDUE], settlement_pending_business_days=PENDING_BUSINESS_DAYS
            )
            with conn.cursor() as cur:
                exception_id = str(_exception_for(cur, OVERDUE)[0])
                cur.execute(
                    """
                    insert into investigations (exception_id, status, recommendation, completed_at)
                    values (%s, 'COMPLETED', 'HUMAN_REVIEW', now())
                    returning id
                    """,
                    (exception_id,),
                )
                investigation_id = str(cur.fetchone()[0])
                conn.commit()

                investigation = get_investigation(cur, investigation_id)

                try:
                    resolve_investigation(
                        cur, investigation_id, investigation, "   ", "reviewer@ledgerlens.dev"
                    )
                    raise AssertionError("a blank note must be rejected")
                except ResolutionError:
                    pass

                resolve_investigation(
                    cur, investigation_id, investigation,
                    "Razorpay settlement confirmed out of band.",
                    "reviewer@ledgerlens.dev",
                )
                conn.commit()

                resolved = get_investigation(cur, investigation_id)
                assert resolved["human_decision"] == "RESOLVED"

                try:
                    escalate_investigation(
                        cur, investigation_id, resolved, "changed my mind",
                        "reviewer@ledgerlens.dev",
                    )
                    raise AssertionError("an already-decided case must not be escalated")
                except ResolutionError:
                    pass
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [OVERDUE])
            conn.commit()


def test_analyst_cannot_resolve_a_razorpay_investigation_over_the_api():
    """The backend stays the authority: an authenticated Analyst may
    create and run an investigation on a Razorpay exception, but
    resolve/escalate remain reviewer-only."""
    created_at = datetime.now(timezone.utc) - timedelta(days=10)
    with connect() as conn:
        with conn.cursor() as cur:
            _insert_payment(cur, OVERDUE, Decimal("100.00"), created_at)
            conn.commit()
        try:
            reconcile_payments(
                payment_ids=[OVERDUE], settlement_pending_business_days=PENDING_BUSINESS_DAYS
            )
            with conn.cursor() as cur:
                exception_id = str(_exception_for(cur, OVERDUE)[0])
                cur.execute(
                    """
                    insert into investigations (exception_id, status, recommendation, completed_at)
                    values (%s, 'COMPLETED', 'HUMAN_REVIEW', now())
                    returning id
                    """,
                    (exception_id,),
                )
                investigation_id = str(cur.fetchone()[0])
                conn.commit()

            client = TestClient(app)
            client.post(
                "/auth/register",
                json={"email": ANALYST_EMAIL, "password": ANALYST_PASSWORD},
            )
            login = client.post(
                "/auth/login",
                json={"email": ANALYST_EMAIL, "password": ANALYST_PASSWORD},
            )
            assert login.status_code == 200
            assert login.json()["role"] == "analyst"

            # Read + investigate: allowed for an Analyst.
            assert client.get(f"/investigations/{investigation_id}").status_code == 200
            assert (
                client.post(
                    "/investigations", json={"exception_id": exception_id}
                ).status_code
                == 200
            )

            # Decide: reviewer-only, and refused server-side.
            assert (
                client.post(
                    f"/investigations/{investigation_id}/resolve", json={"note": "nope"}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    f"/investigations/{investigation_id}/escalate", json={"note": "nope"}
                ).status_code
                == 403
            )

            with connect() as check_conn:
                with check_conn.cursor() as check_cur:
                    assert (
                        get_investigation(check_cur, investigation_id)["human_decision"]
                        is None
                    ), "a refused request must not have changed the record"
        finally:
            with conn.cursor() as cur:
                _cleanup(cur, [OVERDUE])
                _cleanup_user(cur, ANALYST_EMAIL)
            conn.commit()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
