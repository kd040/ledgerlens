"""The existing 100-record demo/evaluation dataset as a data source.

It's a fixed deterministic benchmark (see scripts/generate_eval_dataset.py),
not a live-fetched period, so the requested date range is accepted for a
uniform call signature but not applied. payment_ids is scoped to just the
PAY-* rows (not None/unrestricted) so this source stays an isolated,
fixed benchmark even though other sources -- e.g. razorpay_test -- write
unrelated rows into the same shared payments table.
"""

import time
from datetime import datetime

from app.investigation.runners.deterministic import connect


def run_demo_source(from_dt: datetime, to_dt: datetime) -> dict:
    started = time.perf_counter()

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select external_payment_id
                from payments
                where external_payment_id like %s
                order by external_payment_id
                """,
                ("PAY-%",),
            )
            payment_ids = [row[0] for row in cur.fetchall()]

    return {
        "payments_fetched": len(payment_ids),
        "recon_lines_fetched": None,
        "settlements_normalized": None,
        "payment_ids": payment_ids,
        "settlement_pending_days": None,
        "duration_seconds": time.perf_counter() - started,
    }
