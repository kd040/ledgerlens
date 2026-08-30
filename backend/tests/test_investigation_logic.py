"""Assert-based checks for the deterministic investigation logic.

Pure-function coverage only (no DB) for the branches that decide
financial impact, hypothesis status, and final investigation outcome.
Run directly: python backend/tests/test_investigation_logic.py
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.investigation.runners.deterministic import extract_payment_reference
from app.investigation.services.completion import determine_investigation_outcome
from app.investigation.services.hypotheses import (
    evaluate_amount_mismatch_hypotheses,
    evaluate_duplicate_record_hypotheses,
    evaluate_missing_record_hypotheses,
)
from app.investigation.tools.financial import (
    calculate_amount_difference,
    calculate_duplicate_settlement_impact,
    calculate_missing_settlement_impact,
)


def test_extract_payment_reference_recognizes_eval_dataset_ids():
    assert extract_payment_reference("Payment PAY-005 expected 100.") == "PAY-005"


def test_extract_payment_reference_recognizes_razorpay_ids():
    """Regression guard: exception descriptions for real Razorpay
    payments embed pay_... ids, not PAY-NNN -- both must resolve, or
    starting an investigation on a genuine Razorpay exception raises."""
    description = "No settlement found for payment pay_TUTgDBuJLGCdRC."
    assert extract_payment_reference(description) == "pay_TUTgDBuJLGCdRC"


def test_calculate_amount_difference():
    result = calculate_amount_difference(
        Decimal("2000.00"), Decimal("100.00"), Decimal("0.00"),
        Decimal("0.00"), Decimal("1850.00"),
    )
    assert result["expected_amount"] == "1900.00"
    assert result["difference"] == "50.00"


def test_calculate_missing_settlement_impact():
    result = calculate_missing_settlement_impact(Decimal("1500.00"))
    assert result["observed_amount"] == "0.00"
    assert result["difference"] == "1500.00"


def test_calculate_duplicate_settlement_impact():
    result = calculate_duplicate_settlement_impact(
        [Decimal("3000.00"), Decimal("3000.00")]
    )
    assert result["expected_amount"] == "3000.00"
    assert result["observed_amount"] == "6000.00"
    assert result["difference"] == "3000.00"
    assert result["settlement_count"] == 2


def test_amount_mismatch_hypotheses_support_on_difference():
    results = evaluate_amount_mismatch_hypotheses(
        Decimal("2000.00"), Decimal("100.00"), Decimal("0.00"),
        Decimal("0.00"), Decimal("1850.00"),
    )
    assert results[0].status == "SUPPORTED"


def test_missing_record_hypotheses_confirm_absence():
    results = evaluate_missing_record_hypotheses(
        settlement_count=0, related_record_count=0
    )
    assert results[0].status == "SUPPORTED"
    assert results[1].status == "REJECTED"


def test_missing_record_hypotheses_reject_when_settlement_exists():
    results = evaluate_missing_record_hypotheses(
        settlement_count=1, related_record_count=0
    )
    assert results[0].status == "REJECTED"


def test_duplicate_record_hypotheses_identical_amounts():
    results = evaluate_duplicate_record_hypotheses(
        settlement_count=2, amounts_equal=True,
        settlements_without_bank_confirmation=1,
    )
    assert results[0].status == "SUPPORTED"  # duplicate processing
    assert results[1].status == "REJECTED"   # legitimately distinct
    assert results[2].status == "SUPPORTED"  # bank confirms only a subset


def test_outcome_escalates_on_contradiction_even_if_supported():
    financial_analysis = {"difference": "3000.00"}
    hypotheses = [
        {"hypothesis": "H1", "status": "SUPPORTED",
         "confidence": Decimal("95.00"), "reasoning": "..."},
    ]
    outcome = determine_investigation_outcome(
        financial_analysis, hypotheses, contradiction_count=1
    )
    assert outcome["status"] == "ESCALATED"
    assert outcome["confidence"] == Decimal("50.00")


def test_outcome_no_action_when_difference_zero():
    outcome = determine_investigation_outcome(
        {"difference": "0.00"}, [], contradiction_count=0
    )
    assert outcome["status"] == "COMPLETED"
    assert outcome["recommendation"] == "NO_ACTION"


def test_outcome_completed_with_supported_hypothesis():
    financial_analysis = {"difference": "50.00"}
    hypotheses = [
        {"hypothesis": "Settlement amount is incorrect.",
         "status": "SUPPORTED", "confidence": Decimal("95.00"),
         "reasoning": "..."},
    ]
    outcome = determine_investigation_outcome(
        financial_analysis, hypotheses, contradiction_count=0
    )
    assert outcome["status"] == "COMPLETED"
    assert outcome["root_cause"] == "Settlement amount is incorrect."


def test_outcome_escalates_when_no_hypothesis_supported():
    outcome = determine_investigation_outcome(
        {"difference": "50.00"}, [], contradiction_count=0
    )
    assert outcome["status"] == "ESCALATED"
    assert outcome["confidence"] == Decimal("40.00")


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
