from typing import Any

from app.investigation.services.hypotheses import HypothesisResult


def store_hypotheses(
    cur,
    investigation_id: str,
    results: list[HypothesisResult],
) -> None:
    for result in results:
        cur.execute(
            """
            insert into investigation_hypotheses (
                investigation_id,
                hypothesis,
                status,
                confidence,
                reasoning
            )
            values (%s, %s, %s, %s, %s)
            """,
            (
                investigation_id,
                result.hypothesis,
                result.status,
                result.confidence,
                result.reasoning,
            ),
        )


def list_hypotheses(cur, investigation_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select id, hypothesis, status, confidence, reasoning, created_at
        from investigation_hypotheses
        where investigation_id = %s
        order by created_at asc
        """,
        (investigation_id,),
    )

    return [
        {
            "id": str(row[0]),
            "hypothesis": row[1],
            "status": row[2],
            "confidence": str(row[3]) if row[3] is not None else None,
            "reasoning": row[4],
            "created_at": row[5].isoformat(),
        }
        for row in cur.fetchall()
    ]
