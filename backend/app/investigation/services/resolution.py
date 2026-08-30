"""Human-in-the-loop resolution/escalation for investigations the
deterministic engine recommended for human review.
determine_investigation_outcome() (services/completion.py) never marks a
financially-discrepant case resolved on its own -- HUMAN_REVIEW is the
terminal automated state. This is the one place that closes it out, and
it always requires a human-entered note.

The reviewer identity is the authenticated user's email (see
app/auth/dependencies.py's require_reviewer), threaded in by the router
-- never a fabricated actor.

Resolved-vs-escalated is recorded on `investigations.human_decision`
(migration 007), a field dedicated to the human's own decision -- kept
separate from `investigations.recommendation`, which stays purely
AI-authored (NO_ACTION / HUMAN_REVIEW), so escalation has a value of its
own to write without further overloading that column. Both actions are
recorded as investigation_evidence (the existing audit trail every
other tool call/evidence record already uses) -- HUMAN_DECISION is the
one evidence_type value both share, nothing else changes.
"""

from typing import Any

from app.investigation.services.audit import record_evidence


class ResolutionError(ValueError):
    pass


def _assert_eligible_for_human_decision(investigation: dict[str, Any]) -> None:
    if investigation["recommendation"] != "HUMAN_REVIEW":
        raise ResolutionError(
            "This investigation is not awaiting human review "
            f"(recommendation is {investigation['recommendation']!r})."
        )

    if investigation.get("human_decision") is not None:
        raise ResolutionError(
            "This investigation was already "
            f"{investigation['human_decision'].lower()} by a reviewer."
        )


def resolve_investigation(
    cur,
    investigation_id: str,
    investigation: dict[str, Any],
    note: str,
    reviewer_email: str,
) -> dict[str, Any]:
    note = note.strip()
    if not note:
        raise ResolutionError("A resolution note is required.")

    _assert_eligible_for_human_decision(investigation)

    previous_status = investigation["status"]
    previous_recommendation = investigation["recommendation"]

    cur.execute(
        """
        update investigations
        set status = 'COMPLETED', recommendation = 'RESOLVED', human_decision = 'RESOLVED'
        where id = %s
        """,
        (investigation_id,),
    )

    cur.execute(
        "update exceptions set status = 'RESOLVED', updated_at = now() where id = %s",
        (investigation["exception_id"],),
    )

    evidence_id = record_evidence(
        cur,
        investigation_id,
        "HUMAN_DECISION",
        "investigation",
        investigation_id,
        (
            f"Resolved by human review. Previous status: {previous_status} "
            f"(recommendation: {previous_recommendation}). "
            f"Reviewer: {reviewer_email}. Note: {note}"
        ),
    )

    return {"evidence_id": evidence_id}


def escalate_investigation(
    cur,
    investigation_id: str,
    investigation: dict[str, Any],
    note: str,
    reviewer_email: str,
) -> dict[str, Any]:
    note = note.strip()
    if not note:
        raise ResolutionError("An escalation note is required.")

    _assert_eligible_for_human_decision(investigation)

    previous_status = investigation["status"]
    previous_recommendation = investigation["recommendation"]

    cur.execute(
        """
        update investigations
        set status = 'ESCALATED', human_decision = 'ESCALATED'
        where id = %s
        """,
        (investigation_id,),
    )

    cur.execute(
        "update exceptions set status = 'ESCALATED', updated_at = now() where id = %s",
        (investigation["exception_id"],),
    )

    evidence_id = record_evidence(
        cur,
        investigation_id,
        "HUMAN_DECISION",
        "investigation",
        investigation_id,
        (
            f"Escalated by human review. Previous status: {previous_status} "
            f"(recommendation: {previous_recommendation}). "
            f"Reviewer: {reviewer_email}. Note: {note}"
        ),
    )

    return {"evidence_id": evidence_id}
