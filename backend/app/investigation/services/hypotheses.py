from dataclasses import dataclass
from decimal import Decimal


@dataclass
class HypothesisResult:
    hypothesis: str
    status: str
    confidence: Decimal
    reasoning: str


def evaluate_amount_mismatch_hypotheses(
    gross_amount: Decimal,
    fee_amount: Decimal,
    tax_amount: Decimal,
    adjustment_amount: Decimal,
    observed_amount: Decimal,
) -> list[HypothesisResult]:

    expected_amount = (
        gross_amount
        - fee_amount
        - tax_amount
        + adjustment_amount
    )

    difference = expected_amount - observed_amount

    results: list[HypothesisResult] = []

    # --------------------------------------------------
    # H1: Settlement amount is incorrect
    # --------------------------------------------------

    if difference > Decimal("0.00"):
        results.append(
            HypothesisResult(
                hypothesis="Settlement amount is incorrect.",
                status="SUPPORTED",
                confidence=Decimal("95.00"),
                reasoning=(
                    f"Expected settlement amount is "
                    f"{expected_amount}, while observed "
                    f"settlement amount is {observed_amount}. "
                    f"The difference is {difference}."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis="Settlement amount is incorrect.",
                status="REJECTED",
                confidence=Decimal("90.00"),
                reasoning=(
                    "Observed settlement amount matches or "
                    "exceeds the calculated expected amount."
                ),
            )
        )

    # --------------------------------------------------
    # H2: Fee explains the difference
    # --------------------------------------------------

    if fee_amount > Decimal("0.00"):
        results.append(
            HypothesisResult(
                hypothesis="Fee calculation explains the difference.",
                status="INSUFFICIENT_EVIDENCE",
                confidence=Decimal("50.00"),
                reasoning=(
                    f"Fees total {fee_amount}. The fee exists, "
                    "but additional evidence is required to "
                    "determine whether the fee itself is incorrect."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis="Fee calculation explains the difference.",
                status="REJECTED",
                confidence=Decimal("90.00"),
                reasoning="No fee was recorded for the settlement.",
            )
        )

    # --------------------------------------------------
    # H3: Tax explains the difference
    # --------------------------------------------------

    if tax_amount != Decimal("0.00"):
        results.append(
            HypothesisResult(
                hypothesis="Tax calculation explains the difference.",
                status="INSUFFICIENT_EVIDENCE",
                confidence=Decimal("50.00"),
                reasoning=(
                    f"Taxes total {tax_amount}. Additional "
                    "evidence is required to determine whether "
                    "the tax calculation is incorrect."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis="Tax calculation explains the difference.",
                status="REJECTED",
                confidence=Decimal("95.00"),
                reasoning="No tax amount contributes to the difference.",
            )
        )

    # --------------------------------------------------
    # H4: Adjustment explains the difference
    # --------------------------------------------------

    if adjustment_amount != Decimal("0.00"):
        results.append(
            HypothesisResult(
                hypothesis="Adjustment explains the difference.",
                status="INSUFFICIENT_EVIDENCE",
                confidence=Decimal("50.00"),
                reasoning=(
                    f"Adjustments total {adjustment_amount}. "
                    "Additional evidence is required to determine "
                    "whether the adjustment explains the difference."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis="Adjustment explains the difference.",
                status="REJECTED",
                confidence=Decimal("95.00"),
                reasoning="No adjustment contributes to the difference.",
            )
        )

    return results


def evaluate_missing_record_hypotheses(
    settlement_count: int,
    related_record_count: int,
) -> list[HypothesisResult]:

    results: list[HypothesisResult] = []

    # --------------------------------------------------
    # H1: No settlement was ever created
    # --------------------------------------------------

    if settlement_count == 0:
        results.append(
            HypothesisResult(
                hypothesis="No settlement was ever created for this payment.",
                status="SUPPORTED",
                confidence=Decimal("90.00"),
                reasoning=(
                    "A search for settlements referencing this payment "
                    "returned zero records."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis="No settlement was ever created for this payment.",
                status="REJECTED",
                confidence=Decimal("95.00"),
                reasoning=(
                    f"{settlement_count} settlement record(s) were found "
                    "for this payment, contradicting the missing-record "
                    "exception."
                ),
            )
        )

    # --------------------------------------------------
    # H2: A related record explains the missing settlement
    # --------------------------------------------------

    if related_record_count > 0:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "A related record (refund or bank transaction) "
                    "explains the missing settlement."
                ),
                status="SUPPORTED",
                confidence=Decimal("70.00"),
                reasoning=(
                    f"{related_record_count} related refund or bank "
                    "transaction record(s) were found for this payment "
                    "reference."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "A related record (refund or bank transaction) "
                    "explains the missing settlement."
                ),
                status="REJECTED",
                confidence=Decimal("85.00"),
                reasoning=(
                    "No related refund or bank transaction records were "
                    "found for this payment reference."
                ),
            )
        )

    # --------------------------------------------------
    # H3: Settlement is pending
    # --------------------------------------------------

    results.append(
        HypothesisResult(
            hypothesis="Settlement is pending and has not yet been created.",
            status="INSUFFICIENT_EVIDENCE",
            confidence=Decimal("50.00"),
            reasoning=(
                "The timing of settlement creation cannot be determined "
                "from available records."
            ),
        )
    )

    return results


def evaluate_duplicate_record_hypotheses(
    settlement_count: int,
    amounts_equal: bool,
    settlements_without_bank_confirmation: int,
) -> list[HypothesisResult]:

    results: list[HypothesisResult] = []

    # --------------------------------------------------
    # H1: Settlement was processed more than once
    # --------------------------------------------------

    if amounts_equal:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "Settlement was processed more than once for the "
                    "same payment."
                ),
                status="SUPPORTED",
                confidence=Decimal("90.00"),
                reasoning=(
                    f"{settlement_count} settlements of identical amount "
                    "reference the same payment, indicating duplicate "
                    "processing."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "Settlement was processed more than once for the "
                    "same payment."
                ),
                status="INSUFFICIENT_EVIDENCE",
                confidence=Decimal("50.00"),
                reasoning=(
                    "Settlement amounts differ across the duplicate "
                    "records; additional evidence is required to confirm "
                    "duplicate processing."
                ),
            )
        )

    # --------------------------------------------------
    # H2: Settlements are legitimately distinct transactions
    # --------------------------------------------------

    if amounts_equal:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "Settlements represent legitimately distinct "
                    "transactions sharing the same reference."
                ),
                status="REJECTED",
                confidence=Decimal("85.00"),
                reasoning=(
                    "Identical settlement amounts are inconsistent with "
                    "legitimately distinct transactions."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "Settlements represent legitimately distinct "
                    "transactions sharing the same reference."
                ),
                status="INSUFFICIENT_EVIDENCE",
                confidence=Decimal("50.00"),
                reasoning=(
                    "Differing settlement amounts leave open the "
                    "possibility of distinct transactions."
                ),
            )
        )

    # --------------------------------------------------
    # H3: Bank records confirm only a subset of the duplicates
    # --------------------------------------------------

    if settlements_without_bank_confirmation > 0:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "Bank records confirm only a subset of the duplicate "
                    "settlements actually occurred."
                ),
                status="SUPPORTED",
                confidence=Decimal("85.00"),
                reasoning=(
                    f"{settlements_without_bank_confirmation} of "
                    f"{settlement_count} settlement record(s) have no "
                    "matching bank transaction."
                ),
            )
        )
    else:
        results.append(
            HypothesisResult(
                hypothesis=(
                    "Bank records confirm only a subset of the duplicate "
                    "settlements actually occurred."
                ),
                status="REJECTED",
                confidence=Decimal("80.00"),
                reasoning=(
                    "All duplicate settlement records have a matching "
                    "bank transaction."
                ),
            )
        )

    return results
