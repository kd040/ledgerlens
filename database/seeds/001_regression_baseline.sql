-- LedgerLens
-- Seed 001: the PAY-001..PAY-005 regression baseline.
--
-- WHY THIS FILE EXISTS
--
-- scripts/generate_eval_dataset.py deterministically generates
-- PAY-006..PAY-100 "on top of the existing PAY-001..PAY-005 regression
-- cases" and never touches those five. Migrations 003 and 004 only
-- UPDATE them. Nothing in the repository ever CREATED them -- they were
-- inserted by hand during early development, so a clean database could
-- not reproduce the 100-record benchmark and the benchmark assertions in
-- backend/tests/ failed on any fresh environment (including CI).
--
-- This file closes that gap. Applied after the migrations and before the
-- generator, it makes the full deterministic benchmark reproducible from
-- an empty database:
--
--   migrations 001..008  ->  this seed  ->  generate_eval_dataset.py
--
-- The values are the established benchmark, not new test data. They
-- reproduce exactly the ground truth recorded in data/eval_ground_truth.json:
--
--   PAY-001  RECONCILED
--   PAY-002  EX01 Amount Mismatch    impact    50.00
--   PAY-003  EX02 Missing Record     impact  1500.00
--   PAY-004  EX03 Duplicate Record   impact  3000.00
--   PAY-005  EX01 Amount Mismatch    impact  1235.00
--
-- Settlement amounts are written in their post-migration-004 state, so
-- applying this seed after the migrations is correct and idempotent.
-- order_id is left null, matching what the generator does for
-- PAY-006..PAY-100.
--
-- Every statement is idempotent: re-running changes nothing.


-- ============================================================
-- Payments
-- ============================================================

insert into payments (external_payment_id, amount, currency, status, method, captured_at, created_at)
values
    ('PAY-001', 1000.00, 'INR', 'CAPTURED', 'UPI',        timestamptz '2026-08-24 04:30:00+00', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('PAY-002', 2000.00, 'INR', 'CAPTURED', 'CARD',       timestamptz '2026-08-24 04:35:00+00', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('PAY-003', 1500.00, 'INR', 'CAPTURED', 'UPI',        timestamptz '2026-08-24 04:40:00+00', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('PAY-004', 3000.00, 'INR', 'CAPTURED', 'CARD',       timestamptz '2026-08-24 04:45:00+00', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('PAY-005', 2500.00, 'INR', 'CAPTURED', 'NETBANKING', timestamptz '2026-08-24 04:50:00+00', timestamptz '2026-08-24 23:41:02.032661+00')
on conflict (external_payment_id) do nothing;


-- ============================================================
-- Settlements
--
-- PAY-003 deliberately has no settlement  -> EX02.
-- PAY-004 deliberately has two            -> EX03.
-- SET-002 is 1850.00 against an expected 1900.00 -> EX01 (migration 004).
-- SET-005 is 1250.00 against an expected 2485.00 -> EX01.
-- ============================================================

insert into settlements (external_settlement_id, settlement_amount, currency, status, settlement_date, reference, created_at)
values
    ('SET-001',    970.00, 'INR', 'SETTLED', timestamptz '2026-08-25 03:30:00+00', 'PAY-001', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('SET-002',   1850.00, 'INR', 'SETTLED', timestamptz '2026-08-25 03:30:00+00', 'PAY-002', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('SET-004-A', 3000.00, 'INR', 'SETTLED', timestamptz '2026-08-25 03:30:00+00', 'PAY-004', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('SET-004-B', 3000.00, 'INR', 'SETTLED', timestamptz '2026-08-25 03:30:00+00', 'PAY-004', timestamptz '2026-08-24 23:41:02.032661+00'),
    ('SET-005',   1250.00, 'INR', 'SETTLED', timestamptz '2026-08-25 03:30:00+00', 'PAY-005', timestamptz '2026-08-24 23:41:02.032661+00')
on conflict (external_settlement_id) do nothing;


-- ============================================================
-- Fees / taxes / adjustments
--
-- These tables have no natural unique key, so each insert is guarded by
-- a not-exists check rather than on-conflict. SET-004-B carries no fee
-- rows on purpose -- it is the duplicate settlement.
-- ============================================================

insert into fees (settlement_id, amount, currency, fee_type)
select s.id, v.amount, 'INR', 'PROCESSING_FEE'
from (values
    ('SET-001',   20.00),
    ('SET-002',  100.00),
    ('SET-004-A', 30.00),
    ('SET-005',   15.00)
) as v(external_settlement_id, amount)
join settlements s on s.external_settlement_id = v.external_settlement_id
where not exists (
    select 1 from fees f where f.settlement_id = s.id
);

insert into taxes (settlement_id, amount, currency, tax_type)
select s.id, v.amount, 'INR', 'GST'
from (values
    ('SET-001', 10.00),
    ('SET-002',  0.00)
) as v(external_settlement_id, amount)
join settlements s on s.external_settlement_id = v.external_settlement_id
where not exists (
    select 1 from taxes t where t.settlement_id = s.id
);

insert into adjustments (settlement_id, amount, currency, adjustment_type, reason)
select s.id, 0.00, 'INR', 'NONE', null
from settlements s
where s.external_settlement_id = 'SET-001'
  and not exists (
    select 1 from adjustments a where a.settlement_id = s.id
);


-- ============================================================
-- Bank transactions
--
-- Referenced by settlement id, and used by the investigation tools to
-- confirm which settlements actually reached the bank. BANK-002 shows
-- 1900.00 against a 1850.00 settlement, and PAY-004's duplicate has only
-- one confirming credit -- both are deliberate investigation evidence.
-- ============================================================

insert into bank_transactions (external_transaction_id, transaction_date, amount, currency, transaction_type, reference, description)
values
    ('BANK-001', timestamptz '2026-08-25 03:30:00+00',  970.00, 'INR', 'CREDIT', 'SET-001',   'Settlement credit'),
    ('BANK-002', timestamptz '2026-08-25 03:30:00+00', 1900.00, 'INR', 'CREDIT', 'SET-002',   'Settlement credit'),
    ('BANK-004', timestamptz '2026-08-25 03:30:00+00', 3000.00, 'INR', 'CREDIT', 'SET-004-A', 'Settlement credit'),
    ('BANK-005', timestamptz '2026-08-25 03:30:00+00', 1250.00, 'INR', 'CREDIT', 'SET-005',   'Partial settlement credit')
on conflict (external_transaction_id) do nothing;
