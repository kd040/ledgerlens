"""DB-integration check for GET /exceptions/{id}/duplicate-settlements --
throwaway TEST-DUPSETL-* rows, cleaned up after itself.

Run directly: python backend/tests/test_duplicate_settlements_endpoint.py
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.exceptions.router import get_exception_duplicate_settlements
from app.investigation.runners.deterministic import connect


def test_duplicate_settlements_returns_all_underlying_settlements():
    payment_ref = "PAY-TESTDUPSETL001"
    settlement_refs = ["TEST-DUPSETL-SETL-A", "TEST-DUPSETL-SETL-B"]

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into payments (external_payment_id, amount, currency, status, method, created_at)
                values (%s, %s, 'INR', 'captured', 'card', %s)
                returning id
                """,
                (payment_ref, Decimal("970.00"), datetime.now(timezone.utc)),
            )
            cur.execute(
                """
                insert into settlements (external_settlement_id, settlement_amount, currency, status, settlement_date, reference)
                values (%s, %s, 'INR', 'SETTLED', now(), %s)
                """,
                (settlement_refs[0], Decimal("970.00"), payment_ref),
            )
            cur.execute(
                """
                insert into settlements (external_settlement_id, settlement_amount, currency, status, settlement_date, reference)
                values (%s, %s, 'INR', 'SETTLED', now(), %s)
                """,
                (settlement_refs[1], Decimal("970.00"), payment_ref),
            )
            cur.execute(
                """
                insert into exceptions (exception_code, category, description, financial_impact, status)
                values ('EX03', 'Duplicate Record', %s, %s, 'OPEN')
                returning id
                """,
                (f"Payment {payment_ref} has 2 matching settlements.", Decimal("970.00")),
            )
            exception_id = str(cur.fetchone()[0])
            conn.commit()

            try:
                result = get_exception_duplicate_settlements(exception_id)

                assert result["payment"] == payment_ref
                assert len(result["settlements"]) == 2
                returned_refs = {s["external_settlement_id"] for s in result["settlements"]}
                assert returned_refs == set(settlement_refs)
                for settlement in result["settlements"]:
                    assert settlement["settlement_amount"] == "970.00"
                    assert settlement["status"] == "SETTLED"
                    assert settlement["currency"] == "INR"
                    assert "settlement_date" in settlement
            finally:
                cur.execute("delete from exceptions where id = %s", (exception_id,))
                cur.execute(
                    "delete from settlements where external_settlement_id = any(%s)",
                    (settlement_refs,),
                )
                cur.execute(
                    "delete from payments where external_payment_id = %s", (payment_ref,)
                )
                conn.commit()


if __name__ == "__main__":
    test_duplicate_settlements_returns_all_underlying_settlements()
    print("ok")
