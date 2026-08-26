from typing import Any


def get_taxes(cur, settlement_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select
            id,
            settlement_id,
            amount,
            currency,
            tax_type
        from taxes
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
            "tax_type": row[4],
        }
        for row in rows
    ]
