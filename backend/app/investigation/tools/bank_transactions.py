from typing import Any


def get_bank_transactions(
    cur,
    settlement_reference: str,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        select
            id,
            transaction_date,
            amount,
            currency,
            transaction_type,
            reference
        from bank_transactions
        where reference = %s
        order by transaction_date, id
        """,
        (settlement_reference,),
    )

    rows = cur.fetchall()

    return [
        {
            "id": str(row[0]),
            "transaction_date": row[1].isoformat(),
            "amount": str(row[2]),
            "currency": row[3],
            "transaction_type": row[4],
            "reference": row[5],
        }
        for row in rows
    ]
