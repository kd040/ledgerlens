-- LedgerLens
-- Migration 001: Core financial source entities

create extension if not exists "pgcrypto";


-- ============================================================
-- Customers
-- ============================================================

create table if not exists customers (
    id uuid primary key default gen_random_uuid(),
    external_customer_id text not null unique,
    name text,
    email text,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Orders
-- ============================================================

create table if not exists orders (
    id uuid primary key default gen_random_uuid(),
    external_order_id text not null unique,
    customer_id uuid references customers(id),
    amount numeric(18,2) not null,
    currency text not null default 'INR',
    status text not null,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Payments
-- ============================================================

create table if not exists payments (
    id uuid primary key default gen_random_uuid(),
    external_payment_id text not null unique,
    order_id uuid references orders(id),
    amount numeric(18,2) not null,
    currency text not null default 'INR',
    status text not null,
    method text,
    captured_at timestamptz,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Settlements
-- ============================================================

create table if not exists settlements (
    id uuid primary key default gen_random_uuid(),
    external_settlement_id text not null unique,
    settlement_amount numeric(18,2) not null,
    currency text not null default 'INR',
    status text not null,
    settlement_date timestamptz,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Refunds
-- ============================================================

create table if not exists refunds (
    id uuid primary key default gen_random_uuid(),
    external_refund_id text not null unique,
    payment_id uuid references payments(id),
    amount numeric(18,2) not null,
    currency text not null default 'INR',
    status text not null,
    refunded_at timestamptz,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Fees
-- ============================================================

create table if not exists fees (
    id uuid primary key default gen_random_uuid(),
    settlement_id uuid references settlements(id),
    amount numeric(18,2) not null,
    currency text not null default 'INR',
    fee_type text not null,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Taxes
-- ============================================================

create table if not exists taxes (
    id uuid primary key default gen_random_uuid(),
    settlement_id uuid references settlements(id),
    amount numeric(18,2) not null,
    currency text not null default 'INR',
    tax_type text not null,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Adjustments
-- ============================================================

create table if not exists adjustments (
    id uuid primary key default gen_random_uuid(),
    settlement_id uuid references settlements(id),
    amount numeric(18,2) not null,
    currency text not null default 'INR',
    adjustment_type text not null,
    reason text,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Bank Transactions
-- ============================================================

create table if not exists bank_transactions (
    id uuid primary key default gen_random_uuid(),
    external_transaction_id text not null unique,
    transaction_date timestamptz not null,
    amount numeric(18,2) not null,
    currency text not null default 'INR',
    transaction_type text not null,
    reference text,
    description text,
    created_at timestamptz not null default now()
);


-- ============================================================
-- Indexes
-- ============================================================

create index if not exists idx_orders_customer_id
    on orders(customer_id);

create index if not exists idx_payments_order_id
    on payments(order_id);

create index if not exists idx_refunds_payment_id
    on refunds(payment_id);

create index if not exists idx_fees_settlement_id
    on fees(settlement_id);

create index if not exists idx_taxes_settlement_id
    on taxes(settlement_id);

create index if not exists idx_adjustments_settlement_id
    on adjustments(settlement_id);

create index if not exists idx_bank_transactions_date
    on bank_transactions(transaction_date);