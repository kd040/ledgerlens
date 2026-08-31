from decimal import Decimal
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.datasources import SOURCES
from app.datasources.razorpay.client import RazorpayApiError, RazorpayConfigError
from app.reconciliation.engine import reconcile_payments

router = APIRouter(
    prefix="/reconciliation/sources",
    tags=["datasources"],
    dependencies=[Depends(get_current_user)],
)


class RunSourceRequest(BaseModel):
    source: str
    from_: datetime = Field(alias="from")
    to: datetime

    model_config = {"populate_by_name": True}


@router.post("/run")
def run_source(body: RunSourceRequest) -> dict[str, Any]:
    source_fn = SOURCES.get(body.source)

    if source_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source '{body.source}'. Available: {list(SOURCES)}",
        )

    try:
        fetch_result = source_fn(body.from_, body.to)
    except RazorpayConfigError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except RazorpayApiError as error:
        raise HTTPException(status_code=502, detail=str(error))

    reconciliation_results = reconcile_payments(
        payment_ids=fetch_result["payment_ids"],
        settlement_pending_business_days=fetch_result.get("settlement_pending_days"),
    )

    counts = {
        "reconciled": 0,
        "ex01": 0,
        "ex02": 0,
        "ex03": 0,
        "settlement_pending": 0,
        # A payment the provider never captured -- counted so the buckets
        # still add up to records_processed, never folded into exceptions.
        "not_captured": 0,
        # A payment whose provider status this engine does not recognise.
        "unknown_status": 0,
    }
    financial_impact = Decimal("0.00")
    for row in reconciliation_results:
        key = row["status"].lower()
        if key in counts:
            counts[key] += 1
        if "difference" in row:
            financial_impact += Decimal(row["difference"])

    return {
        "source": body.source,
        "requested_period": {
            "from": body.from_.isoformat(),
            "to": body.to.isoformat(),
        },
        "records_fetched": {
            "payments": fetch_result["payments_fetched"],
            "settlements": fetch_result["settlements_normalized"],
        },
        "records_processed": len(reconciliation_results),
        "reconciliation": counts,
        "financial_impact": str(financial_impact),
        "duration_seconds": round(fetch_result["duration_seconds"], 3),
        "results": reconciliation_results,
    }
