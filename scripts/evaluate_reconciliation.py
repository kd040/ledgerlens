"""Buildathon evaluation: run reconciliation + investigation against the
synthetic dataset and score actual results against known ground truth.

Reuses the existing reconciliation engine and investigation runners
directly (no HTTP layer, no new production logic). Prints a concise
metrics report: detection accuracy, false positives/negatives, per-
category recall, financial impact, investigation outcomes, throughput.

Usage: python scripts/evaluate_reconciliation.py
"""

import json
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
load_dotenv(PROJECT_ROOT / ".env")

from app.investigation.runners.deterministic import connect  # noqa: E402
from app.investigation.services.investigation_store import (  # noqa: E402
    create_investigation,
)
from app.reconciliation.engine import reconcile_payments  # noqa: E402
from app.investigation.router import CATEGORY_RUNNERS  # noqa: E402


GROUND_TRUTH_PATH = PROJECT_ROOT / "data" / "eval_ground_truth.json"


def load_ground_truth() -> dict[str, dict]:
    records = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    return {record["payment_reference"]: record for record in records}


def find_exception_id(cur, payment_reference: str) -> tuple[str, str] | None:
    """Returns (exception_id, category) for the OPEN exception mentioning
    this payment reference, if any."""
    cur.execute(
        """
        select id, category
        from exceptions
        where status = 'OPEN'
          and description like %s
        order by created_at desc
        limit 1
        """,
        (f"%{payment_reference}%",),
    )
    row = cur.fetchone()
    return (str(row[0]), row[1]) if row else None


def main() -> None:
    ground_truth = load_ground_truth()

    start = time.perf_counter()

    results = reconcile_payments()
    actual_by_reference = {row["payment"]: row for row in results}

    investigation_outcomes = {"COMPLETED": 0, "ESCALATED": 0}
    recommendation_counts: dict[str, int] = {}

    with connect() as conn:
        with conn.cursor() as cur:
            for reference, truth in ground_truth.items():
                if truth["expected_state"] == "RECONCILED":
                    continue

                found = find_exception_id(cur, reference)
                if found is None:
                    continue

                exception_id, category = found
                runner = CATEGORY_RUNNERS.get(category)
                if runner is None:
                    continue

                investigation = create_investigation(cur, exception_id)
                conn.commit()

                try:
                    outcome = runner(investigation["id"], exception_id)
                except ValueError:
                    continue

                investigation_outcomes[outcome["status"]] = (
                    investigation_outcomes.get(outcome["status"], 0) + 1
                )
                recommendation_counts[outcome["recommendation"]] = (
                    recommendation_counts.get(outcome["recommendation"], 0) + 1
                )

    elapsed = time.perf_counter() - start

    # --------------------------------------------------
    # Score actual vs. ground truth
    # --------------------------------------------------

    total = len(ground_truth)
    correct = 0
    false_positives = 0
    false_negatives = 0
    per_category = {
        "EX01": {"expected": 0, "detected": 0},
        "EX02": {"expected": 0, "detected": 0},
        "EX03": {"expected": 0, "detected": 0},
    }
    financial_impact_identified = 0.0
    reconciled_count = 0
    exception_count = 0

    for reference, truth in ground_truth.items():
        expected_state = truth["expected_state"]
        actual = actual_by_reference.get(reference)
        actual_state = actual["status"] if actual else "RECONCILED"

        if expected_state == "RECONCILED":
            reconciled_count += 1
        else:
            exception_count += 1
            per_category[expected_state]["expected"] += 1

        if actual_state == expected_state:
            correct += 1
            if expected_state != "RECONCILED":
                per_category[expected_state]["detected"] += 1
                financial_impact_identified += float(
                    truth["expected_financial_impact"]
                )
        elif expected_state == "RECONCILED" and actual_state != "RECONCILED":
            false_positives += 1
        elif expected_state != "RECONCILED" and actual_state == "RECONCILED":
            false_negatives += 1
        # else: detected an exception but classified it under the wrong
        # category -- counted as neither correct nor FP/FN here since it
        # is a partial detection, not a miss.

    detection_accuracy = (correct / total) * 100 if total else 0.0
    throughput = total / elapsed if elapsed > 0 else float("inf")

    print(f"Records processed: {total}")
    print(f"Reconciled: {reconciled_count}")
    print(f"Exceptions: {exception_count}")
    print()
    print(f"Detection accuracy: {detection_accuracy:.1f}%")
    print(f"False positives: {false_positives}")
    print(f"False negatives: {false_negatives}")
    print()
    for code in ("EX01", "EX02", "EX03"):
        stats = per_category[code]
        print(f"{code} detected: {stats['detected']}/{stats['expected']}")
    print()
    print(f"Financial impact identified: Rs {financial_impact_identified:,.2f}")
    print()
    print(f"Investigations completed: {investigation_outcomes.get('COMPLETED', 0)}")
    print(f"Human review required: {recommendation_counts.get('HUMAN_REVIEW', 0)}")
    print(f"Escalated: {investigation_outcomes.get('ESCALATED', 0)}")
    print()
    print(f"Processing time: {elapsed:.2f} seconds")
    print(f"Throughput: {throughput:.1f} records/sec")


if __name__ == "__main__":
    main()
