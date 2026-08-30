"""Razorpay payload -> LedgerLens internal row shapes.

This is the one place Razorpay's field names/units get translated. The
reconciliation engine never sees a Razorpay payload -- only the rows
these functions produce, in exactly the shape the existing payments/
settlements/fees/taxes tables already expect.

Field semantics verified against Razorpay's own documented example
response for Settlement Recon Details (GET /settlements/recon/combined)
before writing this -- notably:

- For a recon line item of type == "payment", `payment_id` is null.
  The payment's own id is `entity_id`. (`payment_id` is only populated
  on refund/transfer items, linking back to the payment they came
  from.) Getting this backwards would silently produce settlement rows
  that never join to any payment.
- `credit` is the net amount actually credited for that line item --
  verified against the example (credit == amount - fee - tax), so it
  maps to LedgerLens's settlement_amount, not `amount` (which is the
  gross payment amount, already captured separately as the payment's
  own `amount`).
- `settled` / `settled_at` are per-line-item, not batch-level.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TypedDict


class NormalizedPayment(TypedDict):
    external_payment_id: str
    amount: Decimal
    currency: str
    status: str
    method: str | None
    created_at: datetime


class NormalizedSettlement(TypedDict):
    external_settlement_id: str
    payment_reference: str
    settlement_amount: Decimal
    fee_amount: Decimal
    tax_amount: Decimal
    status: str
    settlement_date: datetime
    razorpay_settlement_id: str
    utr: str | None


def _paise_to_rupees(value: int) -> Decimal:
    return Decimal(value) / Decimal(100)


def _from_unix(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def normalize_payment(raw: dict[str, Any]) -> NormalizedPayment:
    return {
        "external_payment_id": raw["id"],
        "amount": _paise_to_rupees(raw["amount"]),
        "currency": raw.get("currency", "INR"),
        "status": raw["status"],
        "method": raw.get("method"),
        "created_at": _from_unix(raw["created_at"]),
    }


def normalize_settlement_recon_line(item: dict[str, Any]) -> NormalizedSettlement | None:
    """Normalizes one Settlement Recon Details line item into a settlement
    row -- only for type == "payment" lines (refund/transfer/adjustment
    lines aren't a payment's settlement and are out of scope here; see
    the integration report for why).

    A real Razorpay settlement batches many payments together, which the
    existing settlements table (one row per payment, via `reference`)
    doesn't model. external_settlement_id is therefore a composite
    "{settlement_id}:{payment_id}" -- the real settlement_id stays fully
    traceable in both the id itself and razorpay_settlement_id, this is
    just choosing a per-payment row granularity to match what the
    existing schema/reconciliation engine already expects.
    """
    if item.get("type") != "payment":
        return None

    payment_reference = item["entity_id"]  # NOT item["payment_id"] -- null here
    settlement_id = item["settlement_id"]
    settled_at = item.get("settled_at") or item.get("created_at")

    return {
        "external_settlement_id": f"{settlement_id}:{payment_reference}",
        "payment_reference": payment_reference,
        "settlement_amount": _paise_to_rupees(item["credit"]),
        "fee_amount": _paise_to_rupees(item.get("fee", 0)),
        "tax_amount": _paise_to_rupees(item.get("tax", 0)),
        "status": "SETTLED" if item.get("settled") else "PENDING",
        "settlement_date": _from_unix(settled_at),
        "razorpay_settlement_id": settlement_id,
        "utr": item.get("settlement_utr"),
    }
