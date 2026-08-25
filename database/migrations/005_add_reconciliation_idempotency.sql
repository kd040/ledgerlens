-- LedgerLens
-- Migration 005: Add reconciliation idempotency constraints

create unique index if not exists uq_reconciliation_links_unique_relationship
    on reconciliation_links (
        source_type,
        source_id,
        target_type,
        target_id,
        relationship_type
    );

create unique index if not exists uq_exceptions_unique_case
    on exceptions (
        exception_code,
        description
    );