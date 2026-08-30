-- LedgerLens
-- Migration 007: Separate the human reviewer's decision from the AI's
-- own recommendation.
--
-- investigations.recommendation is AI-authored (NO_ACTION / HUMAN_REVIEW,
-- plus the pre-existing RESOLVED value the human-review resolution flow
-- already wrote). Escalation needs a value of its own without further
-- overloading that column, and without letting a resolved case also be
-- escalated (or vice versa) -- human_decision is that single, dedicated,
-- nullable field: NULL until a reviewer acts, then exactly one of
-- RESOLVED / ESCALATED, permanently.

alter table investigations
    add column if not exists human_decision text
        check (human_decision in ('RESOLVED', 'ESCALATED'));
