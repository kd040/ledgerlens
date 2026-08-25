-- LedgerLens
-- Migration 004: Create deterministic amount mismatch scenario

update settlements
set settlement_amount = 1850.00
where external_settlement_id = 'SET-002'
  and reference = 'PAY-002';