"""Day-by-day financial breakdown for one investigation's own payment.

Every investigation is scoped to exactly one payment. Most have exactly
one settlement (one real date); an EX03 duplicate has one settlement
per duplicate, each with its own settlement_date. "Day navigation"
means navigating across those actual dates -- never a fabricated
calendar, and never data from any other payment.
"""

from decimal import Decimal
from typing import Any

from app.investigation.tools.adjustments import get_adjustments
from app.investigation.tools.fees import get_fees
from app.investigation.tools.settlements import get_settlements
from app.investigation.tools.taxes import get_taxes


def list_available_dates(cur, payment_reference: str) -> list[str]:
    settlements = get_settlements(cur, payment_reference)
    return sorted({settlement["settlement_date"][:10] for settlement in settlements})


def get_daily_financials(
    cur, payment: dict[str, Any], payment_reference: str, selected_date: str
) -> dict[str, Any]:
    settlements = get_settlements(cur, payment_reference)
    day_settlements = [
        s for s in settlements if s["settlement_date"][:10] == selected_date
    ]

    gross_amount = Decimal(payment["amount"])
    fee_amount = Decimal("0.00")
    tax_amount = Decimal("0.00")
    adjustment_amount = Decimal("0.00")
    observed_amount = Decimal("0.00")

    for settlement in day_settlements:
        fee_amount += sum(
            (Decimal(item["amount"]) for item in get_fees(cur, settlement["id"])),
            Decimal("0.00"),
        )
        tax_amount += sum(
            (Decimal(item["amount"]) for item in get_taxes(cur, settlement["id"])),
            Decimal("0.00"),
        )
        adjustment_amount += sum(
            (
                Decimal(item["amount"])
                for item in get_adjustments(cur, settlement["id"])
            ),
            Decimal("0.00"),
        )
        observed_amount += Decimal(settlement["settlement_amount"])

    expected_amount = gross_amount - fee_amount - tax_amount + adjustment_amount

    return {
        "date": selected_date,
        "gross_amount": str(gross_amount),
        "fee_amount": str(fee_amount),
        "tax_amount": str(tax_amount),
        "adjustment_amount": str(adjustment_amount),
        "expected_amount": str(expected_amount),
        "observed_amount": str(observed_amount),
        "difference": str(expected_amount - observed_amount),
        "settlement_count": len(day_settlements),
    }
