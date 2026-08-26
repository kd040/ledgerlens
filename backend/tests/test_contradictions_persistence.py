"""DB-integration check for contradiction persistence + listing.

Creates a throwaway exception/investigation, exercises
record_contradiction / list_contradictions against the real database
(no test DB is configured for this project), then cleans up.
Run directly: python backend/tests/test_contradictions_persistence.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.investigation.runners.deterministic import connect
from app.investigation.services.contradictions import (
    list_contradictions,
    record_contradiction,
)


def test_list_contradictions_empty_then_populated():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into exceptions (
                    exception_code, category, description, financial_impact, status
                )
                values (
                    'EX99', 'Test Category',
                    'Throwaway exception for contradiction persistence test.',
                    1.00, 'OPEN'
                )
                returning id
                """
            )
            exception_id = cur.fetchone()[0]

            cur.execute(
                """
                insert into investigations (exception_id, status)
                values (%s, 'IN_PROGRESS')
                returning id
                """,
                (exception_id,),
            )
            investigation_id = str(cur.fetchone()[0])

            try:
                assert list_contradictions(cur, investigation_id) == []

                record_contradiction(
                    cur, investigation_id, "Test contradiction description."
                )

                results = list_contradictions(cur, investigation_id)
                assert len(results) == 1
                assert results[0]["description"] == (
                    "Test contradiction description."
                )
                assert results[0]["evidence_id"] is None
            finally:
                cur.execute(
                    "delete from investigations where id = %s",
                    (investigation_id,),
                )
                cur.execute(
                    "delete from exceptions where id = %s", (exception_id,)
                )
                conn.commit()


if __name__ == "__main__":
    test_list_contradictions_empty_then_populated()
    print("ok  test_list_contradictions_empty_then_populated")
    print("\n1 passed")
