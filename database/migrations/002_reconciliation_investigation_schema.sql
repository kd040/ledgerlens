-- LedgerLens
-- Migration 002: Reconciliation and investigation layer


-- ============================================================
-- Reconciliation Links
-- ============================================================

create table if not exists reconciliation_links (
    id uuid primary key default gen_random_uuid(),

    source_type text not null,
    source_id uuid,

    target_type text not null,
    target_id uuid,

    relationship_type text not null,
    status text not null default 'PROPOSED',

    confidence numeric(5,2),

    created_at timestamptz not null default now()
);


-- ============================================================
-- Exceptions
-- ============================================================

create table if not exists exceptions (
    id uuid primary key default gen_random_uuid(),

    exception_code text not null,
    category text not null,

    description text,

    financial_impact numeric(18,2),

    status text not null default 'OPEN',

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);


-- ============================================================
-- Investigations
-- ============================================================

create table if not exists investigations (
    id uuid primary key default gen_random_uuid(),

    exception_id uuid not null
        references exceptions(id)
        on delete cascade,

    root_cause text,

    confidence numeric(5,2),

    recommendation text,

    status text not null default 'IN_PROGRESS',

    financial_analysis jsonb,

    started_at timestamptz not null default now(),
    completed_at timestamptz
);


-- ============================================================
-- Investigation Hypotheses
-- ============================================================

create table if not exists investigation_hypotheses (
    id uuid primary key default gen_random_uuid(),

    investigation_id uuid not null
        references investigations(id)
        on delete cascade,

    hypothesis text not null,

    status text not null default 'OPEN',

    confidence numeric(5,2),

    reasoning text,

    created_at timestamptz not null default now()
);


-- ============================================================
-- Investigation Evidence
-- ============================================================

create table if not exists investigation_evidence (
    id uuid primary key default gen_random_uuid(),

    investigation_id uuid not null
        references investigations(id)
        on delete cascade,

    evidence_type text not null,

    record_type text not null,
    record_id uuid,

    description text,

    created_at timestamptz not null default now()
);


-- ============================================================
-- Investigation Tool Calls
-- ============================================================

create table if not exists investigation_tool_calls (
    id uuid primary key default gen_random_uuid(),

    investigation_id uuid not null
        references investigations(id)
        on delete cascade,

    tool_name text not null,

    arguments jsonb,
    result jsonb,

    called_at timestamptz not null default now()
);


-- ============================================================
-- Investigation Contradictions
-- ============================================================

create table if not exists investigation_contradictions (
    id uuid primary key default gen_random_uuid(),

    investigation_id uuid not null
        references investigations(id)
        on delete cascade,

    description text not null,

    evidence_id uuid
        references investigation_evidence(id)
        on delete set null,

    created_at timestamptz not null default now()
);


-- ============================================================
-- Indexes
-- ============================================================

create index if not exists idx_reconciliation_source
    on reconciliation_links(source_type, source_id);

create index if not exists idx_reconciliation_target
    on reconciliation_links(target_type, target_id);

create index if not exists idx_exceptions_category
    on exceptions(category);

create index if not exists idx_exceptions_status
    on exceptions(status);

create index if not exists idx_investigations_exception
    on investigations(exception_id);

create index if not exists idx_investigations_status
    on investigations(status);

create index if not exists idx_hypotheses_investigation
    on investigation_hypotheses(investigation_id);

create index if not exists idx_evidence_investigation
    on investigation_evidence(investigation_id);

create index if not exists idx_tool_calls_investigation
    on investigation_tool_calls(investigation_id);

create index if not exists idx_contradictions_investigation
    on investigation_contradictions(investigation_id);