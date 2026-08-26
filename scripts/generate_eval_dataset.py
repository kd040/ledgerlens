"""Generate the buildathon evaluation dataset.

Deterministically generates PAY-006..PAY-100 (95 records) on top of the
existing PAY-001..PAY-005 regression cases, inserts the source financial
data (payments/settlements/fees/taxes/adjustments only -- the fields
reconcile_payments() actually reads), and writes the known ground truth
for all 100 records to data/eval_ground_truth.json.

Fixed seed (42): re-running this script produces the same logical
dataset every time. Inserts are idempotent (unique external ids for
payments/settlements; existence-checked fee/tax/adjustment rows), and
PAY-001..PAY-005 are never touched.

Usage: python scripts/generate_eval_dataset.py
"""

import json
import os
import random
from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

SEED = 42
START_INDEX = 6
CATEGORY_COUNTS = {
    "RECONCILED": 69,
    "EX01": 13,
    "EX02": 7,
    "EX03": 6,
}

# Known ground truth for the existing regression cases (Day 1 seed data).
KNOWN_GROUND_TRUTH = [
    {
        "payment_reference": "PAY-001",
        "expected_state": "RECONCILED",
        "expected_category": None,
        "expected_financial_impact": "0.00",
        "expected_investigation_category": None,
    },
    {
        "payment_reference": "PAY-002",
        "expected_state": "EX01",
        "expected_category": "Amount Mismatch",
        "expected_financial_impact": "50.00",
        "expected_investigation_category": "Amount Mismatch",
    },
    {
        "payment_reference": "PAY-003",
        "expected_state": "EX02",
        "expected_category": "Missing Record",
        "expected_financial_impact": "1500.00",
        "expected_investigation_category": "Missing Record",
    },
    {
        "payment_reference": "PAY-004",
        "expected_state": "EX03",
        "expected_category": "Duplicate Record",
        "expected_financial_impact": "3000.00",
        "expected_investigation_category": "Duplicate Record",
    },
    {
        "payment_reference": "PAY-005",
        "expected_state": "EX01",
        "expected_category": "Amount Mismatch",
        "expected_financial_impact": "1235.00",
        "expected_investigation_category": "Amount Mismatch",
    },
]


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_category_sequence(rng: random.Random) -> list[str]:
    categories = []
    for category, count in CATEGORY_COUNTS.items():
        categories.extend([category] * count)
    rng.shuffle(categories)
    return categories


def upsert_payment(cur, ref: str, gross: Decimal) -> None:
    cur.execute(
        """
        insert into payments (
            external_payment_id, amount, currency, status, method, captured_at
        )
        values (%s, %s, 'INR', 'CAPTURED', 'UPI', now())
        on conflict (external_payment_id) do nothing
        """,
        (ref, gross),
    )


def upsert_settlement(
    cur, settlement_ref: str, amount: Decimal, payment_ref: str
) -> None:
    cur.execute(
        """
        insert into settlements (
            external_settlement_id, settlement_amount, currency, status,
            settlement_date, reference
        )
        values (%s, %s, 'INR', 'SETTLED', now(), %s)
        on conflict (external_settlement_id) do nothing
        """,
        (settlement_ref, amount, payment_ref),
    )


def upsert_settlement_charge(
    cur, table: str, type_column: str, settlement_ref: str,
    amount: Decimal, charge_type: str,
) -> None:
    cur.execute(
        f"""
        insert into {table} (settlement_id, amount, currency, {type_column})
        select id, %s, 'INR', %s
        from settlements
        where external_settlement_id = %s
          and not exists (
              select 1 from {table} c
              where c.settlement_id = settlements.id
                and c.{type_column} = %s
          )
        """,
        (amount, charge_type, settlement_ref, charge_type),
    )


def generate_records(rng: random.Random) -> Iterator[tuple[dict, dict]]:
    categories = build_category_sequence(rng)
    ground_truth = []

    for offset, category in enumerate(categories):
        idx = START_INDEX + offset
        ref = f"PAY-{idx:03d}"
        settlement_ref = f"SET-{idx:03d}"

        gross = money(rng.uniform(500.0, 5000.0))
        fee = money(float(gross) * rng.uniform(0.01, 0.03))
        tax = (
            money(float(gross) * rng.uniform(0.0, 0.02))
            if rng.random() < 0.3
            else Decimal("0.00")
        )
        adjustment = (
            money(rng.uniform(5.0, 50.0) * rng.choice([1, -1]))
            if rng.random() < 0.1
            else Decimal("0.00")
        )
        expected = gross - fee - tax + adjustment

        record = {
            "payment_reference": ref,
            "gross_amount": gross,
            "fee": fee,
            "tax": tax,
            "adjustment": adjustment,
            "expected_amount": expected,
            "category": category,
            "settlements": [],
        }

        if category == "RECONCILED":
            record["settlements"] = [(settlement_ref, expected)]
            truth = {
                "expected_state": "RECONCILED",
                "expected_category": None,
                "expected_financial_impact": "0.00",
                "expected_investigation_category": None,
            }

        elif category == "EX01":
            max_mismatch = max(20.0, float(expected) * 0.4)
            mismatch = money(rng.uniform(10.0, max_mismatch))
            observed = expected - mismatch
            if observed <= Decimal("0.00"):
                observed = expected / 2
                mismatch = expected - observed
            record["settlements"] = [(settlement_ref, observed)]
            truth = {
                "expected_state": "EX01",
                "expected_category": "Amount Mismatch",
                "expected_financial_impact": str(mismatch),
                "expected_investigation_category": "Amount Mismatch",
            }

        elif category == "EX02":
            record["settlements"] = []
            truth = {
                "expected_state": "EX02",
                "expected_category": "Missing Record",
                "expected_financial_impact": str(gross),
                "expected_investigation_category": "Missing Record",
            }

        else:  # EX03
            dup_count = 3 if rng.random() < 0.2 else 2
            suffixes = "ABC"[:dup_count]
            record["settlements"] = [
                (f"{settlement_ref}-{suffix}", expected) for suffix in suffixes
            ]
            truth = {
                "expected_state": "EX03",
                "expected_category": "Duplicate Record",
                "expected_financial_impact": str(gross),
                "expected_investigation_category": "Duplicate Record",
            }

        truth["payment_reference"] = ref
        ground_truth.append(truth)

        yield record, truth


def insert_record(cur, record: dict) -> None:
    ref = record["payment_reference"]

    upsert_payment(cur, ref, record["gross_amount"])

    for settlement_ref, amount in record["settlements"]:
        upsert_settlement(cur, settlement_ref, amount, ref)

    # Fees/taxes/adjustments only matter for RECONCILED/EX01 -- the
    # reconciliation engine short-circuits before reading them for
    # duplicate settlements, and EX02 has no settlement to attach to.
    if record["category"] in ("RECONCILED", "EX01"):
        settlement_ref = record["settlements"][0][0]
        upsert_settlement_charge(
            cur, "fees", "fee_type", settlement_ref,
            record["fee"], "PROCESSING_FEE",
        )
        if record["tax"] != Decimal("0.00"):
            upsert_settlement_charge(
                cur, "taxes", "tax_type", settlement_ref,
                record["tax"], "GST",
            )
        if record["adjustment"] != Decimal("0.00"):
            upsert_settlement_charge(
                cur, "adjustments", "adjustment_type", settlement_ref,
                record["adjustment"], "MANUAL_ADJUSTMENT",
            )


def main() -> None:
    database_url = os.getenv("SUPABASE_DB_URL")
    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL is not configured")

    rng = random.Random(SEED)

    generated_truth = []

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            for record, truth in generate_records(rng):
                insert_record(cur, record)
                generated_truth.append(truth)
        conn.commit()

    all_ground_truth = KNOWN_GROUND_TRUTH + generated_truth
    all_ground_truth.sort(key=lambda row: row["payment_reference"])

    output_path = PROJECT_ROOT / "data" / "eval_ground_truth.json"
    output_path.write_text(
        json.dumps(all_ground_truth, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Generated {len(generated_truth)} synthetic records (PAY-006..PAY-100).")
    print(f"Ground truth written for {len(all_ground_truth)} total records: {output_path}")


if __name__ == "__main__":
    main()
