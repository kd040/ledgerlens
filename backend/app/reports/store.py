"""Read-only reporting aggregates for the Finance Controller view.

Every number here is summed straight out of the tables the
reconciliation engine and the investigation flow already wrote -- this
module never re-runs reconciliation, never writes, and never invents a
figure. Where a formula is unavoidable (expected settlement, and
therefore the financial gap) it is the engine's own formula --
`gross - fees - taxes + adjustments`, see reconciliation/engine.py --
expressed as an aggregate rather than a per-payment loop.

Date scoping: each section is filtered on its own natural timestamp,
because that is the only one it has. Payments/settlement financials use
`payments.created_at`, exceptions use `exceptions.created_at`,
investigations use `investigations.started_at`. The UI labels each
section with its basis rather than implying one global filter.
"""

from decimal import Decimal
from typing import Any

from app.reconciliation.engine import SETTLEABLE_PAYMENT_STATUSES

# Exceptions persist only OPEN / RESOLVED / ESCALATED (see
# reconciliation/engine.py's create_exception and
# investigation/services/resolution.py). IN_PROGRESS and HUMAN_REVIEW
# are investigation-level states, so an exception's workflow position is
# derived from its investigation -- from stored values only, never a
# status string the database doesn't actually hold.
_EXCEPTION_WORKFLOW_STATUS = """
    case
        when e.status = 'RESOLVED' then 'RESOLVED'
        when e.status = 'ESCALATED' then 'ESCALATED'
        when i.id is null then 'OPEN'
        when i.recommendation = 'HUMAN_REVIEW' and i.human_decision is null
            then 'HUMAN_REVIEW'
        else 'IN_PROGRESS'
    end
"""

EXCEPTION_WORKFLOW_STATUSES = [
    "OPEN",
    "IN_PROGRESS",
    "HUMAN_REVIEW",
    "RESOLVED",
    "ESCALATED",
]

# Same precedence as the frontend's investigationOutcomePresentation
# (src/lib/status.ts), so Reports and Overview can never disagree about
# what one investigation's outcome is. Mutually exclusive by
# construction: the first matching branch wins.
_INVESTIGATION_OUTCOME = """
    case
        when i.status = 'ESCALATED' then 'ESCALATED'
        when i.recommendation = 'RESOLVED' then 'RESOLVED'
        when i.status = 'COMPLETED' and i.recommendation = 'NO_ACTION'
            then 'RESOLVED'
        when i.recommendation = 'HUMAN_REVIEW' then 'HUMAN_REVIEW'
        else 'IN_PROGRESS'
    end
"""

EXCEPTION_CODE_LABELS = {
    "EX01": "Amount Mismatch",
    "EX02": "Missing Record",
    "EX03": "Duplicate Record",
}


def _range_clause(column: str, start: str | None, end: str | None) -> tuple[str, list]:
    """`end` is inclusive of its whole calendar day -- a controller
    picking 24th to 26th means through the end of the 26th."""
    parts: list[str] = []
    params: list[Any] = []

    if start:
        parts.append(f"{column} >= %s::date")
        params.append(start)
    if end:
        parts.append(f"{column} < %s::date + 1")
        params.append(end)

    return (" and ".join(parts) if parts else "true"), params


def _money(value: Any) -> str:
    return str(value if value is not None else Decimal("0.00"))


def _financial_control(cur, start: str | None, end: str | None) -> dict[str, Any]:
    clause, params = _range_clause("p.created_at", start, end)

    cur.execute(
        f"""
        with settlement_costs as (
            select
                s.id,
                s.reference,
                s.settlement_amount,
                coalesce((select sum(amount) from fees
                          where settlement_id = s.id), 0) as fee,
                coalesce((select sum(amount) from taxes
                          where settlement_id = s.id), 0) as tax,
                coalesce((select sum(amount) from adjustments
                          where settlement_id = s.id), 0) as adjustment
            from settlements s
        ),
        per_payment as (
            select
                p.id,
                p.amount as gross,
                lower(p.status) <> all(%s) as not_captured,
                count(sc.id) as settlement_count,
                coalesce(sum(sc.settlement_amount), 0) as observed,
                coalesce(sum(sc.fee), 0) as fee,
                coalesce(sum(sc.tax), 0) as tax,
                coalesce(sum(sc.adjustment), 0) as adjustment
            from payments p
            left join settlement_costs sc
                on sc.reference = p.external_payment_id
            where {clause}
            group by p.id, p.amount
        )
        select
            count(*),
            coalesce(sum(gross) filter (where not not_captured), 0),
            coalesce(sum(observed), 0),
            coalesce(sum(fee), 0),
            coalesce(sum(tax), 0),
            coalesce(sum(adjustment), 0),
            coalesce(sum(gross - fee - tax + adjustment)
                     filter (where settlement_count = 1), 0),
            coalesce(sum(observed) filter (where settlement_count = 1), 0),
            count(*) filter (
                where settlement_count = 1
                  and gross - fee - tax + adjustment = observed
            ),
            coalesce(sum(observed) filter (
                where settlement_count = 1
                  and gross - fee - tax + adjustment = observed
            ), 0),
            count(*) filter (where settlement_count > 1),
            coalesce(sum(observed) filter (where settlement_count > 1), 0),
            count(*) filter (where settlement_count = 0 and not not_captured),
            coalesce(
                sum(gross) filter (where settlement_count = 0 and not not_captured), 0
            ),
            count(*) filter (where not_captured),
            coalesce(sum(gross) filter (where not_captured), 0)
        from per_payment
        """,
        [sorted(SETTLEABLE_PAYMENT_STATUSES)] + params,
    )

    (
        total_payments,
        gross,
        observed,
        fee,
        tax,
        adjustment,
        expected_matched,
        observed_matched,
        reconciled_count,
        reconciled_amount,
        duplicate_count,
        duplicate_amount,
        unsettled_count,
        unsettled_amount,
        not_captured_count,
        not_captured_amount,
    ) = cur.fetchone()

    return {
        "total_payments": total_payments,
        # "Gross processed" -- the value of payments that actually became
        # money owed to the merchant. Payments the provider never
        # captured are excluded here and reported on their own line
        # below, so this figure means the same thing as the Overview and
        # Reconciliation pages' own gross (see
        # countsTowardGrossProcessed in frontend/src/lib/status.ts).
        "total_payment_value": _money(gross),
        "total_settled_value": _money(observed),
        "total_fees": _money(fee),
        "total_taxes": _money(tax),
        "total_adjustments": _money(adjustment),
        "expected_settlement_value": _money(expected_matched),
        # Deliberately scoped to payments with exactly one settlement --
        # the only ones where expected and observed are comparable. A
        # duplicate-settled payment contributes two observed amounts to
        # one expected amount, so folding it in here would drive the gap
        # negative and misreport an over-settlement as a surplus. Its
        # exposure is reported by duplicate_settlement_value below and by
        # the EX03 line in exception_exposure; an unsettled payment's by
        # unsettled_payment_value and the EX02 line.
        "total_financial_gap": _money(expected_matched - observed_matched),
        "reconciled_payments": reconciled_count,
        "reconciled_amount": _money(reconciled_amount),
        "duplicate_settled_payments": duplicate_count,
        "duplicate_settlement_value": _money(duplicate_amount),
        # Captured money that has not been settled -- both the genuine
        # EX02s and the ones still inside the provider's settlement
        # window. Payments the provider never captured are deliberately
        # excluded: that money was never owed, so counting it as
        # unsettled would overstate exposure (see
        # NON_SETTLEABLE_PAYMENT_STATUSES).
        "unsettled_payments": unsettled_count,
        "unsettled_payment_value": _money(unsettled_amount),
        "not_captured_payments": not_captured_count,
        "not_captured_value": _money(not_captured_amount),
    }


def _exception_analysis(cur, start: str | None, end: str | None) -> dict[str, Any]:
    clause, params = _range_clause("e.created_at", start, end)

    cur.execute(
        f"""
        select
            e.exception_code,
            count(*),
            coalesce(sum(e.financial_impact), 0)
        from exceptions e
        where {clause}
        group by e.exception_code
        order by e.exception_code
        """,
        params,
    )

    by_code = [
        {
            "code": row[0],
            "label": EXCEPTION_CODE_LABELS.get(row[0], row[0]),
            "count": row[1],
            "financial_impact": _money(row[2]),
        }
        for row in cur.fetchall()
    ]

    cur.execute(
        f"""
        select {_EXCEPTION_WORKFLOW_STATUS}, count(*)
        from exceptions e
        left join investigations i on i.exception_id = e.id
        where {clause}
        group by 1
        """,
        params,
    )

    counted = dict(cur.fetchall())
    by_status = {
        status: counted.get(status, 0) for status in EXCEPTION_WORKFLOW_STATUSES
    }

    return {
        "total": sum(item["count"] for item in by_code),
        "by_code": by_code,
        "by_status": by_status,
        # The one number answering "how much money is currently affected
        # by exceptions?" -- each exception's own persisted
        # financial_impact, exactly as the engine wrote it.
        "exception_exposure": _money(
            sum(Decimal(item["financial_impact"]) for item in by_code)
        ),
    }


def _investigation_outcomes(cur, start: str | None, end: str | None) -> dict[str, Any]:
    clause, params = _range_clause("i.started_at", start, end)

    cur.execute(
        f"""
        select
            count(*),
            count(*) filter (where i.root_cause_assessment is not null),
            count(*) filter (where {_INVESTIGATION_OUTCOME} = 'HUMAN_REVIEW'),
            count(*) filter (where {_INVESTIGATION_OUTCOME} = 'RESOLVED'),
            count(*) filter (where {_INVESTIGATION_OUTCOME} = 'ESCALATED'),
            count(*) filter (where {_INVESTIGATION_OUTCOME} = 'IN_PROGRESS')
        from investigations i
        where {clause}
        """,
        params,
    )

    total, ai_count, human_review, resolved, escalated, in_progress = cur.fetchone()

    def rate(count: int) -> float:
        return round(count / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "ai_investigations": ai_count,
        "awaiting_human_review": human_review,
        "resolved": resolved,
        "escalated": escalated,
        "in_progress": in_progress,
        "resolution_rate": rate(resolved),
        "escalation_rate": rate(escalated),
    }


def _ai_insights(cur, start: str | None, end: str | None) -> dict[str, Any]:
    clause, params = _range_clause("i.started_at", start, end)

    # root_cause_assessment is the AI-only column (migration 008) -- the
    # deterministic runner never populates it, so it is the honest
    # marker of "an AI investigation actually ran here", and confidence
    # is averaged over those rows alone rather than over every
    # investigation.
    cur.execute(
        f"""
        select
            count(*) filter (where i.root_cause_assessment is not null),
            avg(i.confidence) filter (where i.root_cause_assessment is not null),
            count(*) filter (
                where i.recommendation = 'HUMAN_REVIEW'
                  and i.human_decision is null
            ),
            count(*) filter (where i.human_decision = 'RESOLVED'),
            count(*) filter (where i.human_decision = 'ESCALATED')
        from investigations i
        where {clause}
        """,
        params,
    )

    ai_count, avg_confidence, human_review, decided_resolved, decided_escalated = (
        cur.fetchone()
    )

    cur.execute(
        f"""
        select e.category, count(*)
        from investigations i
        join exceptions e on e.id = i.exception_id
        where {clause}
        group by e.category
        order by count(*) desc, e.category
        """,
        params,
    )

    return {
        "investigation_count": ai_count,
        "average_confidence": (
            str(round(avg_confidence, 1)) if avg_confidence is not None else None
        ),
        "human_review_count": human_review,
        "human_decisions": {
            "RESOLVED": decided_resolved,
            "ESCALATED": decided_escalated,
        },
        # Investigations carry a free-text root_cause sentence, which
        # does not group. The exception's `category` is the real
        # persisted classification, so that is what gets counted.
        "root_cause_categories": [
            {"category": row[0], "count": row[1]} for row in cur.fetchall()
        ],
    }


def get_report_summary(
    cur, start: str | None = None, end: str | None = None
) -> dict[str, Any]:
    return {
        "period": {"start": start, "end": end},
        "financial_control": _financial_control(cur, start, end),
        "exceptions": _exception_analysis(cur, start, end),
        "investigations": _investigation_outcomes(cur, start, end),
        "ai": _ai_insights(cur, start, end),
    }


def get_available_period(cur) -> dict[str, str | None]:
    """The full span the report can cover, so the UI's date inputs can
    default to the real data range instead of an arbitrary window."""
    cur.execute(
        """
        select
            min(earliest)::date::text,
            max(latest)::date::text
        from (
            select min(created_at) as earliest, max(created_at) as latest
                from payments
            union all
            select min(created_at), max(created_at) from exceptions
            union all
            select min(started_at), max(started_at) from investigations
        ) spans
        """
    )
    row = cur.fetchone()
    return {"start": row[0], "end": row[1]}
