"""Fetches Razorpay Test Mode data for a requested period, normalizes it,
and persists it idempotently into the existing payments/settlements/
fees/taxes tables -- so the unmodified reconciliation engine can operate
on it exactly as it does on the demo dataset.

Timezone: the requested [from, to) window is interpreted in whatever
timezone the caller's datetimes carry (IST, +05:30, at the router
layer); Settlement Recon Details is fetched per IST calendar day since
that's the granularity Razorpay's own API uses for that endpoint.
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone

from app.datasources.razorpay.client import RazorpayClient
from app.datasources.razorpay.normalize import (
    normalize_payment,
    normalize_settlement_recon_line,
)
from app.investigation.runners.deterministic import connect

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
PAYMENTS_PAGE_SIZE = 100
RECON_PAGE_SIZE = 1000

# Razorpay's own documented default settlement cycle for domestic (INR)
# payments is T+2 working days (T = capture date) -- see
# https://razorpay.com/docs/payments/settlements/. A payment younger
# than this has no settlement yet for a normal, expected reason, so
# reconcile_payments() should treat it as SETTLEMENT_PENDING rather
# than EX02 Missing Record.
#
# ponytail: "working days" excludes Sundays, the 2nd/4th Saturday, and
# bank holidays; this uses plain calendar days as an approximation, so
# a payment captured right before a long weekend could still show EX02
# a little before Razorpay actually settles it. Upgrade to a real
# working-day calendar if that false positive shows up in practice.
SETTLEMENT_PENDING_DAYS = 2


def _paginate(fetch_page, page_size: int) -> list[dict]:
    items: list[dict] = []
    skip = 0
    while True:
        page = fetch_page(count=page_size, skip=skip)
        batch = page.get("items", [])
        items.extend(batch)
        if len(batch) < page_size:
            break
        skip += page_size
    return items


def _ist_days_in_range(start: datetime, end: datetime) -> list[date]:
    current = start.astimezone(IST).date()
    last = end.astimezone(IST).date()
    days = []
    while current <= last:
        days.append(current)
        current += timedelta(days=1)
    return days


def _insert_payment(cur, payment) -> None:
    cur.execute(
        """
        insert into payments (
            external_payment_id, amount, currency, status, method, created_at
        )
        values (%s, %s, %s, %s, %s, %s)
        on conflict (external_payment_id) do nothing
        """,
        (
            payment["external_payment_id"],
            payment["amount"],
            payment["currency"],
            payment["status"],
            payment["method"],
            payment["created_at"],
        ),
    )


def _insert_settlement(cur, settlement) -> None:
    cur.execute(
        """
        insert into settlements (
            external_settlement_id, settlement_amount, currency, status,
            settlement_date, reference
        )
        values (%s, %s, 'INR', %s, %s, %s)
        on conflict (external_settlement_id) do nothing
        """,
        (
            settlement["external_settlement_id"],
            settlement["settlement_amount"],
            settlement["status"],
            settlement["settlement_date"],
            settlement["payment_reference"],
        ),
    )

    if settlement["fee_amount"] > 0:
        cur.execute(
            """
            insert into fees (settlement_id, amount, currency, fee_type)
            select id, %s, 'INR', 'RAZORPAY_FEE'
            from settlements
            where external_settlement_id = %s
              and not exists (
                  select 1 from fees f
                  where f.settlement_id = settlements.id
                    and f.fee_type = 'RAZORPAY_FEE'
              )
            """,
            (settlement["fee_amount"], settlement["external_settlement_id"]),
        )

    if settlement["tax_amount"] > 0:
        cur.execute(
            """
            insert into taxes (settlement_id, amount, currency, tax_type)
            select id, %s, 'INR', 'GST'
            from settlements
            where external_settlement_id = %s
              and not exists (
                  select 1 from taxes t
                  where t.settlement_id = settlements.id
                    and t.tax_type = 'GST'
              )
            """,
            (settlement["tax_amount"], settlement["external_settlement_id"]),
        )


def run_razorpay_source(from_dt: datetime, to_dt: datetime) -> dict:
    started = time.perf_counter()
    client = RazorpayClient()

    raw_payments = _paginate(
        lambda count, skip: client.list_payments(
            from_ts=int(from_dt.timestamp()), to_ts=int(to_dt.timestamp()),
            count=count, skip=skip,
        ),
        PAYMENTS_PAGE_SIZE,
    )
    payments = [normalize_payment(p) for p in raw_payments]

    days = _ist_days_in_range(from_dt, to_dt)
    raw_recon: list[dict] = []
    for day in days:
        raw_recon.extend(
            _paginate(
                lambda count, skip, day=day: client.list_settlement_recon(
                    year=day.year, month=day.month, day=day.day,
                    count=count, skip=skip,
                ),
                RECON_PAGE_SIZE,
            )
        )

    settlements = [
        s for s in (normalize_settlement_recon_line(item) for item in raw_recon)
        if s is not None
    ]

    payment_ids = [p["external_payment_id"] for p in payments]

    with connect() as conn:
        with conn.cursor() as cur:
            for payment in payments:
                _insert_payment(cur, payment)
            for settlement in settlements:
                _insert_settlement(cur, settlement)
        conn.commit()

    duration = time.perf_counter() - started

    logger.info(
        "razorpay_test source: range=%s..%s days=%d payments_fetched=%d "
        "recon_lines_fetched=%d settlements_normalized=%d duration=%.2fs",
        from_dt.isoformat(), to_dt.isoformat(), len(days),
        len(payments), len(raw_recon), len(settlements), duration,
    )

    return {
        "payments_fetched": len(payments),
        "recon_lines_fetched": len(raw_recon),
        "settlements_normalized": len(settlements),
        "payment_ids": payment_ids,
        "settlement_pending_days": SETTLEMENT_PENDING_DAYS,
        "duration_seconds": duration,
    }
