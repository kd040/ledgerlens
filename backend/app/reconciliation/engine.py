import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from dotenv import load_dotenv


load_dotenv()


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
    settlement_pending_window: timedelta | None = None,
) -> list[dict]:
    """Reconciles payments against settlements.

    payment_ids is optional and provider-agnostic: omit it (the default)
    to reconcile every payment in the table, exactly as before. Pass a
    list of external_payment_id values to scope reconciliation to just
    those payments -- e.g. the set a data source just fetched for a
    requested period -- without touching unrelated rows.

    settlement_pending_window is optional and provider-agnostic: omit it
    (the default) and a missing settlement is EX02 immediately, exactly
    as before -- this is what the demo/eval dataset and the unscoped
    endpoint always use, so their output is untouched bit-for-bit. Pass
    a timedelta to give a payment a grace period: if no settlement
    exists yet AND the payment is younger than this window, it's
    SETTLEMENT_PENDING instead of EX02 (normal settlement lag, not a
    genuinely missing record). A payment older than the window with no
    settlement is still EX02. Callers own the window's value and its
    justification -- the engine only compares an age to a duration.
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
                        p.created_at
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
                        p.created_at
                    from payments p
                    where p.external_payment_id = any(%s)
                    order by p.external_payment_id
                    """,
                    (payment_ids,),
                )

            payments = cur.fetchall()

            for payment_id, payment_ref, payment_amount, currency, payment_created_at in payments:

                payment_date = (
                    payment_created_at.date().isoformat()
                    if payment_created_at is not None
                    else None
                )

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
                        settlement_pending_window is not None
                        and payment_created_at is not None
                        and datetime.now(timezone.utc) - payment_created_at
                        < settlement_pending_window
                    ):
                        print(f"{payment_ref}: SETTLEMENT_PENDING")
                        results.append({
                            "payment": payment_ref,
                            "status": "SETTLEMENT_PENDING",
                            "category": "Settlement Pending",
                            "gross_amount": str(payment_amount),
                            "payment_date": payment_date,
                        })
                        continue

                    print(f"{payment_ref}: EX02 Missing Record")
                    results.append({
                        "payment": payment_ref,
                        "status": "EX02",
                        "category": "Missing Record",
                        "gross_amount": str(payment_amount),
                        "payment_date": payment_date,
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
                        "payment_date": payment_date,
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
                        "payment_date": payment_date,
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
                    "payment_date": payment_date,
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