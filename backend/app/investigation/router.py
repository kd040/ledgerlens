from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.ai.investigator import AiInvestigationError, run_ai_investigation
from app.auth.dependencies import get_current_user, require_reviewer
from app.investigation.runners.deterministic import (
    connect,
    extract_payment_reference,
    load_payment_by_reference,
    run_amount_mismatch_investigation,
    run_duplicate_record_investigation,
    run_missing_record_investigation,
)
from app.investigation.services.audit import list_evidence, list_tool_calls
from app.investigation.services.contradictions import list_contradictions
from app.investigation.services.daily_financials import (
    get_daily_financials,
    list_available_dates,
)
from app.investigation.services.hypothesis_store import list_hypotheses
from app.investigation.services.investigation_store import (
    create_investigation,
    get_investigation,
    list_investigations,
)
from app.investigation.services.resolution import (
    ResolutionError,
    escalate_investigation,
    resolve_investigation,
)


router = APIRouter(
    prefix="/investigations",
    tags=["investigations"],
    dependencies=[Depends(get_current_user)],
)

CATEGORY_RUNNERS = {
    "Amount Mismatch": run_amount_mismatch_investigation,
    "Missing Record": run_missing_record_investigation,
    "Duplicate Record": run_duplicate_record_investigation,
}


class CreateInvestigationRequest(BaseModel):
    exception_id: str


@router.post("")
def create_investigation_endpoint(
    body: CreateInvestigationRequest,
) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            try:
                investigation = create_investigation(cur, body.exception_id)
            except ValueError as error:
                raise HTTPException(status_code=404, detail=str(error))

            conn.commit()

    return investigation


@router.get("")
def list_investigations_endpoint() -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            return list_investigations(cur)


@router.get("/{investigation_id}")
def get_investigation_endpoint(investigation_id: str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            investigation = get_investigation(cur, investigation_id)

    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    return investigation


@router.post("/{investigation_id}/run")
def run_investigation_endpoint(investigation_id: str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            investigation = get_investigation(cur, investigation_id)

    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    runner = CATEGORY_RUNNERS.get(investigation["category"])

    if runner is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No investigation runner is implemented for "
                f"category '{investigation['category']}' yet."
            ),
        )

    try:
        return runner(investigation_id, investigation["exception_id"])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/{investigation_id}/ai-investigate")
def ai_investigate_endpoint(investigation_id: str) -> dict[str, Any]:
    """Additive AI analysis layer on top of an already-run deterministic
    investigation -- see app/ai/investigator.py. Any authenticated user
    (Analyst or Reviewer) may trigger this: it is a read/analysis
    operation, never a resolve/escalate action, so it does not require
    require_reviewer."""
    with connect() as conn:
        with conn.cursor() as cur:
            investigation = get_investigation(cur, investigation_id)

    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    try:
        result = run_ai_investigation(investigation_id, investigation["exception_id"])
    except AiInvestigationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))

    return result["investigation"]


@router.get("/{investigation_id}/evidence")
def get_investigation_evidence(investigation_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            return list_evidence(cur, investigation_id)


@router.get("/{investigation_id}/hypotheses")
def get_investigation_hypotheses(investigation_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            return list_hypotheses(cur, investigation_id)


@router.get("/{investigation_id}/tool-calls")
def get_investigation_tool_calls(investigation_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            return list_tool_calls(cur, investigation_id)


@router.get("/{investigation_id}/contradictions")
def get_investigation_contradictions(
    investigation_id: str,
) -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            if get_investigation(cur, investigation_id) is None:
                raise HTTPException(
                    status_code=404, detail="Investigation not found"
                )

            return list_contradictions(cur, investigation_id)


@router.get("/{investigation_id}/financials/daily")
def get_investigation_daily_financials(
    investigation_id: str, date: str | None = None
) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            investigation = get_investigation(cur, investigation_id)

            if investigation is None:
                raise HTTPException(
                    status_code=404, detail="Investigation not found"
                )

            try:
                payment_reference = extract_payment_reference(
                    investigation["description"]
                )
                payment = load_payment_by_reference(cur, payment_reference)
            except ValueError as error:
                raise HTTPException(status_code=404, detail=str(error))

            available_dates = list_available_dates(cur, payment_reference)

            if not available_dates:
                return {
                    "available_dates": [],
                    "selected_date": None,
                    "financials": None,
                }

            selected_date = date if date in available_dates else available_dates[0]
            financials = get_daily_financials(
                cur, payment, payment_reference, selected_date
            )

    return {
        "available_dates": available_dates,
        "selected_date": selected_date,
        "financials": financials,
    }


class ResolveInvestigationRequest(BaseModel):
    note: str


@router.post("/{investigation_id}/resolve")
def resolve_investigation_endpoint(
    investigation_id: str,
    body: ResolveInvestigationRequest,
    reviewer: dict = Depends(require_reviewer),
) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            investigation = get_investigation(cur, investigation_id)

            if investigation is None:
                raise HTTPException(
                    status_code=404, detail="Investigation not found"
                )

            try:
                resolve_investigation(
                    cur, investigation_id, investigation, body.note, reviewer["email"]
                )
            except ResolutionError as error:
                raise HTTPException(status_code=400, detail=str(error))

            conn.commit()

            return get_investigation(cur, investigation_id)


class EscalateInvestigationRequest(BaseModel):
    note: str


@router.post("/{investigation_id}/escalate")
def escalate_investigation_endpoint(
    investigation_id: str,
    body: EscalateInvestigationRequest,
    reviewer: dict = Depends(require_reviewer),
) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            investigation = get_investigation(cur, investigation_id)

            if investigation is None:
                raise HTTPException(
                    status_code=404, detail="Investigation not found"
                )

            try:
                escalate_investigation(
                    cur, investigation_id, investigation, body.note, reviewer["email"]
                )
            except ResolutionError as error:
                raise HTTPException(status_code=400, detail=str(error))

            conn.commit()

            return get_investigation(cur, investigation_id)
