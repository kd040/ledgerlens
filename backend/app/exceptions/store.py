from typing import Any

# Each exception has at most one investigation in practice (create_investigation
# is idempotent per exception_id), so the left join never fans out a row.
_EXCEPTION_QUERY = """
    select
        e.id,
        e.exception_code,
        e.category,
        e.description,
        e.financial_impact,
        e.status,
        e.created_at,
        e.updated_at,
        i.id,
        i.status,
        i.recommendation
    from exceptions e
    left join investigations i on i.exception_id = e.id
"""


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "exception_code": row[1],
        "category": row[2],
        "description": row[3],
        "financial_impact": str(row[4]) if row[4] is not None else None,
        "status": row[5],
        "created_at": row[6].isoformat(),
        "updated_at": row[7].isoformat(),
        "investigation_id": str(row[8]) if row[8] is not None else None,
        "investigation_status": row[9],
        "investigation_recommendation": row[10],
    }


def list_exceptions(cur) -> list[dict[str, Any]]:
    cur.execute(_EXCEPTION_QUERY + " order by e.created_at desc")
    return [_row_to_dict(row) for row in cur.fetchall()]


def get_exception(cur, exception_id: str) -> dict[str, Any] | None:
    cur.execute(_EXCEPTION_QUERY + " where e.id = %s", (exception_id,))
    row = cur.fetchone()
    return _row_to_dict(row) if row is not None else None
