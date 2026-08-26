from typing import Any


def record_contradiction(
    cur,
    investigation_id: str,
    description: str,
) -> str:
    cur.execute(
        """
        insert into investigation_contradictions (
            investigation_id,
            description
        )
        values (%s, %s)
        returning id
        """,
        (
            investigation_id,
            description,
        ),
    )

    return str(cur.fetchone()[0])


def list_contradictions(cur, investigation_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select id, description, evidence_id, created_at
        from investigation_contradictions
        where investigation_id = %s
        order by created_at asc
        """,
        (investigation_id,),
    )

    return [
        {
            "id": str(row[0]),
            "description": row[1],
            "evidence_id": str(row[2]) if row[2] is not None else None,
            "created_at": row[3].isoformat(),
        }
        for row in cur.fetchall()
    ]
