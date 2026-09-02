# Seed data

Two seed files, applied in numeric order. The numbering reflects **application
order**, not the order they were written — `002_demo_financial_data.sql` is
older than `001_regression_baseline.sql`.

| File | Applied by | Required for |
|---|---|---|
| `001_regression_baseline.sql` | CI, and the local setup in the README | The 100-record evaluation benchmark |
| `002_demo_financial_data.sql` | Nothing automated | Customer/order records behind the deployed demo |

## `001_regression_baseline.sql`

The `PAY-001`..`PAY-005` regression cases that
`scripts/generate_eval_dataset.py` builds `PAY-006`..`PAY-100` on top of.
Without it the benchmark assertions see 0 payments instead of 100.

It writes settlement amounts in their **post-migration state**, so it is
order-independent: apply it any time after the migrations.

```bash
for migration in database/migrations/*.sql; do
  python scripts/run_migration.py "$migration"
done
python scripts/run_migration.py database/seeds/001_regression_baseline.sql
python scripts/generate_eval_dataset.py
```

## `002_demo_financial_data.sql`

The original dataset, added 25 Aug in `cd49837` alongside the reconciliation
engine. It is the source of the `CUST-001`..`CUST-005` customers and
`ORD-001`..`ORD-005` orders in the deployed demo database.

No automated process applies it. Nothing in `backend/app` or `backend/tests`
reads the `customers` or `orders` tables, so it is not needed for the test
suite or for the benchmark.

## How they overlap

These files are not independent fixtures. They are two snapshots of the same
five records at different points in the migration timeline, so most of their
content is duplicated:

- Both insert `PAY-001`..`PAY-005`
- Both insert `SET-001`, `SET-002`, `SET-004-A`, `SET-004-B`, `SET-005`
- Both insert the same fees, taxes, adjustment, and `BANK-*` transactions

Only `002` adds customers, orders, and the `payments.order_id` links.

**They disagree on one value.** `002` writes `SET-002` at `1900.00` — the
correct settlement — and migration `004_create_amount_mismatch.sql` then
rewrites it to `1850.00` to create the EX01 amount mismatch. `001` writes
`1850.00` directly.

That difference drives the ordering rules below.

## Ordering rules

**`002` must be applied between migrations 003 and 004.** It writes to
`settlements.reference`, a column migration 003 adds, so 003 must run first;
and migration 004 must run after it to create the mismatch.

Applying `002` after *all* migrations leaves `SET-002` at `1900.00`. `PAY-002`
then reconciles cleanly and the benchmark quietly comes out at **14 EX01
instead of 15** — a wrong result with no error.

**Applying `001` and then `002` is safe but partial.** Every insert in both
files is guarded by `on conflict ... do nothing` or `where not exists`, so
whichever runs first wins. After `001`, the overlapping rows in `002` are
no-ops; you get the customers and orders, but the payments keep
`order_id = null`, because `002` sets the link as part of a payment insert that
now conflicts. Nothing reads `order_id`, so this does not affect the test suite
or the benchmark.

## Known duplication

The overlap above is redundancy worth removing: `001` could be reduced to the
values that differ, or `002` reduced to the customers and orders it uniquely
provides. That consolidation is deliberately not done here — it would mean
rewriting seed SQL that no local environment in this project can currently
execute (there is no container runtime or local PostgreSQL available), and an
untested rewrite of the fixture the benchmark depends on is a worse trade than
documented duplication.
