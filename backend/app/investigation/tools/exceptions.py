from typing import Any


def get_exception(cur, exception_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        select
            id,
            exception_code,
            category,
            description,
            financial_impact,
            status,
            created_at,
            updated_at
        from exceptions
        where id = %s
        """,
        (exception_id,),
    )

    row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": str(row[0]),
        "exception_code": row[1],
        "category": row[2],
        "description": row[3],
        "financial_impact": str(row[4]) if row[4] is not None else None,
        "status": row[5],
        "created_at": row[6].isoformat(),
        "updated_at": row[7].isoformat(),
    }
