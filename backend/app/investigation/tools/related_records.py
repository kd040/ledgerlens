from typing import Any


def find_related_records(
    cur,
    payment_reference: str,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "settlements": [],
        "refunds": [],
        "bank_transactions": [],
    }

    cur.execute(
        """
        select
            id,
            external_settlement_id,
            settlement_amount,
            currency,
            status,
            settlement_date,
            reference
        from settlements
        where reference = %s
        order by external_settlement_id
        """,
        (payment_reference,),
    )

    for row in cur.fetchall():
        result["settlements"].append(
            {
                "id": str(row[0]),
                "external_settlement_id": row[1],
                "settlement_amount": str(row[2]),
                "currency": row[3],
                "status": row[4],
                "settlement_date": row[5].isoformat(),
                "reference": row[6],
            }
        )

    cur.execute(
        """
        select
            r.id,
            r.amount,
            r.currency,
            r.status,
            r.created_at
        from refunds r
        join payments p on p.id = r.payment_id
        where p.external_payment_id = %s
        order by r.created_at
        """,
        (payment_reference,),
    )

    for row in cur.fetchall():
        result["refunds"].append(
            {
                "id": str(row[0]),
                "amount": str(row[1]),
                "currency": row[2],
                "status": row[3],
                "created_at": row[4].isoformat(),
            }
        )

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
        (payment_reference,),
    )

    for row in cur.fetchall():
        result["bank_transactions"].append(
            {
                "id": str(row[0]),
                "transaction_date": row[1].isoformat(),
                "amount": str(row[2]),
                "currency": row[3],
                "transaction_type": row[4],
                "reference": row[5],
            }
        )

    return result
