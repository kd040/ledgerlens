-- LedgerLens
-- Migration 008: AI Investigator root-cause assessment
--
-- AI-only, additive column. investigations.root_cause stays the short
-- deterministic-or-AI summary sentence it already is; this column holds
-- the AI Investigator's structured known/likely/not-proven breakdown
-- (see backend/app/ai/investigator.py). Nullable and never required --
-- the deterministic runner never populates it, and every existing
-- investigation keeps working with it NULL.

alter table investigations
    add column if not exists root_cause_assessment jsonb;
