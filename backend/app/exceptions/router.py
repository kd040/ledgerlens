from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.exceptions.store import get_exception, list_exceptions
from app.investigation.runners.deterministic import connect, extract_payment_reference
from app.investigation.tools.settlements import get_settlements

router = APIRouter(
    prefix="/exceptions", tags=["exceptions"], dependencies=[Depends(get_current_user)]
)


@router.get("")
def list_exceptions_endpoint() -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            return list_exceptions(cur)


@router.get("/{exception_id}")
def get_exception_endpoint(exception_id: str) -> dict[str, Any]:
    with connect() as conn:
        with conn.cursor() as cur:
            exception = get_exception(cur, exception_id)

    if exception is None:
        raise HTTPException(status_code=404, detail="Exception not found")

    return exception


@router.get("/{exception_id}/duplicate-settlements")
def get_exception_duplicate_settlements(exception_id: str) -> dict[str, Any]:
    """The individual settlement records behind an EX03 exception -- the
    same rows the deterministic duplicate-record investigation already
    retrieves (see get_settlements / run_duplicate_record_investigation),
    exposed directly so the UI can show them before an investigation
    has even been started. Not gated to EX03: any exception's payment
    may have 0, 1, or several settlements, and returning whatever
    exists is more honest than pretending duplicates are exclusive to
    one exception code."""
    with connect() as conn:
        with conn.cursor() as cur:
            exception = get_exception(cur, exception_id)

            if exception is None:
                raise HTTPException(status_code=404, detail="Exception not found")

            try:
                payment_reference = extract_payment_reference(exception["description"])
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error))

            settlements = get_settlements(cur, payment_reference)

    return {"payment": payment_reference, "settlements": settlements}
