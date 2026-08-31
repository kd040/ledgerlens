from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.investigation.runners.deterministic import connect
from app.reports.store import get_available_period, get_report_summary

router = APIRouter(
    prefix="/reports", tags=["reports"], dependencies=[Depends(get_current_user)]
)


@router.get("/summary")
def get_report_summary_endpoint(
    start: str | None = None, end: str | None = None
) -> dict[str, Any]:
    """One aggregated payload backing the whole Reports page -- read-only
    and available to any authenticated user (Analyst or Reviewer): a
    report is a read, never a resolve/escalate action, so it does not
    require require_reviewer. Never public: the router-level
    get_current_user dependency gates every route here."""
    if start and end and start > end:
        raise HTTPException(
            status_code=400, detail="Start date must not be after end date."
        )

    with connect() as conn:
        with conn.cursor() as cur:
            try:
                summary = get_report_summary(cur, start, end)
                summary["available_period"] = get_available_period(cur)
            except Exception as error:
                # A malformed date reaches Postgres as an invalid cast --
                # a client input problem, not a server fault.
                if "invalid input syntax" in str(error):
                    raise HTTPException(
                        status_code=400,
                        detail="Dates must be in YYYY-MM-DD format.",
                    )
                raise

    return summary
