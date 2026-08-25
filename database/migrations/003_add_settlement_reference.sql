-- LedgerLens
-- Migration 003: Add settlement reference for deterministic matching

alter table settlements
add column if not exists reference text;

create index if not exists idx_settlements_reference
    on settlements(reference);

update settlements
set reference = 'PAY-001'
where external_settlement_id = 'SET-001'
  and reference is null;

update settlements
set reference = 'PAY-002'
where external_settlement_id = 'SET-002'
  and reference is null;

update settlements
set reference = 'PAY-004'
where external_settlement_id = 'SET-004-A'
  and reference is null;

update settlements
set reference = 'PAY-004'
where external_settlement_id = 'SET-004-B'
  and reference is null;

update settlements
set reference = 'PAY-005'
where external_settlement_id = 'SET-005'
  and reference is null;