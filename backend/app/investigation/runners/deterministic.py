import os
from decimal import Decimal
from typing import Any

import psycopg
from dotenv import load_dotenv

from app.investigation.services.audit import (
    record_evidence,
    record_tool_call,
)
from app.investigation.services.completion import determine_investigation_outcome
from app.investigation.services.contradictions import record_contradiction
from app.investigation.services.hypotheses import (
    evaluate_amount_mismatch_hypotheses,
    evaluate_duplicate_record_hypotheses,
    evaluate_missing_record_hypotheses,
)
from app.investigation.services.hypothesis_store import store_hypotheses
from app.investigation.tools.adjustments import get_adjustments
from app.investigation.tools.bank_transactions import get_bank_transactions
from app.investigation.tools.exceptions import get_exception
from app.investigation.tools.fees import get_fees
from app.investigation.tools.financial import (
    calculate_amount_difference,
    calculate_duplicate_settlement_impact,
    calculate_missing_settlement_impact,
)
from app.investigation.tools.payments import get_payment
from app.investigation.tools.related_records import find_related_records
from app.investigation.tools.settlements import get_settlements
from app.investigation.tools.taxes import get_taxes


load_dotenv()


def connect() -> psycopg.Connection:
    database_url = os.getenv("SUPABASE_DB_URL")

    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL is not configured")

    return psycopg.connect(database_url)


def _extract_payment_reference(description: str) -> str:
    for token in description.split():
        if token.startswith("PAY-"):
            return token.rstrip(",.")

    raise ValueError(
        "Could not determine payment reference from exception description."
    )


def _load_payment_by_reference(cur, payment_reference: str) -> dict[str, Any]:
    cur.execute(
        """
        select id
        from payments
        where external_payment_id = %s
        """,
        (payment_reference,),
    )

    payment_row = cur.fetchone()

    if payment_row is None:
        raise ValueError(f"Payment {payment_reference} was not found.")

    payment = get_payment(cur, str(payment_row[0]))

    if payment is None:
        raise ValueError(f"Payment {payment_reference} was not found.")

    return payment


def _hypotheses_to_dicts(hypothesis_results: list) -> list[dict[str, Any]]:
    return [
        {
            "hypothesis": result.hypothesis,
            "status": result.status,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
        }
        for result in hypothesis_results
    ]


def _contradiction_count(cur, investigation_id: str) -> int:
    cur.execute(
        """
        select count(*)
        from investigation_contradictions
        where investigation_id = %s
        """,
        (investigation_id,),
    )

    return cur.fetchone()[0]


def _complete_investigation(
    cur,
    investigation_id: str,
    outcome: dict[str, Any],
    financial_analysis: dict[str, Any],
) -> None:
    cur.execute(
        """
        update investigations
        set
            root_cause = %s,
            confidence = %s,
            recommendation = %s,
            status = %s,
            financial_analysis = %s,
            completed_at = now()
        where id = %s
        """,
        (
            outcome["root_cause"],
            outcome["confidence"],
            outcome["recommendation"],
            outcome["status"],
            psycopg.types.json.Jsonb(financial_analysis),
            investigation_id,
        ),
    )


def run_amount_mismatch_investigation(
    investigation_id: str,
    exception_id: str,
) -> dict[str, Any]:

    with connect() as conn:
        with conn.cursor() as cur:

            # --------------------------------------------------
            # 1. Exception
            # --------------------------------------------------

            exception = get_exception(cur, exception_id)

            if exception is None:
                raise ValueError(
                    f"Exception {exception_id} was not found."
                )

            record_tool_call(
                cur,
                investigation_id,
                "get_exception",
                {"exception_id": exception_id},
                exception,
            )

            record_evidence(
                cur,
                investigation_id,
                "DATABASE_RECORD",
                "exception",
                exception["id"],
                (
                    f"Exception {exception['exception_code']} "
                    f"retrieved."
                ),
            )

            # --------------------------------------------------
            # 2. Payment
            # --------------------------------------------------

            payment_reference = _extract_payment_reference(
                exception["description"]
            )

            payment = _load_payment_by_reference(cur, payment_reference)

            record_tool_call(
                cur,
                investigation_id,
                "get_payment",
                {"payment_id": payment["id"]},
                payment,
            )

            record_evidence(
                cur,
                investigation_id,
                "DATABASE_RECORD",
                "payment",
                payment["id"],
                (
                    f"Payment {payment['external_payment_id']} "
                    f"retrieved."
                ),
            )

            # --------------------------------------------------
            # 3. Settlement
            # --------------------------------------------------

            settlements = get_settlements(
                cur,
                payment["external_payment_id"],
            )

            record_tool_call(
                cur,
                investigation_id,
                "get_settlements",
                {
                    "payment_reference":
                        payment["external_payment_id"]
                },
                {"settlements": settlements},
            )

            if len(settlements) != 1:
                raise ValueError(
                    "Amount mismatch investigation requires "
                    "exactly one settlement."
                )

            settlement = settlements[0]

            record_evidence(
                cur,
                investigation_id,
                "DATABASE_RECORD",
                "settlement",
                settlement["id"],
                (
                    f"Settlement "
                    f"{settlement['external_settlement_id']} "
                    f"retrieved."
                ),
            )

            # --------------------------------------------------
            # 4. Fees
            # --------------------------------------------------

            fees = get_fees(
                cur,
                settlement["id"],
            )

            record_tool_call(
                cur,
                investigation_id,
                "get_fees",
                {"settlement_id": settlement["id"]},
                {"fees": fees},
            )

            fee_amount = sum(
                (
                    Decimal(item["amount"])
                    for item in fees
                ),
                Decimal("0.00"),
            )

            # --------------------------------------------------
            # 5. Taxes
            # --------------------------------------------------

            taxes = get_taxes(
                cur,
                settlement["id"],
            )

            record_tool_call(
                cur,
                investigation_id,
                "get_taxes",
                {"settlement_id": settlement["id"]},
                {"taxes": taxes},
            )

            tax_amount = sum(
                (
                    Decimal(item["amount"])
                    for item in taxes
                ),
                Decimal("0.00"),
            )

            # --------------------------------------------------
            # 6. Adjustments
            # --------------------------------------------------

            adjustments = get_adjustments(
                cur,
                settlement["id"],
            )

            record_tool_call(
                cur,
                investigation_id,
                "get_adjustments",
                {"settlement_id": settlement["id"]},
                {"adjustments": adjustments},
            )

            adjustment_amount = sum(
                (
                    Decimal(item["amount"])
                    for item in adjustments
                ),
                Decimal("0.00"),
            )

            # --------------------------------------------------
            # 7. Deterministic financial calculation
            # --------------------------------------------------

            financial_analysis = calculate_amount_difference(
                Decimal(payment["amount"]),
                fee_amount,
                tax_amount,
                adjustment_amount,
                Decimal(settlement["settlement_amount"]),
            )

            record_tool_call(
                cur,
                investigation_id,
                "calculate_amount_difference",
                {
                    "gross_amount": payment["amount"],
                    "fee_amount": str(fee_amount),
                    "tax_amount": str(tax_amount),
                    "adjustment_amount":
                        str(adjustment_amount),
                    "observed_amount":
                        settlement["settlement_amount"],
                },
                financial_analysis,
            )

            record_evidence(
                cur,
                investigation_id,
                "CALCULATION",
                "financial_analysis",
                None,
                (
                    f"Expected settlement amount is "
                    f"{financial_analysis['expected_amount']}; "
                    f"observed amount is "
                    f"{financial_analysis['observed_amount']}; "
                    f"difference is "
                    f"{financial_analysis['difference']}."
                ),
            )

            # --------------------------------------------------
            # 8. Hypotheses
            # --------------------------------------------------

            difference = Decimal(
                financial_analysis["difference"]
            )

            hypothesis_results = evaluate_amount_mismatch_hypotheses(
                Decimal(payment["amount"]),
                fee_amount,
                tax_amount,
                adjustment_amount,
                Decimal(settlement["settlement_amount"]),
            )

            store_hypotheses(cur, investigation_id, hypothesis_results)

            # --------------------------------------------------
            # 9. Contradictions
            # --------------------------------------------------

            contradiction_count = _contradiction_count(cur, investigation_id)

            # --------------------------------------------------
            # 10. Complete investigation
            # --------------------------------------------------

            outcome = determine_investigation_outcome(
                financial_analysis,
                _hypotheses_to_dicts(hypothesis_results),
                contradiction_count,
            )

            _complete_investigation(
                cur, investigation_id, outcome, financial_analysis
            )

            conn.commit()

            return {
                "investigation_id": investigation_id,
                "exception_code":
                    exception["exception_code"],
                "payment":
                    payment["external_payment_id"],
                "status": outcome["status"],
                "root_cause": outcome["root_cause"],
                "financial_analysis":
                    financial_analysis,
                "confidence": str(outcome["confidence"]),
                "recommendation": outcome["recommendation"],
                "reason": outcome["reason"],
                "difference": str(difference),
            }


def run_missing_record_investigation(
    investigation_id: str,
    exception_id: str,
) -> dict[str, Any]:

    with connect() as conn:
        with conn.cursor() as cur:

            # --------------------------------------------------
            # 1. Exception
            # --------------------------------------------------

            exception = get_exception(cur, exception_id)

            if exception is None:
                raise ValueError(f"Exception {exception_id} was not found.")

            record_tool_call(
                cur,
                investigation_id,
                "get_exception",
                {"exception_id": exception_id},
                exception,
            )

            record_evidence(
                cur,
                investigation_id,
                "DATABASE_RECORD",
                "exception",
                exception["id"],
                f"Exception {exception['exception_code']} retrieved.",
            )

            # --------------------------------------------------
            # 2. Payment
            # --------------------------------------------------

            payment_reference = _extract_payment_reference(
                exception["description"]
            )

            payment = _load_payment_by_reference(cur, payment_reference)

            record_tool_call(
                cur,
                investigation_id,
                "get_payment",
                {"payment_id": payment["id"]},
                payment,
            )

            record_evidence(
                cur,
                investigation_id,
                "DATABASE_RECORD",
                "payment",
                payment["id"],
                f"Payment {payment['external_payment_id']} retrieved.",
            )

            # --------------------------------------------------
            # 3. Settlements (expected to be absent)
            # --------------------------------------------------

            settlements = get_settlements(cur, payment["external_payment_id"])

            record_tool_call(
                cur,
                investigation_id,
                "get_settlements",
                {"payment_reference": payment["external_payment_id"]},
                {"settlements": settlements},
            )

            if settlements:
                for settlement in settlements:
                    record_evidence(
                        cur,
                        investigation_id,
                        "DATABASE_RECORD",
                        "settlement",
                        settlement["id"],
                        (
                            f"Settlement "
                            f"{settlement['external_settlement_id']} was "
                            "found despite the exception reporting a "
                            "missing record."
                        ),
                    )

                record_contradiction(
                    cur,
                    investigation_id,
                    (
                        f"Exception {exception['exception_code']} reports "
                        f"no settlement for payment "
                        f"{payment['external_payment_id']}, but "
                        f"{len(settlements)} settlement record(s) now "
                        "exist."
                    ),
                )
            else:
                record_evidence(
                    cur,
                    investigation_id,
                    "ABSENCE_OF_RECORD",
                    "settlement",
                    None,
                    (
                        f"No settlement record exists for payment "
                        f"{payment['external_payment_id']}."
                    ),
                )

            # --------------------------------------------------
            # 4. Related records
            # --------------------------------------------------

            related = find_related_records(cur, payment["external_payment_id"])

            record_tool_call(
                cur,
                investigation_id,
                "find_related_records",
                {"payment_reference": payment["external_payment_id"]},
                related,
            )

            related_record_count = len(related["refunds"]) + len(
                related["bank_transactions"]
            )

            if related_record_count > 0:
                record_evidence(
                    cur,
                    investigation_id,
                    "DATABASE_RECORD",
                    "related_records",
                    None,
                    (
                        f"Found {related_record_count} related refund or "
                        f"bank transaction record(s) for payment "
                        f"{payment['external_payment_id']}."
                    ),
                )
            else:
                record_evidence(
                    cur,
                    investigation_id,
                    "ABSENCE_OF_RECORD",
                    "related_records",
                    None,
                    (
                        "No related refund or bank transaction records "
                        f"were found for payment "
                        f"{payment['external_payment_id']}."
                    ),
                )

            # --------------------------------------------------
            # 5. Deterministic financial calculation
            # --------------------------------------------------

            financial_analysis = calculate_missing_settlement_impact(
                Decimal(payment["amount"])
            )

            record_tool_call(
                cur,
                investigation_id,
                "calculate_missing_settlement_impact",
                {"gross_amount": payment["amount"]},
                financial_analysis,
            )

            record_evidence(
                cur,
                investigation_id,
                "CALCULATION",
                "financial_analysis",
                None,
                (
                    f"Expected settlement amount is "
                    f"{financial_analysis['expected_amount']}; no "
                    "settlement amount has been observed."
                ),
            )

            # --------------------------------------------------
            # 6. Hypotheses
            # --------------------------------------------------

            hypothesis_results = evaluate_missing_record_hypotheses(
                len(settlements),
                related_record_count,
            )

            store_hypotheses(cur, investigation_id, hypothesis_results)

            # --------------------------------------------------
            # 7. Contradictions
            # --------------------------------------------------

            contradiction_count = _contradiction_count(cur, investigation_id)

            # --------------------------------------------------
            # 8. Complete investigation
            # --------------------------------------------------

            outcome = determine_investigation_outcome(
                financial_analysis,
                _hypotheses_to_dicts(hypothesis_results),
                contradiction_count,
            )

            _complete_investigation(
                cur, investigation_id, outcome, financial_analysis
            )

            conn.commit()

            return {
                "investigation_id": investigation_id,
                "exception_code": exception["exception_code"],
                "payment": payment["external_payment_id"],
                "status": outcome["status"],
                "root_cause": outcome["root_cause"],
                "financial_analysis": financial_analysis,
                "confidence": str(outcome["confidence"]),
                "recommendation": outcome["recommendation"],
                "reason": outcome["reason"],
                "difference": financial_analysis["difference"],
            }


def run_duplicate_record_investigation(
    investigation_id: str,
    exception_id: str,
) -> dict[str, Any]:

    with connect() as conn:
        with conn.cursor() as cur:

            # --------------------------------------------------
            # 1. Exception
            # --------------------------------------------------

            exception = get_exception(cur, exception_id)

            if exception is None:
                raise ValueError(f"Exception {exception_id} was not found.")

            record_tool_call(
                cur,
                investigation_id,
                "get_exception",
                {"exception_id": exception_id},
                exception,
            )

            record_evidence(
                cur,
                investigation_id,
                "DATABASE_RECORD",
                "exception",
                exception["id"],
                f"Exception {exception['exception_code']} retrieved.",
            )

            # --------------------------------------------------
            # 2. Payment
            # --------------------------------------------------

            payment_reference = _extract_payment_reference(
                exception["description"]
            )

            payment = _load_payment_by_reference(cur, payment_reference)

            record_tool_call(
                cur,
                investigation_id,
                "get_payment",
                {"payment_id": payment["id"]},
                payment,
            )

            record_evidence(
                cur,
                investigation_id,
                "DATABASE_RECORD",
                "payment",
                payment["id"],
                f"Payment {payment['external_payment_id']} retrieved.",
            )

            # --------------------------------------------------
            # 3. Settlements
            # --------------------------------------------------

            settlements = get_settlements(cur, payment["external_payment_id"])

            record_tool_call(
                cur,
                investigation_id,
                "get_settlements",
                {"payment_reference": payment["external_payment_id"]},
                {"settlements": settlements},
            )

            if len(settlements) < 2:
                raise ValueError(
                    "Duplicate record investigation requires at least "
                    "two settlements."
                )

            for settlement in settlements:
                record_evidence(
                    cur,
                    investigation_id,
                    "DATABASE_RECORD",
                    "settlement",
                    settlement["id"],
                    (
                        f"Settlement "
                        f"{settlement['external_settlement_id']} "
                        f"({settlement['settlement_amount']}) retrieved."
                    ),
                )

            settlement_amounts = [
                Decimal(settlement["settlement_amount"])
                for settlement in settlements
            ]

            amounts_equal = len(set(settlement_amounts)) == 1

            # --------------------------------------------------
            # 4. Bank transaction confirmation per settlement
            # --------------------------------------------------

            settlements_without_bank_confirmation = 0

            for settlement in settlements:
                bank_transactions = get_bank_transactions(
                    cur,
                    settlement["external_settlement_id"],
                )

                record_tool_call(
                    cur,
                    investigation_id,
                    "get_bank_transactions",
                    {
                        "settlement_reference":
                            settlement["external_settlement_id"]
                    },
                    {"bank_transactions": bank_transactions},
                )

                if bank_transactions:
                    record_evidence(
                        cur,
                        investigation_id,
                        "DATABASE_RECORD",
                        "bank_transaction",
                        None,
                        (
                            "A bank transaction confirms settlement "
                            f"{settlement['external_settlement_id']}."
                        ),
                    )
                else:
                    settlements_without_bank_confirmation += 1

                    record_evidence(
                        cur,
                        investigation_id,
                        "ABSENCE_OF_RECORD",
                        "bank_transaction",
                        None,
                        (
                            "No bank transaction confirms settlement "
                            f"{settlement['external_settlement_id']}."
                        ),
                    )

                    if settlement["status"] == "SETTLED":
                        record_contradiction(
                            cur,
                            investigation_id,
                            (
                                f"Settlement "
                                f"{settlement['external_settlement_id']} "
                                f"has status 'SETTLED' but no matching "
                                "bank transaction was found."
                            ),
                        )

            # --------------------------------------------------
            # 5. Deterministic financial calculation
            # --------------------------------------------------

            financial_analysis = calculate_duplicate_settlement_impact(
                settlement_amounts
            )

            record_tool_call(
                cur,
                investigation_id,
                "calculate_duplicate_settlement_impact",
                {
                    "settlement_amounts": [
                        str(amount) for amount in settlement_amounts
                    ]
                },
                financial_analysis,
            )

            record_evidence(
                cur,
                investigation_id,
                "CALCULATION",
                "financial_analysis",
                None,
                (
                    f"{financial_analysis['settlement_count']} settlement "
                    "records total "
                    f"{financial_analysis['observed_amount']} against an "
                    f"expected single settlement of "
                    f"{financial_analysis['expected_amount']}; excess "
                    f"exposure is {financial_analysis['difference']}."
                ),
            )

            # --------------------------------------------------
            # 6. Hypotheses
            # --------------------------------------------------

            hypothesis_results = evaluate_duplicate_record_hypotheses(
                len(settlements),
                amounts_equal,
                settlements_without_bank_confirmation,
            )

            store_hypotheses(cur, investigation_id, hypothesis_results)

            # --------------------------------------------------
            # 7. Contradictions
            # --------------------------------------------------

            contradiction_count = _contradiction_count(cur, investigation_id)

            # --------------------------------------------------
            # 8. Complete investigation
            # --------------------------------------------------

            outcome = determine_investigation_outcome(
                financial_analysis,
                _hypotheses_to_dicts(hypothesis_results),
                contradiction_count,
            )

            _complete_investigation(
                cur, investigation_id, outcome, financial_analysis
            )

            conn.commit()

            return {
                "investigation_id": investigation_id,
                "exception_code": exception["exception_code"],
                "payment": payment["external_payment_id"],
                "status": outcome["status"],
                "root_cause": outcome["root_cause"],
                "financial_analysis": financial_analysis,
                "confidence": str(outcome["confidence"]),
                "recommendation": outcome["recommendation"],
                "reason": outcome["reason"],
                "difference": financial_analysis["difference"],
            }
