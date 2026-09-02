-- LedgerLens
-- Demo financial dataset
-- Migration-independent seed data

-- ============================================================
-- Customers
-- ============================================================

insert into customers (
    external_customer_id,
    name,
    email
)
values
    ('CUST-001', 'Aarav Sharma', 'aarav@example.com'),
    ('CUST-002', 'Priya Singh', 'priya@example.com'),
    ('CUST-003', 'Rohan Mehta', 'rohan@example.com'),
    ('CUST-004', 'Ananya Gupta', 'ananya@example.com'),
    ('CUST-005', 'Vikram Patel', 'vikram@example.com')
on conflict (external_customer_id) do nothing;


-- ============================================================
-- Orders
-- ============================================================

insert into orders (
    external_order_id,
    customer_id,
    amount,
    currency,
    status
)
select
    'ORD-001',
    id,
    1000.00,
    'INR',
    'PAID'
from customers
where external_customer_id = 'CUST-001'
on conflict (external_order_id) do nothing;


insert into orders (
    external_order_id,
    customer_id,
    amount,
    currency,
    status
)
select
    'ORD-002',
    id,
    2000.00,
    'INR',
    'PAID'
from customers
where external_customer_id = 'CUST-002'
on conflict (external_order_id) do nothing;


insert into orders (
    external_order_id,
    customer_id,
    amount,
    currency,
    status
)
select
    'ORD-003',
    id,
    1500.00,
    'INR',
    'PAID'
from customers
where external_customer_id = 'CUST-003'
on conflict (external_order_id) do nothing;


insert into orders (
    external_order_id,
    customer_id,
    amount,
    currency,
    status
)
select
    'ORD-004',
    id,
    3000.00,
    'INR',
    'PAID'
from customers
where external_customer_id = 'CUST-004'
on conflict (external_order_id) do nothing;


insert into orders (
    external_order_id,
    customer_id,
    amount,
    currency,
    status
)
select
    'ORD-005',
    id,
    2500.00,
    'INR',
    'PAID'
from customers
where external_customer_id = 'CUST-005'
on conflict (external_order_id) do nothing;


-- ============================================================
-- Payments
-- ============================================================

insert into payments (
    external_payment_id,
    order_id,
    amount,
    currency,
    status,
    method,
    captured_at
)
select
    'PAY-001',
    id,
    1000.00,
    'INR',
    'CAPTURED',
    'UPI',
    '2026-08-24 10:00:00+05:30'
from orders
where external_order_id = 'ORD-001'
on conflict (external_payment_id) do nothing;


insert into payments (
    external_payment_id,
    order_id,
    amount,
    currency,
    status,
    method,
    captured_at
)
select
    'PAY-002',
    id,
    2000.00,
    'INR',
    'CAPTURED',
    'CARD',
    '2026-08-24 10:05:00+05:30'
from orders
where external_order_id = 'ORD-002'
on conflict (external_payment_id) do nothing;


insert into payments (
    external_payment_id,
    order_id,
    amount,
    currency,
    status,
    method,
    captured_at
)
select
    'PAY-003',
    id,
    1500.00,
    'INR',
    'CAPTURED',
    'UPI',
    '2026-08-24 10:10:00+05:30'
from orders
where external_order_id = 'ORD-003'
on conflict (external_payment_id) do nothing;


insert into payments (
    external_payment_id,
    order_id,
    amount,
    currency,
    status,
    method,
    captured_at
)
select
    'PAY-004',
    id,
    3000.00,
    'INR',
    'CAPTURED',
    'CARD',
    '2026-08-24 10:15:00+05:30'
from orders
where external_order_id = 'ORD-004'
on conflict (external_payment_id) do nothing;


insert into payments (
    external_payment_id,
    order_id,
    amount,
    currency,
    status,
    method,
    captured_at
)
select
    'PAY-005',
    id,
    2500.00,
    'INR',
    'CAPTURED',
    'NETBANKING',
    '2026-08-24 10:20:00+05:30'
from orders
where external_order_id = 'ORD-005'
on conflict (external_payment_id) do nothing;


-- ============================================================
-- Settlements
-- ============================================================

-- PAY-001: correct settlement
insert into settlements (
    external_settlement_id,
    settlement_amount,
    currency,
    status,
    settlement_date,
    reference
)
values (
    'SET-001',
    970.00,
    'INR',
    'SETTLED',
    '2026-08-25 09:00:00+05:30',
    'PAY-001'
)
on conflict (external_settlement_id) do nothing;


-- PAY-002: amount mismatch
insert into settlements (
    external_settlement_id,
    settlement_amount,
    currency,
    status,
    settlement_date,
    reference
)
values (
    'SET-002',
    1900.00,
    'INR',
    'SETTLED',
    '2026-08-25 09:00:00+05:30',
    'PAY-002'
)
on conflict (external_settlement_id) do nothing;


-- PAY-003: intentionally NO settlement
-- This creates a missing-record scenario.


-- PAY-004: duplicate settlements
insert into settlements (
    external_settlement_id,
    settlement_amount,
    currency,
    status,
    settlement_date,
    reference
)
values (
    'SET-004-A',
    3000.00,
    'INR',
    'SETTLED',
    '2026-08-25 09:00:00+05:30',
    'PAY-004'
)
on conflict (external_settlement_id) do nothing;


insert into settlements (
    external_settlement_id,
    settlement_amount,
    currency,
    status,
    settlement_date,
    reference
)
values (
    'SET-004-B',
    3000.00,
    'INR',
    'SETTLED',
    '2026-08-25 09:00:00+05:30',
    'PAY-004'
)
on conflict (external_settlement_id) do nothing;


-- PAY-005: partial settlement
insert into settlements (
    external_settlement_id,
    settlement_amount,
    currency,
    status,
    settlement_date,
    reference
)
values (
    'SET-005',
    1250.00,
    'INR',
    'SETTLED',
    '2026-08-25 09:00:00+05:30',
    'PAY-005'
)
on conflict (external_settlement_id) do nothing;


-- ============================================================
-- Fees
-- ============================================================

insert into fees (
    settlement_id,
    amount,
    currency,
    fee_type
)
select
    id,
    20.00,
    'INR',
    'PROCESSING_FEE'
from settlements
where external_settlement_id = 'SET-001'
  and not exists (
      select 1
      from fees f
      where f.settlement_id = settlements.id
        and f.fee_type = 'PROCESSING_FEE'
  );

insert into fees (
    settlement_id,
    amount,
    currency,
    fee_type
)
select
    id,
    100.00,
    'INR',
    'PROCESSING_FEE'
from settlements
where external_settlement_id = 'SET-002'
  and not exists (
      select 1
      from fees f
      where f.settlement_id = settlements.id
        and f.fee_type = 'PROCESSING_FEE'
  );


insert into fees (
    settlement_id,
    amount,
    currency,
    fee_type
)
select
    id,
    30.00,
    'INR',
    'PROCESSING_FEE'
from settlements
where external_settlement_id = 'SET-004-A'
  and not exists (
      select 1
      from fees f
      where f.settlement_id = settlements.id
        and f.fee_type = 'PROCESSING_FEE'
  ) ;


insert into fees (
    settlement_id,
    amount,
    currency,
    fee_type
)
select
    id,
    15.00,
    'INR',
    'PROCESSING_FEE'
from settlements
where external_settlement_id = 'SET-005'
  and not exists (
      select 1
      from fees f
      where f.settlement_id = settlements.id
        and f.fee_type = 'PROCESSING_FEE'
  );


-- ============================================================
-- Taxes
-- ============================================================

insert into taxes (
    settlement_id,
    amount,
    currency,
    tax_type
)
select
    id,
    10.00,
    'INR',
    'GST'
from settlements
where external_settlement_id = 'SET-001'
  and not exists (
      select 1
      from taxes t
      where t.settlement_id = settlements.id
        and t.tax_type = 'GST'
  );


insert into taxes (
    settlement_id,
    amount,
    currency,
    tax_type
)
select
    id,
    0.00,
    'INR',
    'GST'
from settlements
where external_settlement_id = 'SET-002'
  and not exists (
      select 1
      from taxes t
      where t.settlement_id = settlements.id
        and t.tax_type = 'GST'
  );


-- ============================================================
-- Adjustments
-- ============================================================

insert into adjustments (
    settlement_id,
    amount,
    currency,
    adjustment_type,
    reason
)
select
    id,
    0.00,
    'INR',
    'NONE',
    'No adjustment'
from settlements
where external_settlement_id = 'SET-001'
  and not exists (
      select 1
      from adjustments a
      where a.settlement_id = settlements.id
        and a.adjustment_type = 'NONE'
  );


-- ============================================================
-- Bank Transactions
-- ============================================================

insert into bank_transactions (
    external_transaction_id,
    transaction_date,
    amount,
    currency,
    transaction_type,
    reference,
    description
)
values
    (
        'BANK-001',
        '2026-08-25 09:00:00+05:30',
        970.00,
        'INR',
        'CREDIT',
        'SET-001',
        'Settlement credit'
    ),
    (
        'BANK-002',
        '2026-08-25 09:00:00+05:30',
        1900.00,
        'INR',
        'CREDIT',
        'SET-002',
        'Settlement credit'
    ),
    (
        'BANK-004',
        '2026-08-25 09:00:00+05:30',
        3000.00,
        'INR',
        'CREDIT',
        'SET-004-A',
        'Settlement credit'
    ),
    (
        'BANK-005',
        '2026-08-25 09:00:00+05:30',
        1250.00,
        'INR',
        'CREDIT',
        'SET-005',
        'Partial settlement credit'
    )
on conflict (external_transaction_id) do nothing;