import json
from typing import Any


def record_tool_call(
    cur,
    investigation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any],
) -> str:
    cur.execute(
        """
        insert into investigation_tool_calls (
            investigation_id,
            tool_name,
            arguments,
            result
        )
        values (%s, %s, %s, %s)
        returning id
        """,
        (
            investigation_id,
            tool_name,
            json.dumps(arguments),
            json.dumps(result),
        ),
    )

    return str(cur.fetchone()[0])


def list_tool_calls(cur, investigation_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select id, tool_name, arguments, result, called_at
        from investigation_tool_calls
        where investigation_id = %s
        order by called_at asc
        """,
        (investigation_id,),
    )

    return [
        {
            "id": str(row[0]),
            "tool_name": row[1],
            "arguments": row[2],
            "result": row[3],
            "called_at": row[4].isoformat(),
        }
        for row in cur.fetchall()
    ]


def record_evidence(
    cur,
    investigation_id: str,
    evidence_type: str,
    record_type: str,
    record_id: str | None,
    description: str,
) -> str:
    cur.execute(
        """
        insert into investigation_evidence (
            investigation_id,
            evidence_type,
            record_type,
            record_id,
            description
        )
        values (%s, %s, %s, %s, %s)
        returning id
        """,
        (
            investigation_id,
            evidence_type,
            record_type,
            record_id,
            description,
        ),
    )

    return str(cur.fetchone()[0])


def list_evidence(cur, investigation_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select id, evidence_type, record_type, record_id, description, created_at
        from investigation_evidence
        where investigation_id = %s
        order by created_at asc
        """,
        (investigation_id,),
    )

    return [
        {
            "id": str(row[0]),
            "evidence_type": row[1],
            "record_type": row[2],
            "record_id": str(row[3]) if row[3] is not None else None,
            "description": row[4],
            "created_at": row[5].isoformat(),
        }
        for row in cur.fetchall()
    ]
