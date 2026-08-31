import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from dotenv import load_dotenv


load_dotenv()


# Every payment status this engine knows how to reason about, compared
# case-insensitively (the demo dataset stores 'CAPTURED', Razorpay
# reports 'captured').
#
# SETTLEABLE: the payment became money owed to the merchant, so a
# settlement is genuinely expected and its absence is an EX02.
#
# NON_SETTLEABLE: the payment never became money owed -- started,
# held, or declined -- so no settlement is ever due and calling it a
# "Missing Record" would invent an exception out of nothing.
#
# Anything in neither set is UNKNOWN. It is deliberately NOT assumed to
# be either: a status this engine has never seen might be settleable
# (silently suppressing a real EX02) or might not be (inventing a false
# one). Both guesses are wrong in a way that costs money, so an unknown
# status becomes its own visible, unreconciled outcome that a human has
# to classify -- see UNKNOWN_STATUS below.
SETTLEABLE_PAYMENT_STATUSES = {"captured", "refunded"}
NON_SETTLEABLE_PAYMENT_STATUSES = {"created", "authorized", "failed"}

# Indian banking time. Settlement cycles are quoted in banking days, so
# whether a given instant falls on a working day is an IST question, not
# a UTC one -- a payment at 02:00 IST Monday is 20:30 UTC Sunday, and
# counting that as a weekend would push its deadline out by a day.
_IST = timezone(timedelta(hours=5, minutes=30))


def add_business_days(start: datetime, days: int) -> datetime:
    """`start` plus `days` banking days, weekends excluded.

    Friday + 2 -> Tuesday; Monday + 2 -> Wednesday. Saturday/Sunday are
    skipped rather than counted.

    ponytail: weekends only -- bank and exchange holidays are NOT
    modelled, because this project has no holiday calendar and inventing
    one (or taking a dependency for it) would be guessing at a
    jurisdiction. A payment captured before a long public holiday can
    therefore be flagged EX02 slightly early. Add a real holiday
    calendar here if that false positive shows up in practice.
    """
    if days <= 0:
        return start

    result = start
    remaining = days
    while remaining > 0:
        result += timedelta(days=1)
        if result.astimezone(_IST).weekday() < 5:  # Mon-Fri
            remaining -= 1
    return result


def create_exception(
    cur,
    code: str,
    category: str,
    description: str,
    financial_impact: Decimal | None,
) -> None:
    cur.execute(
        """
        insert into exceptions (
        exception_code,
        category,
        description,
        financial_impact,
        status
    )
    values (%s, %s, %s, %s, 'OPEN')
    on conflict (exception_code, description) do nothing
        """,
        (
            code,
            category,
            description,
            financial_impact,
        ),
    )


def create_reconciliation_link(
    cur,
    source_type: str,
    source_id,
    target_type: str,
    target_id,
    relationship_type: str,
    confidence: Decimal,
) -> None:
    cur.execute(
        """
        insert into reconciliation_links (
    source_type,
    source_id,
    target_type,
    target_id,
    relationship_type,
    status,
    confidence
)
values (%s, %s, %s, %s, %s, 'CONFIRMED', %s)
    on conflict (
    source_type,
    source_id,
    target_type,
    target_id,
    relationship_type
) do nothing
    """,
        (
            source_type,
            source_id,
            target_type,
            target_id,
            relationship_type,
            confidence,
        ),
    )


def reconcile_payments(
    payment_ids: list[str] | None = None,
    settlement_pending_business_days: int | None = None,
) -> list[dict]:
    """Reconciles payments against settlements.

    payment_ids is optional and provider-agnostic: omit it (the default)
    to reconcile every payment in the table, exactly as before. Pass a
    list of external_payment_id values to scope reconciliation to just
    those payments -- e.g. the set a data source just fetched for a
    requested period -- without touching unrelated rows.

    settlement_pending_business_days is optional and provider-agnostic:
    omit it (the default) and a missing settlement is EX02 immediately,
    exactly as before -- this is what the demo/eval dataset and the
    unscoped endpoint always use, so their output is untouched
    bit-for-bit. Pass a number of BANKING days to give a payment a grace
    period: if no settlement exists yet AND the payment's settlement
    deadline (see add_business_days) has not passed, it's
    SETTLEMENT_PENDING instead of EX02 -- normal settlement lag, not a
    genuinely missing record. Past the deadline with no settlement is
    still EX02. Callers own the number and its justification; the engine
    owns only the banking-day arithmetic.
    """
    database_url = os.getenv("SUPABASE_DB_URL")

    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL is not configured")

    results = []

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:

            if payment_ids is None:
                cur.execute(
                    """
                    select
                        p.id,
                        p.external_payment_id,
                        p.amount,
                        p.currency,
                        p.created_at,
                        p.status
                    from payments p
                    order by p.external_payment_id
                    """
                )
            else:
                cur.execute(
                    """
                    select
                        p.id,
                        p.external_payment_id,
                        p.amount,
                        p.currency,
                        p.created_at,
                        p.status
                    from payments p
                    where p.external_payment_id = any(%s)
                    order by p.external_payment_id
                    """,
                    (payment_ids,),
                )

            payments = cur.fetchall()

            for (
                payment_id,
                payment_ref,
                payment_amount,
                currency,
                payment_created_at,
                payment_status,
            ) in payments:

                payment_date = (
                    payment_created_at.date().isoformat()
                    if payment_created_at is not None
                    else None
                )

                # Carried on every result row so a caller can show when a
                # payment actually happened and what state the provider
                # says it is in -- `payment_date` stays the IST-day label
                # the daily trends bucket by, unchanged.
                payment_context = {
                    "payment_date": payment_date,
                    "payment_created_at": (
                        payment_created_at.isoformat()
                        if payment_created_at is not None
                        else None
                    ),
                    "payment_status": payment_status,
                }

                # --------------------------------------------------
                # Payment status triage
                # --------------------------------------------------

                normalized_status = (
                    payment_status.lower() if payment_status is not None else None
                )

                if normalized_status in NON_SETTLEABLE_PAYMENT_STATUSES:
                    print(f"{payment_ref}: NOT_CAPTURED ({payment_status})")
                    results.append({
                        "payment": payment_ref,
                        "status": "NOT_CAPTURED",
                        "category": "Not Captured",
                        "gross_amount": str(payment_amount),
                        **payment_context,
                    })

                    continue

                if normalized_status not in SETTLEABLE_PAYMENT_STATUSES:
                    # Neither known-settleable nor known-non-settleable.
                    # Reconciling it either way would be a guess, so it
                    # stops here: no settlement lookup, no exception, and
                    # a status a human can see and act on.
                    print(f"{payment_ref}: UNKNOWN_STATUS ({payment_status})")
                    results.append({
                        "payment": payment_ref,
                        "status": "UNKNOWN_STATUS",
                        "category": "Unsupported Payment Status",
                        "gross_amount": str(payment_amount),
                        **payment_context,
                    })

                    continue

                cur.execute(
                    """
                    select
                        s.id,
                        s.external_settlement_id,
                        s.settlement_amount
                    from settlements s
                    where s.reference = %s
                    order by s.external_settlement_id
                    """,
                    (payment_ref,),
                )

                settlements = cur.fetchall()

                # --------------------------------------------------
                # Missing settlement
                # --------------------------------------------------

                if not settlements:
                    if (
                        settlement_pending_business_days is not None
                        and payment_created_at is not None
                        and datetime.now(timezone.utc)
                        < add_business_days(
                            payment_created_at, settlement_pending_business_days
                        )
                    ):
                        print(f"{payment_ref}: SETTLEMENT_PENDING")
                        results.append({
                            "payment": payment_ref,
                            "status": "SETTLEMENT_PENDING",
                            "category": "Settlement Pending",
                            "gross_amount": str(payment_amount),
                            **payment_context,
                        })
                        continue

                    print(f"{payment_ref}: EX02 Missing Record")
                    results.append({
                        "payment": payment_ref,
                        "status": "EX02",
                        "category": "Missing Record",
                        "gross_amount": str(payment_amount),
                        **payment_context,
                    })

                    create_exception(
                        cur,
                        "EX02",
                        "Missing Record",
                        f"No settlement found for payment {payment_ref}.",
                        payment_amount,
                    )

                    continue

                # --------------------------------------------------
                # Duplicate settlement
                # --------------------------------------------------

                if len(settlements) > 1:
                    print(
                        f"{payment_ref}: EX03 Duplicate Record "
                        f"({len(settlements)} settlements)"
                    )

                    # Costs were genuinely incurred once per duplicate
                    # settlement -- sum across all of them so the
                    # Financial Overview reflects the real total impact,
                    # not just one settlement's line items.
                    total_fee = Decimal("0.00")
                    total_tax = Decimal("0.00")
                    total_adjustment = Decimal("0.00")
                    total_observed = Decimal("0.00")

                    for settlement_id, settlement_ref, settlement_amount in settlements:
                        create_reconciliation_link(
                            cur,
                            "payment",
                            payment_id,
                            "settlement",
                            settlement_id,
                            "DUPLICATE_CANDIDATE",
                            Decimal("100.00"),
                        )

                        cur.execute(
                            "select coalesce(sum(amount), 0) from fees where settlement_id = %s",
                            (settlement_id,),
                        )
                        total_fee += cur.fetchone()[0]

                        cur.execute(
                            "select coalesce(sum(amount), 0) from taxes where settlement_id = %s",
                            (settlement_id,),
                        )
                        total_tax += cur.fetchone()[0]

                        cur.execute(
                            "select coalesce(sum(amount), 0) from adjustments where settlement_id = %s",
                            (settlement_id,),
                        )
                        total_adjustment += cur.fetchone()[0]

                        total_observed += settlement_amount

                    results.append({
                        "payment": payment_ref,
                        "status": "EX03",
                        "category": "Duplicate Record",
                        "settlement_count": len(settlements),
                        "gross_amount": str(payment_amount),
                        "fee_amount": str(total_fee),
                        "tax_amount": str(total_tax),
                        "adjustment_amount": str(total_adjustment),
                        "observed_amount": str(total_observed),
                        **payment_context,
                    })

                    create_exception(
                        cur,
                        "EX03",
                        "Duplicate Record",
                        (
                            f"Payment {payment_ref} has "
                            f"{len(settlements)} matching settlements."
                        ),
                        payment_amount,
                    )

                    continue

                # --------------------------------------------------
                # Single settlement
                # --------------------------------------------------

                settlement_id, settlement_ref, settlement_amount = settlements[0]

                create_reconciliation_link(
                    cur,
                    "payment",
                    payment_id,
                    "settlement",
                    settlement_id,
                    "PAYMENT_TO_SETTLEMENT",
                    Decimal("100.00"),
                )

                # Fees
                cur.execute(
                    """
                    select coalesce(sum(amount), 0)
                    from fees
                    where settlement_id = %s
                    """,
                    (settlement_id,),
                )

                fee_amount = cur.fetchone()[0]

                # Taxes
                cur.execute(
                    """
                    select coalesce(sum(amount), 0)
                    from taxes
                    where settlement_id = %s
                    """,
                    (settlement_id,),
                )

                tax_amount = cur.fetchone()[0]

                # Adjustments
                cur.execute(
                    """
                    select coalesce(sum(amount), 0)
                    from adjustments
                    where settlement_id = %s
                    """,
                    (settlement_id,),
                )

                adjustment_amount = cur.fetchone()[0]

                expected_amount = (
                    payment_amount
                    - fee_amount
                    - tax_amount
                    + adjustment_amount
                )

                difference = expected_amount - settlement_amount

                # --------------------------------------------------
                # Reconciled
                # --------------------------------------------------

                if difference == Decimal("0.00"):
                    print(
                        f"{payment_ref}: RECONCILED "
                        f"(expected={expected_amount}, "
                        f"observed={settlement_amount})"
                    )

                    results.append({
                        "payment": payment_ref,
                        "status": "RECONCILED",
                        "gross_amount": str(payment_amount),
                        "fee_amount": str(fee_amount),
                        "tax_amount": str(tax_amount),
                        "adjustment_amount": str(adjustment_amount),
                        "expected_amount": str(expected_amount),
                        "observed_amount": str(settlement_amount),
                        "difference": "0.00",
                        **payment_context,
                    })

                    continue

                # --------------------------------------------------
                # Partial / amount mismatch
                # --------------------------------------------------

                if settlement_amount < expected_amount:
                    category = "Amount Mismatch"
                    description = (
                        f"Payment {payment_ref} expected "
                        f"{expected_amount} but settlement "
                        f"{settlement_ref} contains "
                        f"{settlement_amount}. "
                        f"Difference: {difference}."
                    )

                    print(
                        f"{payment_ref}: EX01 Amount Mismatch / Partial "
                        f"(expected={expected_amount}, "
                        f"observed={settlement_amount}, "
                        f"difference={difference})"
                    )

                else:
                    category = "Amount Mismatch"
                    description = (
                        f"Payment {payment_ref} expected "
                        f"{expected_amount} but settlement "
                        f"{settlement_ref} contains "
                        f"{settlement_amount}. "
                        f"Difference: {difference}."
                    )

                    print(
                        f"{payment_ref}: EX01 Amount Mismatch "
                        f"(expected={expected_amount}, "
                        f"observed={settlement_amount}, "
                        f"difference={difference})"
                    )
                results.append({
                    "payment": payment_ref,
                    "status": "EX01",
                    "category": category,
                    "gross_amount": str(payment_amount),
                    "fee_amount": str(fee_amount),
                    "tax_amount": str(tax_amount),
                    "adjustment_amount": str(adjustment_amount),
                    "expected_amount": str(expected_amount),
                    "observed_amount": str(settlement_amount),
                    "difference": str(difference),
                    **payment_context,
                })
                create_exception(
                    cur,
                    "EX01",
                    category,
                    description,
                    difference,
                )

        conn.commit()
    return results

if __name__ == "__main__":
    reconcile_payments()