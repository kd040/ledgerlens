"""The AI Investigator: an additive analysis pass over an EXISTING
investigation. The deterministic runners (investigation/runners/
deterministic.py) remain the only source of financial arithmetic and the
only thing that ever creates an investigation -- this module never
recomputes a dollar figure and never runs before a deterministic pass
has already produced investigations.financial_analysis for this case.

Every number the model reports back is verified against that persisted,
already-computed financial_analysis before anything is shown or stored.
A mismatch is rejected outright, never silently corrected.

Model access goes through one provider-agnostic seam (app/ai/providers/)
-- Anthropic and Gemini are interchangeable via AI_PROVIDER, and tests
inject a fake provider (or, for backward compatibility, a fake Anthropic
client) so no test ever makes a live API call.
"""

import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.ai.config import AI_PROVIDER
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.base import AIProvider, AIProviderError
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.schemas import AiInvestigationResult
from app.ai.tools import TOOL_DEFINITIONS, build_tool_dispatch
from app.investigation.runners.deterministic import connect, extract_payment_reference
from app.investigation.services.audit import record_evidence
from app.investigation.services.contradictions import record_contradiction
from app.investigation.services.hypotheses import HypothesisResult
from app.investigation.services.hypothesis_store import store_hypotheses
from app.investigation.services.investigation_store import get_investigation


class AiInvestigationError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


SUBMIT_TOOL_NAME = "submit_investigation_findings"

_GENERAL_SYSTEM_PROMPT = """You are LedgerLens's AI Investigator, a financial reconciliation \
analyst. You explain a specific detected exception using only real, tool-verified evidence.

Rules you must never break:
- Never invent a transaction ID, payment ID, settlement ID, amount, date, fee, tax, status, \
record, root cause, or piece of evidence. Every specific fact in your output must come from a \
tool result or from the "KNOWN, VERIFIED FACTS" given to you.
- The financial_analysis and summary.financial_gap you report back must exactly match the \
"KNOWN, VERIFIED FACTS" given to you -- copy those numbers verbatim, never recompute or round them.
- The deterministic financial_analysis given to you is the sole source of financial arithmetic. \
Do not introduce alternate calculations or conflicting financial figures anywhere in your \
response, including free-text hypothesis reasoning and root_cause_assessment -- refer back to \
the given KNOWN, VERIFIED FACTS instead of computing a new number of your own.
- Distinguish explicitly between what is KNOWN (directly proven by a record), LIKELY (a \
reasonable inference the evidence supports but doesn't prove), and NOT PROVEN (cannot currently \
be established from available records). Never present "likely" as if it were "known."
- If the evidence is insufficient to reach a confident conclusion, say so plainly in \
root_cause_assessment.not_proven, keep confidence low, and set recommendation to HUMAN_REVIEW. \
Do not claim certainty when the evidence is incomplete.
- Use the available tools to gather evidence before concluding. Call get_investigation_evidence/\
hypotheses/contradictions first to see what has already been found, so you don't re-derive it \
from scratch.
- You may recommend NO_ACTION, HUMAN_REVIEW, or ESCALATE. You never resolve or escalate a case \
yourself -- a human reviewer does that after reading your findings.
- When you are done gathering evidence, call submit_investigation_findings exactly once with \
your complete structured conclusion. Do not answer in plain text.
"""

_CATEGORY_GUIDANCE: dict[str, str] = {
    "EX01": """This is an EX01 Amount Mismatch case. Answer: "Why is the settlement different \
from the expected amount?" Walk gross amount -> fees -> tax -> adjustments -> expected \
settlement, compare against the observed settlement, and explicitly identify what portion of \
the difference is explained by fees/tax/adjustments and what portion (if any) remains \
unexplained after accounting for all of them. Use get_settlements, get_fees, get_taxes, and \
get_adjustments to verify each line item individually rather than assuming the KNOWN FACTS \
breakdown is exhaustive.""",
    "EX02": """This is an EX02 Missing Record case. Investigate whether a settlement genuinely \
never occurred, or whether it may simply be pending. Use get_payment to check how old the \
payment is (created_at), get_settlements to confirm none exist, and find_related_records for \
any refund or bank transaction that might explain the absence. A payment created only recently \
should usually NOT be called a confirmed missing settlement -- settlements normally take some \
time to appear, so a young payment with nothing else unusual is more likely still pending than \
genuinely lost. In that case your root_cause_assessment.not_proven should say a genuine missing \
settlement cannot yet be confirmed, and recommendation should reflect that (NO_ACTION or \
HUMAN_REVIEW, not an alarmed conclusion). Only treat it as a confirmed missing record when the \
payment is clearly old relative to normal settlement timing and no related record explains it.""",
    "EX03": """This is an EX03 Duplicate Record case. Use get_settlements to retrieve EVERY \
settlement record referencing this payment -- do not assume there are exactly two; there may be \
more. For each one, note its settlement ID, amount, status, and date, and use \
get_bank_transactions (by each settlement's own reference) to see which are actually confirmed \
by a bank transaction. Report the true duplicate count you observed. Never fabricate an \
additional duplicate record beyond what get_settlements actually returned.""",
}


def _system_prompt(exception_code: str) -> str:
    guidance = _CATEGORY_GUIDANCE.get(exception_code, "")
    return _GENERAL_SYSTEM_PROMPT + ("\n" + guidance if guidance else "")


def _known_facts_message(
    investigation: dict[str, Any], payment_reference: str
) -> str:
    fa = investigation["financial_analysis"] or {}
    return (
        "Investigate this financial reconciliation exception.\n\n"
        "KNOWN, VERIFIED FACTS -- do not recompute, round, or alter these; report them back "
        "exactly as given wherever your output includes a financial_analysis or financial_gap:\n"
        f"- Exception code: {investigation['exception_code']} ({investigation['category']})\n"
        f"- Payment reference: {payment_reference}\n"
        f"- Exception description: {investigation['description']}\n"
        f"- Financial analysis (already computed by the deterministic reconciliation engine): "
        f"{json.dumps(fa)}\n\n"
        "Use the available tools to gather evidence, then call submit_investigation_findings "
        "with your complete conclusion."
    )


def _build_provider() -> AIProvider:
    if AI_PROVIDER == "gemini":
        return GeminiProvider()
    if AI_PROVIDER == "anthropic":
        return AnthropicProvider()
    raise AiInvestigationError(
        f"Unknown AI_PROVIDER {AI_PROVIDER!r} (expected 'anthropic' or 'gemini').",
        status_code=503,
    )


def _validate_financial_values(
    ai_result: AiInvestigationResult, investigation: dict[str, Any], payment_reference: str
) -> None:
    if ai_result.summary.exception_code != investigation["exception_code"]:
        raise AiInvestigationError(
            "AI-reported exception_code does not match this investigation's exception."
        )
    if ai_result.summary.payment_reference != payment_reference:
        raise AiInvestigationError(
            "AI-reported payment_reference does not match this investigation's payment."
        )

    real_fa = investigation["financial_analysis"] or {}

    def _decimal(value: str, field: str) -> Decimal:
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError) as error:
            raise AiInvestigationError(f"AI returned a non-numeric {field}: {value!r}") from error

    for field in ("expected_amount", "observed_amount", "difference"):
        real_value = real_fa.get(field)
        ai_value = getattr(ai_result.financial_analysis, field)
        if real_value is None:
            raise AiInvestigationError(
                f"This investigation's persisted financial_analysis has no {field} to verify against."
            )
        if _decimal(ai_value, field) != _decimal(real_value, field):
            raise AiInvestigationError(
                f"AI-reported {field} ({ai_value}) does not match the verified "
                f"financial_analysis ({real_value}). Rejecting the response."
            )

    real_difference = _decimal(real_fa.get("difference", "0"), "difference")
    ai_gap = _decimal(ai_result.summary.financial_gap, "financial_gap")
    if ai_gap != abs(real_difference):
        raise AiInvestigationError(
            f"AI-reported financial_gap ({ai_result.summary.financial_gap}) does not match the "
            f"verified difference ({real_difference}). Rejecting the response."
        )


def _map_recommendation(ai_recommendation: str) -> str:
    """AI is explicitly allowed to write investigations.recommendation/confidence
    (approved architecture), but that column also gates resolve/escalate
    eligibility (_assert_eligible_for_human_decision requires it to be exactly
    "HUMAN_REVIEW"). HUMAN_REVIEW and ESCALATE both mean "a human needs to look
    at this" from that gate's point of view, so both map to "HUMAN_REVIEW" --
    the AI's own literal recommendation (including "ESCALATE") is still fully
    preserved, verbatim, in the AI_ANALYSIS evidence row and in the API
    response the frontend renders. Only NO_ACTION is written through as-is."""
    if ai_recommendation == "NO_ACTION":
        return "NO_ACTION"
    return "HUMAN_REVIEW"


def _as_uuid_or_none(value: str | None) -> str | None:
    """evidence_reviewed[].record_id is free text from the model -- it's
    not schema-checked as a UUID (Pydantic only requires `str | None`),
    but record_evidence inserts it into a `uuid` column. A record_id the
    model didn't phrase as a real UUID is dropped rather than crashing
    the whole persist step; the human-readable summary text is what
    actually carries the finding."""
    if value is None:
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _persist_results(
    cur,
    conn,
    investigation_id: str,
    ai_result: AiInvestigationResult,
) -> None:
    for item in ai_result.evidence_reviewed:
        record_evidence(
            cur,
            investigation_id,
            "AI_ANALYSIS",
            item.record_type,
            _as_uuid_or_none(item.record_id),
            item.summary,
        )

    hypothesis_rows = [
        HypothesisResult(
            hypothesis=h.title,
            status=h.status,
            confidence=Decimal(h.confidence),
            reasoning=(
                "Supporting evidence: "
                + ("; ".join(h.supporting_evidence) if h.supporting_evidence else "none noted")
                + ". Contradicting evidence: "
                + ("; ".join(h.contradicting_evidence) if h.contradicting_evidence else "none noted")
                + "."
            ),
        )
        for h in ai_result.hypotheses
    ]
    if hypothesis_rows:
        store_hypotheses(cur, investigation_id, hypothesis_rows)

    for contradiction in ai_result.contradictions:
        record_contradiction(cur, investigation_id, contradiction.description)

    rca = ai_result.root_cause_assessment
    record_evidence(
        cur,
        investigation_id,
        "AI_ANALYSIS",
        "ai_conclusion",
        None,
        (
            f"AI conclusion (confidence {ai_result.confidence}%, "
            f"recommendation {ai_result.recommendation}). "
            f"Known: {rca.known} Likely: {rca.likely} Not proven: {rca.not_proven}"
        ),
    )

    root_cause_summary = rca.known if rca.known else rca.likely

    cur.execute(
        """
        update investigations
        set
            root_cause = coalesce(%s, root_cause),
            root_cause_assessment = %s,
            confidence = %s,
            recommendation = %s
        where id = %s
        """,
        (
            root_cause_summary or None,
            json.dumps(
                {"known": rca.known, "likely": rca.likely, "not_proven": rca.not_proven}
            ),
            Decimal(ai_result.confidence),
            _map_recommendation(ai_result.recommendation),
            investigation_id,
        ),
    )

    conn.commit()


def run_ai_investigation(
    investigation_id: str,
    exception_id: str,
    *,
    client: Any | None = None,
    provider: AIProvider | None = None,
) -> dict[str, Any]:
    """`provider` selects (or, in tests, fakes) which AI backend runs --
    see app/ai/providers/. `client` is kept only for backward
    compatibility with the existing Anthropic test suite: passing a fake
    Anthropic client wraps it in AnthropicProvider exactly as before."""
    with connect() as conn:
        with conn.cursor() as cur:
            investigation = get_investigation(cur, investigation_id)

            if investigation is None:
                raise ValueError(f"Investigation {investigation_id} was not found.")

            if investigation["exception_id"] != exception_id:
                raise AiInvestigationError(
                    "The exception id does not match this investigation.", status_code=400
                )

            if investigation["financial_analysis"] is None:
                raise AiInvestigationError(
                    "This investigation has no deterministic financial analysis yet -- "
                    "run the investigation before running the AI Investigator.",
                    status_code=400,
                )

            if investigation["recommendation"] != "HUMAN_REVIEW":
                raise AiInvestigationError(
                    "The AI Investigator only runs on cases the deterministic engine "
                    f"flagged for human review (recommendation is "
                    f"{investigation['recommendation']!r}).",
                    status_code=400,
                )

            payment_reference = extract_payment_reference(investigation["description"])

            if provider is None:
                provider = AnthropicProvider(client=client) if client is not None else _build_provider()

            dispatch = build_tool_dispatch(cur, investigation_id, exception_id)

            try:
                raw_output = provider.run_investigation(
                    system_prompt=_system_prompt(investigation["exception_code"]),
                    user_message=_known_facts_message(investigation, payment_reference),
                    tool_definitions=TOOL_DEFINITIONS,
                    submit_tool_name=SUBMIT_TOOL_NAME,
                    submit_tool_schema=AiInvestigationResult.model_json_schema(),
                    dispatch=dispatch,
                    cur=cur,
                    conn=conn,
                    investigation_id=investigation_id,
                )
            except AIProviderError as error:
                raise AiInvestigationError(str(error), status_code=error.status_code) from error

            try:
                ai_result = AiInvestigationResult.model_validate(raw_output)
            except ValidationError as error:
                raise AiInvestigationError(
                    f"The AI's response did not match the required structure: {error}"
                ) from error

            _validate_financial_values(ai_result, investigation, payment_reference)

            _persist_results(cur, conn, investigation_id, ai_result)

            updated = get_investigation(cur, investigation_id)

    return {
        "investigation": updated,
        "ai_result": ai_result.model_dump(),
    }
