import os
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


def reconcile_payments() -> list[dict]:
    database_url = os.getenv("SUPABASE_DB_URL")

    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL is not configured")
        
    results = []

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                select
                    p.id,
                    p.external_payment_id,
                    p.amount,
                    p.currency
                from payments p
                order by p.external_payment_id
                """
            )

            payments = cur.fetchall()

            for payment_id, payment_ref, payment_amount, currency in payments:

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
                    print(f"{payment_ref}: EX02 Missing Record")
                    results.append({
                        "payment": payment_ref,
                        "status": "EX02",
                        "category": "Missing Record",
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
                    results.append({
                        "payment": payment_ref,
                        "status": "EX03",
                        "category": "Duplicate Record",
                        "settlement_count": len(settlements),
                    })

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
                        "expected_amount": str(expected_amount),
                        "observed_amount": str(settlement_amount),
                        "difference": "0.00",
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
                    "expected_amount": str(expected_amount),
                    "observed_amount": str(settlement_amount),
                    "difference": str(difference),
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