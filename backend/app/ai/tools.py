"""Claude-facing tool wrappers around the EXISTING read-only investigation
tools (backend/app/investigation/tools/*.py, services/*.py) -- no
business logic is duplicated here, every function below just adapts an
already-existing function's arguments/return shape for the model and
records the call.

The model never receives a database cursor, a connection string, or any
credential. Each wrapper is a closure over one already-open cursor (and
this investigation's id) supplied by investigator.py -- the model only
ever sees and passes plain JSON-serializable arguments.

Nothing here writes to the database except the tool-call audit record
(record_tool_call) -- these are read tools.
"""

import json
from typing import Any, Callable

from app.investigation.runners.deterministic import load_payment_by_reference
from app.investigation.services.audit import record_tool_call
from app.investigation.services.contradictions import list_contradictions
from app.investigation.services.hypothesis_store import list_hypotheses
from app.investigation.tools.adjustments import get_adjustments
from app.investigation.tools.bank_transactions import get_bank_transactions
from app.investigation.tools.exceptions import get_exception
from app.investigation.tools.fees import get_fees
from app.investigation.tools.related_records import find_related_records
from app.investigation.tools.settlements import get_settlements
from app.investigation.tools.taxes import get_taxes
from app.investigation.services.audit import list_evidence as _list_evidence

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_payment",
        "description": "Look up the payment by its external reference (e.g. 'pay_xxx' or 'PAY-001').",
        "input_schema": {
            "type": "object",
            "properties": {"payment_reference": {"type": "string"}},
            "required": ["payment_reference"],
        },
    },
    {
        "name": "get_settlements",
        "description": "List every settlement record referencing this payment (0, 1, or several -- several means a duplicate).",
        "input_schema": {
            "type": "object",
            "properties": {"payment_reference": {"type": "string"}},
            "required": ["payment_reference"],
        },
    },
    {
        "name": "get_fees",
        "description": "List the fee line items charged against one settlement.",
        "input_schema": {
            "type": "object",
            "properties": {"settlement_id": {"type": "string"}},
            "required": ["settlement_id"],
        },
    },
    {
        "name": "get_taxes",
        "description": "List the tax line items charged against one settlement.",
        "input_schema": {
            "type": "object",
            "properties": {"settlement_id": {"type": "string"}},
            "required": ["settlement_id"],
        },
    },
    {
        "name": "get_adjustments",
        "description": "List the adjustment line items applied to one settlement.",
        "input_schema": {
            "type": "object",
            "properties": {"settlement_id": {"type": "string"}},
            "required": ["settlement_id"],
        },
    },
    {
        "name": "get_bank_transactions",
        "description": "List bank transactions confirming one settlement, by the settlement's own external reference.",
        "input_schema": {
            "type": "object",
            "properties": {"settlement_reference": {"type": "string"}},
            "required": ["settlement_reference"],
        },
    },
    {
        "name": "find_related_records",
        "description": "Find settlements, refunds, and bank transactions related to a payment reference in one call.",
        "input_schema": {
            "type": "object",
            "properties": {"payment_reference": {"type": "string"}},
            "required": ["payment_reference"],
        },
    },
    {
        "name": "get_exception",
        "description": "Fetch this investigation's own exception record (code, category, description, financial impact).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_investigation_evidence",
        "description": "List evidence already recorded on this investigation (from the deterministic engine and/or an earlier AI run).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_investigation_hypotheses",
        "description": "List hypotheses already evaluated on this investigation.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_investigation_contradictions",
        "description": "List contradictions already detected on this investigation.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def build_tool_dispatch(
    cur, investigation_id: str, exception_id: str
) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Closures over one open cursor + this investigation's ids. Every
    dispatched call is recorded via the existing record_tool_call --
    the caller (investigator.py) is responsible for committing."""

    def _get_payment(args: dict[str, Any]) -> Any:
        payment = load_payment_by_reference(cur, args["payment_reference"])
        return payment

    def _get_settlements(args: dict[str, Any]) -> Any:
        return get_settlements(cur, args["payment_reference"])

    def _get_fees(args: dict[str, Any]) -> Any:
        return get_fees(cur, args["settlement_id"])

    def _get_taxes(args: dict[str, Any]) -> Any:
        return get_taxes(cur, args["settlement_id"])

    def _get_adjustments(args: dict[str, Any]) -> Any:
        return get_adjustments(cur, args["settlement_id"])

    def _get_bank_transactions(args: dict[str, Any]) -> Any:
        return get_bank_transactions(cur, args["settlement_reference"])

    def _find_related_records(args: dict[str, Any]) -> Any:
        return find_related_records(cur, args["payment_reference"])

    def _get_exception(_args: dict[str, Any]) -> Any:
        return get_exception(cur, exception_id)

    def _get_investigation_evidence(_args: dict[str, Any]) -> Any:
        return _list_evidence(cur, investigation_id)

    def _get_investigation_hypotheses(_args: dict[str, Any]) -> Any:
        return list_hypotheses(cur, investigation_id)

    def _get_investigation_contradictions(_args: dict[str, Any]) -> Any:
        return list_contradictions(cur, investigation_id)

    return {
        "get_payment": _get_payment,
        "get_settlements": _get_settlements,
        "get_fees": _get_fees,
        "get_taxes": _get_taxes,
        "get_adjustments": _get_adjustments,
        "get_bank_transactions": _get_bank_transactions,
        "find_related_records": _find_related_records,
        "get_exception": _get_exception,
        "get_investigation_evidence": _get_investigation_evidence,
        "get_investigation_hypotheses": _get_investigation_hypotheses,
        "get_investigation_contradictions": _get_investigation_contradictions,
    }


class ToolExecutionError(ValueError):
    pass


def execute_tool(
    cur,
    investigation_id: str,
    dispatch: dict[str, Callable[[dict[str, Any]], Any]],
    tool_name: str,
    tool_input: dict[str, Any],
) -> Any:
    """Runs one tool call and records it via the existing
    investigation_tool_calls audit mechanism -- exactly the same
    record_tool_call the deterministic runners already use, so AI tool
    activity shows up in the same Audit drawer/Timeline unmodified.

    Recorded whether the call succeeds or fails: a failed lookup (e.g. an
    id the model got wrong) is still something that was actually
    attempted against real data, and belongs in the audit trail exactly
    as much as a successful one."""
    handler = dispatch.get(tool_name)

    if handler is None:
        error_result = {"error": f"Unknown tool: {tool_name}"}
        record_tool_call(cur, investigation_id, tool_name, tool_input, error_result)
        raise ToolExecutionError(f"Unknown tool: {tool_name}")

    try:
        result = handler(tool_input)
    except Exception as error:
        error_result = {"error": str(error)}
        record_tool_call(cur, investigation_id, tool_name, tool_input, error_result)
        raise

    record_tool_call(cur, investigation_id, tool_name, tool_input, _jsonable(result))

    return result


def _jsonable(value: Any) -> Any:
    """record_tool_call json.dumps()s arguments/result itself -- this
    only guards against a non-JSON-serializable tool return sneaking
    through (e.g. a stray Decimal), failing loudly instead of at the
    DB call. Every existing tool already returns str-ified Decimals, so
    this is a safety net, not the primary conversion path."""
    json.dumps(value)
    return value


__all__ = [
    "TOOL_DEFINITIONS",
    "build_tool_dispatch",
    "execute_tool",
    "ToolExecutionError",
]
