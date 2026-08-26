from typing import Any


def get_settlements(cur, payment_reference: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select
            s.id,
            s.external_settlement_id,
            s.settlement_amount,
            s.currency,
            s.status,
            s.settlement_date,
            s.reference
        from settlements s
        where s.reference = %s
        order by s.external_settlement_id
        """,
        (payment_reference,),
    )

    rows = cur.fetchall()

    return [
        {
            "id": str(row[0]),
            "external_settlement_id": row[1],
            "settlement_amount": str(row[2]),
            "currency": row[3],
            "status": row[4],
            "settlement_date": row[5].isoformat(),
            "reference": row[6],
        }
        for row in rows
    ]
