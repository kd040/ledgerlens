from typing import Any


def get_payment(cur, payment_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        select
            p.id,
            p.external_payment_id,
            p.order_id,
            p.amount,
            p.currency,
            p.status,
            p.created_at
        from payments p
        where p.id = %s
        """,
        (payment_id,),
    )

    row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": str(row[0]),
        "external_payment_id": row[1],
        "order_id": str(row[2]) if row[2] is not None else None,
        "amount": str(row[3]),
        "currency": row[4],
        "status": row[5],
        "created_at": row[6].isoformat(),
    }
