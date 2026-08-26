from typing import Any


def create_investigation(cur, exception_id: str) -> dict[str, Any]:
    cur.execute(
        """
        select id, exception_id, status
        from investigations
        where exception_id = %s
        """,
        (exception_id,),
    )

    existing = cur.fetchone()

    if existing is not None:
        return {
            "id": str(existing[0]),
            "exception_id": str(existing[1]),
            "status": existing[2],
        }

    cur.execute(
        """
        select 1 from exceptions where id = %s
        """,
        (exception_id,),
    )

    if cur.fetchone() is None:
        raise ValueError(f"Exception {exception_id} was not found.")

    cur.execute(
        """
        insert into investigations (exception_id, status)
        values (%s, 'IN_PROGRESS')
        returning id, exception_id, status
        """,
        (exception_id,),
    )

    row = cur.fetchone()

    return {
        "id": str(row[0]),
        "exception_id": str(row[1]),
        "status": row[2],
    }


def list_investigations(cur) -> list[dict[str, Any]]:
    cur.execute(
        """
        select
            i.id,
            i.exception_id,
            e.exception_code,
            e.category,
            i.root_cause,
            i.confidence,
            i.recommendation,
            i.status,
            i.started_at,
            i.completed_at
        from investigations i
        join exceptions e on e.id = i.exception_id
        order by i.started_at desc
        """
    )

    rows = cur.fetchall()

    return [
        {
            "id": str(row[0]),
            "exception_id": str(row[1]),
            "exception_code": row[2],
            "category": row[3],
            "root_cause": row[4],
            "confidence": str(row[5]) if row[5] is not None else None,
            "recommendation": row[6],
            "status": row[7],
            "started_at": row[8].isoformat(),
            "completed_at": row[9].isoformat() if row[9] is not None else None,
        }
        for row in rows
    ]


def get_investigation(cur, investigation_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        select
            i.id,
            i.exception_id,
            e.exception_code,
            e.category,
            e.description,
            e.financial_impact,
            i.root_cause,
            i.confidence,
            i.recommendation,
            i.status,
            i.financial_analysis,
            i.started_at,
            i.completed_at
        from investigations i
        join exceptions e on e.id = i.exception_id
        where i.id = %s
        """,
        (investigation_id,),
    )

    row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": str(row[0]),
        "exception_id": str(row[1]),
        "exception_code": row[2],
        "category": row[3],
        "description": row[4],
        "financial_impact": str(row[5]) if row[5] is not None else None,
        "root_cause": row[6],
        "confidence": str(row[7]) if row[7] is not None else None,
        "recommendation": row[8],
        "status": row[9],
        "financial_analysis": row[10],
        "started_at": row[11].isoformat(),
        "completed_at": row[12].isoformat() if row[12] is not None else None,
    }
