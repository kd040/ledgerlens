from typing import Any


def get_adjustments(cur, settlement_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select
            id,
            settlement_id,
            amount,
            currency,
            adjustment_type,
            reason
        from adjustments
        where settlement_id = %s
        order by id
        """,
        (settlement_id,),
    )

    rows = cur.fetchall()

    return [
        {
            "id": str(row[0]),
            "settlement_id": str(row[1]),
            "amount": str(row[2]),
            "currency": row[3],
            "adjustment_type": row[4],
            "reason": row[5],
        }
        for row in rows
    ]
