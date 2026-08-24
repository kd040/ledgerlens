# LedgerLens — Data Model

## 1. Purpose

This document defines the canonical financial data model used by LedgerLens for reconciliation, exception investigation, evidence retrieval, and evaluation.

## 2. Core Entities

LedgerLens initially models:

- Customer
- Order
- Payment
- Settlement
- Refund
- Fee
- Tax
- Adjustment
- Bank Transaction

## 3. Financial Relationship

Customer
    ↓
Order
    ↓
Payment
    ↓
Settlement
    ↓
Bank Transaction

Supporting relationships:

Payment
    └── Refund

Settlement
    ├── Fee
    ├── Tax
    └── Adjustment

## 4. Customer

| Field | Type | Description |
|---|---|---|
| customer_id | UUID | Internal identifier |
| external_customer_id | TEXT | Source-system identifier |
| created_at | TIMESTAMPTZ | Creation timestamp |

## 5. Order

| Field | Type | Description |
|---|---|---|
| order_id | UUID | Internal identifier |
| external_order_id | TEXT | Business/source identifier |
| customer_id | UUID | Customer reference |
| amount | NUMERIC(18,2) | Expected order amount |
| currency | TEXT | Currency |
| status | TEXT | Order status |
| created_at | TIMESTAMPTZ | Creation timestamp |

## 6. Payment

| Field | Type | Description |
|---|---|---|
| payment_id | UUID | Internal identifier |
| external_payment_id | TEXT | Payment identifier |
| order_id | UUID | Related order |
| amount | NUMERIC(18,2) | Captured amount |
| currency | TEXT | Currency |
| status | TEXT | Payment status |
| payment_method | TEXT | Payment method |
| captured_at | TIMESTAMPTZ | Capture timestamp |

## 7. Settlement

| Field | Type | Description |
|---|---|---|
| settlement_id | UUID | Internal identifier |
| external_settlement_id | TEXT | Settlement identifier |
| gross_amount | NUMERIC(18,2) | Gross settlement amount |
| net_amount | NUMERIC(18,2) | Net transferred amount |
| fee_amount | NUMERIC(18,2) | Total fee |
| tax_amount | NUMERIC(18,2) | Total tax |
| adjustment_amount | NUMERIC(18,2) | Total adjustments |
| settled_at | TIMESTAMPTZ | Settlement timestamp |
| status | TEXT | Settlement status |

A settlement may relate to one or more payments.

## 8. Refund

| Field | Type | Description |
|---|---|---|
| refund_id | UUID | Internal identifier |
| external_refund_id | TEXT | Refund identifier |
| payment_id | UUID | Original payment |
| amount | NUMERIC(18,2) | Refund amount |
| status | TEXT | Refund status |
| created_at | TIMESTAMPTZ | Creation timestamp |
| processed_at | TIMESTAMPTZ | Processing timestamp |

## 9. Fee

| Field | Type | Description |
|---|---|---|
| fee_id | UUID | Internal identifier |
| settlement_id | UUID | Settlement reference |
| fee_type | TEXT | Fee classification |
| amount | NUMERIC(18,2) | Fee amount |
| currency | TEXT | Currency |

## 10. Tax

| Field | Type | Description |
|---|---|---|
| tax_id | UUID | Internal identifier |
| settlement_id | UUID | Settlement reference |
| tax_type | TEXT | Tax classification |
| amount | NUMERIC(18,2) | Tax amount |
| currency | TEXT | Currency |

## 11. Adjustment

| Field | Type | Description |
|---|---|---|
| adjustment_id | UUID | Internal identifier |
| settlement_id | UUID | Settlement reference |
| adjustment_type | TEXT | Adjustment classification |
| amount | NUMERIC(18,2) | Adjustment amount |
| reason | TEXT | Adjustment reason |
| created_at | TIMESTAMPTZ | Creation timestamp |

## 12. Bank Transaction

| Field | Type | Description |
|---|---|---|
| bank_transaction_id | UUID | Internal identifier |
| external_bank_transaction_id | TEXT | Bank transaction identifier |
| amount | NUMERIC(18,2) | Transaction amount |
| currency | TEXT | Currency |
| transaction_type | TEXT | CREDIT or DEBIT |
| transaction_date | TIMESTAMPTZ | Bank transaction timestamp |
| description | TEXT | Bank narration/reference |

## 13. Deterministic Financial Rules

The system must calculate financial values deterministically.

For a settlement:

net_amount =
gross_amount
- fee_amount
- tax_amount
+ adjustment_amount

AI-generated values must never replace deterministic financial calculations.

## 14. Reconciliation Relationships

Financial records cannot always be represented through direct foreign-key relationships.

LedgerLens therefore treats reconciliation relationships as explicit evidence.

The reconciliation layer must support:

- One-to-one
- One-to-many
- Many-to-one
- Missing relationships
- Duplicate relationships
- Partial relationships

### Reconciliation Link

A reconciliation link represents an observed or proposed relationship between financial records.

Conceptually:

```text
Payment A ───────┐
Payment B ───────┼──→ Settlement X
Payment C ───────┘
## 15. Design Principle

Financial facts are stored as structured records.

Relationships between records are evidence.

The AI investigator reasons over evidence but does not create financial facts.