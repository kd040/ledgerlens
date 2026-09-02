# Development Notes

How LedgerLens was actually built. This is process context for anyone reading
the commit history — the product documentation is in [README.md](README.md) and
the design documents are in [`docs/`](docs/).

## Solo project

LedgerLens was built solo for the Razorpay AI Buildathon 2026 (Track 04 — AI
Finance Controller). Every commit in this repository is by one author. There was
no second reviewer, which is worth knowing when reading the history: code review
happened against the test suite and the deterministic benchmark rather than
against another person.

## How the work was sequenced

Development ran in phases over roughly ten days. The phases below are derived
from `git log`, not reconstructed from memory.

**1. Specification before code (24–25 Aug).** The first substantive commits are
documentation, not application code: the product specification, the financial
data model and evaluation framework, and the system architecture including the
AI investigator design — about 1,350 lines across `docs/01`–`docs/06` before the
first line of FastAPI. The exception taxonomy (EX01/EX02/EX03) and the shape of
the evaluation benchmark were fixed at this point and did not materially change
afterwards.

**2. Deterministic core (25–26 Aug).** Backend scaffolding, database connection,
the financial schema, then the deterministic reconciliation engine
(`cd49837`), the investigation API with the three exception runners (`07e1697`,
27 files), and the generator for the 100-record evaluation dataset (`d80ec67`).
The ordering here was deliberate: the arithmetic and its ground truth existed
before anything AI-related did.

**3. Application surface (30 Aug).** The largest single day — nine commits
covering authentication and signup, the Razorpay Test Mode datasource, the
investigation resolution workflow, the exceptions and duplicate-settlement APIs,
the AI investigation engine (`726e9a4`, 2,528 insertions), and the entire React
frontend (`037cb2b`, 60 files, 8,311 insertions).

**4. Production hardening (31 Aug).** The reporting dashboard, then a run of
fixes driven by deploying the application rather than by planning: Razorpay sync
and reconciliation hardening (`b7997e4`, 25 files), a one-line dependency
conflict fix for the Gemini SDK (`7209a9a`), the cross-site session cookie
(`2a9bd7e`), the Vercel `/api` proxy (`e284576`), and the reconciliation query
batching that took the endpoint from 531 database round trips to 7 (`2a0497a`).

**5. Resilience and release preparation (1 Sep).** AI provider failover with
Groq as a bounded fallback behind Gemini (`e65767c`), then the documentation
pass that prepared the repository to be public.

**6. Continuous integration (1–2 Sep).** Added last, after the application was
feature-complete. See below.

## Commit granularity

Work is batched into larger commits rather than one commit per change. The
frontend arrived in a single 60-file commit; the AI investigation engine, the
investigation API, and the Razorpay hardening pass are each one commit of
2,000–4,000 lines. The commit history is therefore a record of completed
milestones, not an incremental log of individual decisions.

This was a deliberate trade for solo work under a deadline, and it has a real
cost worth naming: individual commits are not independently reviewable, and
`git bisect` over this history is coarse. The finer-grained history is the two
CI pull requests, which were iterated in the open against real runs.

## What CI surfaced

CI was added after the application already worked in production, primarily so
that the test counts claimed in the README would be verifiable rather than
asserted. It immediately failed, for a reason worth recording.

The backend suite is not mocked at the database boundary — every test opens a
real PostgreSQL connection. The first CI attempt pointed it at the shared hosted
database ([PR #1](https://github.com/kd040/ledgerlens/pull/1), closed) and never
passed: six consecutive runs, **14 of 203 tests failing**, roughly fifteen
minutes each.

Two independent causes, both fixed in
[PR #2](https://github.com/kd040/ledgerlens/pull/2):

**The 100-record benchmark could not be reproduced on a clean database.** The
generator `scripts/generate_eval_dataset.py` produces `PAY-006`..`PAY-100` *on
top of* five hand-written regression cases, `PAY-001`..`PAY-005`. Those five
records do exist in the repository, in the demo seed committed 25 Aug in
`cd49837` (since renumbered to
`database/seeds/002_demo_financial_data.sql`) — but that file was never
referenced by any script, workflow, or setup instruction. Nothing applied it. A fresh clone ran the migrations, applied no
seed, and every benchmark assertion saw 0 payments instead of 100.

The ordering that file depends on was also never written down. It inserts
`SET-002` at 1900.00, and migration `004_create_amount_mismatch.sql` then
rewrites it to 1850.00 to create the EX01 amount mismatch — so the seed has to
be applied *between* migrations 003 and 004 to produce the documented ground
truth. Applied after all migrations, as anyone following the README would have
done, `PAY-002` reconciles cleanly and the benchmark quietly comes out at 14
EX01 instead of 15.

The fix was `database/seeds/001_regression_baseline.sql`, which writes the same
five records in their post-migration-004 state. Because the values are already
final, it is order-independent: migrations, then seed, then generator. It is
verified against `data/eval_ground_truth.json`.

**Concurrent runs corrupted each other.** The concurrency group keyed off
`pull_request.head.ref` for pull requests and `github.ref` for pushes — two
different strings for the same branch — so the push run and the PR run executed
simultaneously against one shared database. One run's schema reset landed in the
middle of the other's test session, producing unique-constraint failures on
`exceptions` and `users` that looked like test flakiness.

Both were resolved by giving each run its own ephemeral `postgres:16` service
container. That also removed the need for any repository secret, and removed a
`drop schema public cascade` that had been running against whatever database the
CI connection string pointed at.

Result: **203 passed in 10.08s**, with the whole job taking 1m19s, down from a
14m50s failing run. The suite was network-bound against a hosted database, not
slow on its own.

### Seed file collision — resolved

Two seed files were both numbered `001`. The original demo dataset has been
renumbered to `database/seeds/002_demo_financial_data.sql`, and the
relationship between the two is documented in
[`database/seeds/README.md`](database/seeds/README.md). The numbering now
reflects application order rather than the order the files were written.

An earlier version of this note said the two files were "not contradictory."
That was wrong. They overlap on every record they share — `PAY-001`..`PAY-005`,
the five settlements, the fees, taxes, adjustment and bank transactions — and
they **disagree on one value**: the demo seed writes `SET-002` at 1900.00 and
relies on migration 004 to rewrite it to 1850.00, while the regression baseline
writes 1850.00 directly. Applying the demo seed after all migrations therefore
produces 14 EX01 exceptions instead of 15, silently.

The duplication itself is still present. Consolidating it means rewriting seed
SQL that no local environment in this project can execute — there is no
container runtime or local PostgreSQL available here — and an untested rewrite
of the fixture the benchmark depends on is a worse trade than documented
duplication. The ordering hazard is recorded in the seeds README instead.

## Testing approach and its limits

The backend suite has no `conftest.py` and no fixtures. Tests insert the rows
they need and delete them at the end, rather than running inside a transaction
that rolls back. This works when the database starts empty, which is why CI
provisions a fresh container per run.

It does not work well for repeated local runs: a test that fails partway leaves
its rows behind, and the next run fails on a unique constraint for a row the
previous run created. Those follow-up failures are an artefact of the harness
rather than a defect in the code under test. The practical workaround, and the
local setup that matches CI, is documented under
[Running tests locally](README.md#running-tests-locally).

Converting the suite to transactional fixtures is the obvious improvement and
has not been done.

## What is verified, and what is not

Verified by automated tests on every run: reconciliation determinism and its
query-count regression, the exception taxonomy against the 100-record benchmark,
investigation and resolution workflows, role enforcement, session-cookie policy,
the Razorpay datasource, reporting aggregates, and the AI provider failover chain
with mocked transports.

Not covered by automated tests: no end-to-end browser tests — the frontend
suite covers component and utility logic only; responsive behaviour was checked
by hand at four viewport widths; and no test makes a live AI provider call, so
the Gemini and Groq integrations are verified against mocked transports plus
manual live runs recorded in the pull request history.
