from decimal import Decimal
from typing import Any


def calculate_amount_difference(
    gross_amount: Decimal,
    fee_amount: Decimal,
    tax_amount: Decimal,
    adjustment_amount: Decimal,
    observed_amount: Decimal,
) -> dict[str, Any]:
    expected_amount = (
        gross_amount
        - fee_amount
        - tax_amount
        + adjustment_amount
    )

    difference = expected_amount - observed_amount

    return {
        "gross_amount": str(gross_amount),
        "fee_amount": str(fee_amount),
        "tax_amount": str(tax_amount),
        "adjustment_amount": str(adjustment_amount),
        "expected_amount": str(expected_amount),
        "observed_amount": str(observed_amount),
        "difference": str(difference),
    }


def calculate_missing_settlement_impact(
    gross_amount: Decimal,
) -> dict[str, Any]:
    return {
        "expected_amount": str(gross_amount),
        "observed_amount": "0.00",
        "difference": str(gross_amount),
    }


def calculate_duplicate_settlement_impact(
    settlement_amounts: list[Decimal],
) -> dict[str, Any]:
    expected_amount = settlement_amounts[0]
    observed_amount = sum(settlement_amounts, Decimal("0.00"))
    difference = observed_amount - expected_amount

    return {
        "expected_amount": str(expected_amount),
        "observed_amount": str(observed_amount),
        "difference": str(difference),
        "settlement_count": len(settlement_amounts),
    }
