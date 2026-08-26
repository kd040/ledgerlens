from decimal import Decimal
from typing import Any


def determine_investigation_outcome(
    financial_analysis: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    contradiction_count: int,
) -> dict[str, Any]:
    difference = Decimal(
        financial_analysis["difference"]
    )

    supported = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis["status"] == "SUPPORTED"
    ]

    if contradiction_count > 0:
        return {
            "status": "ESCALATED",
            "root_cause": None,
            "confidence": Decimal("50.00"),
            "recommendation": "HUMAN_REVIEW",
            "reason": (
                "Contradictory evidence prevents a "
                "high-confidence conclusion."
            ),
        }

    if difference == Decimal("0.00"):
        return {
            "status": "COMPLETED",
            "root_cause": "No financial discrepancy identified.",
            "confidence": Decimal("100.00"),
            "recommendation": "NO_ACTION",
            "reason": "Expected and observed amounts match.",
        }

    if supported:
        primary = supported[0]

        return {
            "status": "COMPLETED",
            "root_cause": primary["hypothesis"],
            "confidence": primary["confidence"],
            "recommendation": "HUMAN_REVIEW",
            "reason": primary["reasoning"],
        }

    return {
        "status": "ESCALATED",
        "root_cause": None,
        "confidence": Decimal("40.00"),
        "recommendation": "HUMAN_REVIEW",
        "reason": (
            "No sufficiently supported hypothesis "
            "explains the discrepancy."
        ),
    }
