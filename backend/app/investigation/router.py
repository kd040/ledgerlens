from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.investigation.runners.deterministic import (
    connect,
    run_amount_mismatch_investigation,
    run_duplicate_record_investigation,
    run_missing_record_investigation,
)
from app.investigation.services.audit import list_evidence, list_tool_calls
from app.investigation.services.contradictions import list_contradictions
from app.investigation.services.hypothesis_store import list_hypotheses
from app.investigation.services.investigation_store import (
    create_investigation,
    get_investigation,
    list_investigations,
)


router = APIRouter(prefix="/investigations", tags=["investigations"])

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
