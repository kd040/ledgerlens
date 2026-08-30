# LedgerLens

## AI Finance Controller

LedgerLens is an AI-powered Finance Controller designed to reconcile payment and settlement records, detect financial exceptions, investigate their root causes using evidence, and support human reviewers in resolving or escalating those exceptions.

Built for the **Razorpay AI Buildathon 2026 — Track 04: AI Finance Controller**.

---

## Core Workflow

```text
Financial Data
      ↓
Normalization
      ↓
Reconciliation
      ↓
Exception Detection
      ↓
Investigation
      ↓
AI Root-Cause Analysis
      ↓
Human Review
      ↓
Resolve / Escalate
      ↓
Audit Trail
LedgerLens combines deterministic financial logic with AI-assisted investigation.

Financial calculations and reconciliation remain deterministic, while the AI layer investigates detected exceptions using controlled tools and persisted evidence.

Key Capabilities
Reconciliation
Payment and settlement reconciliation
Fee and tax reconciliation
Deterministic financial calculations
Exception detection
Idempotent reconciliation
Financial lifecycle tracking
Deterministic evaluation dataset
Exception Management
Exception listing and filtering
Exception details
Duplicate settlement detection
Investigation creation
Investigation status tracking
Investigation Engine

LedgerLens supports investigation workflows for:

EX01 — Amount mismatch
EX02 — Missing settlement
EX03 — Duplicate settlement

Investigations persist:

Evidence
Hypotheses
Contradictions
Tool calls
Conclusions
Audit information
AI Investigator

LedgerLens includes a tool-driven AI investigation engine with:

Google Gemini provider
Anthropic provider abstraction
Structured investigation schemas
Controlled tool calling
Tool-call limits
Financial-value validation
Malformed-output rejection
Unknown-tool rejection
No-partial-persistence behavior

The AI recommendation is kept separate from the final human decision.

AI recommendations do not automatically resolve or escalate financial exceptions.

Human Review

Reviewer users can:

Review investigation evidence
Inspect financial analysis
Review AI recommendations
Mark investigations as resolved
Escalate investigations

Human decisions are explicitly recorded separately from AI recommendations.

Roles
Capability	Analyst	Reviewer
View financial data	✓	✓
View exceptions	✓	✓
View investigations	✓	✓
Run investigations	✓	✓
Run AI investigations	✓	✓
Resolve investigations	—	✓
Escalate investigations	—	✓

New users can register through the application and are assigned the Analyst role by default.

Reviewer-only actions are enforced by the backend and are not dependent only on frontend visibility.

Data Sources
Deterministic Demo Dataset

LedgerLens includes a deterministic evaluation dataset containing:

100 payments
30 exceptions

EX01: 15
EX02: 8
EX03: 7

The dataset is reproducible and reconciliation is idempotent.

Razorpay Test Mode

LedgerLens can ingest and normalize payment data from the Razorpay Test Mode API.

Razorpay credentials remain server-side and are never exposed to the frontend.

Architecture
┌─────────────────────────────────┐
│     React / TypeScript UI       │
└───────────────┬─────────────────┘
                │
                │ HTTP
                ▼
┌─────────────────────────────────┐
│         FastAPI Backend         │
├─────────────────────────────────┤
│ Authentication & Authorization  │
│ Reconciliation                  │
│ Exception Detection             │
│ Investigation Engine             │
│ Human Review                    │
│ AI Investigator                 │
└───────────────┬─────────────────┘
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
┌───────────────┐  ┌──────────────────┐
│ PostgreSQL /  │  │   AI Providers   │
│   Supabase    │  │ Gemini / Anthropic│
└───────────────┘  └──────────────────┘
AI Investigation Architecture

The AI Investigator does not directly manipulate financial records.

Instead, it operates through a controlled investigation loop:

Exception
    ↓
Investigation Context
    ↓
AI Investigator
    ↓
Controlled Tools
    ↓
Financial Evidence
    ↓
Hypotheses / Contradictions
    ↓
Financial Validation
    ↓
AI Recommendation
    ↓
Human Review

The system validates financial values produced by the AI against persisted financial data before accepting the investigation result.

AI failures are handled safely without leaving partially persisted investigation results.

Tech Stack
Frontend
React
TypeScript
Vite
Tailwind CSS
React Router
TanStack Query
Backend
Python
FastAPI
Pydantic
psycopg
Database
PostgreSQL
Supabase
AI
Google Gemini
Anthropic provider abstraction
Structured tool calling
Integrations
Razorpay Test Mode API
Project Structure
.
├── backend/
│   ├── app/
│   │   ├── ai/
│   │   │   ├── providers/
│   │   │   ├── config.py
│   │   │   ├── investigator.py
│   │   │   ├── schemas.py
│   │   │   └── tools.py
│   │   │
│   │   ├── auth/
│   │   ├── datasources/
│   │   ├── exceptions/
│   │   ├── investigation/
│   │   └── reconciliation/
│   │
│   ├── scripts/
│   ├── tests/
│   └── requirements.txt
│
├── database/
│   └── migrations/
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── domain/
│   │   ├── lib/
│   │   └── pages/
│   └── package.json
│
└── README.md
Local Development
Backend

From the project root:

cd backend

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000

The backend runs on:

http://localhost:8000
Frontend

Open another terminal:

cd frontend

npm install
npm run dev

The frontend runs on:

http://localhost:5173
Environment Variables

Create the backend environment from the example:

cp .env.example .env

Configure the required database, Razorpay Test Mode, and AI provider credentials.

Frontend configuration is provided in:

frontend/.env.example

Example frontend configuration:

VITE_API_BASE_URL=http://localhost:8000

Never commit .env files or API secrets.

Demo Accounts

The application includes seeded demo accounts for evaluation:

Analyst
analyst@ledgerlens.dev

Reviewer
reviewer@ledgerlens.dev

Demo passwords are configured through the backend environment and demo-user seeding configuration rather than stored in the repository.

Authentication

LedgerLens supports:

User registration
Login
Logout
Session authentication
Role-based authorization
Analyst and Reviewer roles

New registrations are automatically assigned the Analyst role.

Reviewer authorization is enforced at the backend API level.

Investigation Lifecycle

An investigation follows an explicit lifecycle:

OPEN
  ↓
IN_PROGRESS
  ↓
HUMAN_REVIEW
  ↓
┌─────────────┐
│             │
▼             ▼
RESOLVED    ESCALATED

The system keeps the AI recommendation and human decision separate.

For example:

AI Recommendation: HUMAN_REVIEW

Human Decision: RESOLVED

This distinction preserves an auditable record of what the AI recommended and what the authorized human reviewer actually decided.

Security

LedgerLens includes:

PBKDF2-HMAC-SHA256 password hashing
Per-user password salts
Session-based authentication
Role-based authorization
Reviewer-only mutation endpoints
Server-side Razorpay credentials
Server-side AI credentials
Environment-variable based secrets
.env files excluded from Git
Backend authorization independent of frontend visibility
AI financial-value validation
Malformed AI output rejection
Unknown-tool rejection
Safe AI failure handling without partial persistence
Evaluation Dataset

The deterministic evaluation dataset exercises the complete financial investigation workflow.

Expected baseline:

100 payments
30 exceptions

EX01: 15
EX02: 8
EX03: 7

Reconciliation is idempotent.

Repeated reconciliation runs do not create duplicate exceptions.

Testing
Backend Tests
cd backend
source .venv/bin/activate
pytest -q

Current verification:

105 tests passed
TypeScript
cd frontend
npx tsc -b
Lint
npx oxlint .
Production Build
npm run build
Current Verification
Backend tests:     105/105 passed
TypeScript:        clean
Oxlint:            0 warnings, 0 errors
Production build:  successful
Responsive Interface

The application has been verified across desktop, tablet, and mobile viewport sizes.

Verified viewport widths include:

1440px
1024px
820px
390px

The core application screens have no horizontal page overflow at these viewport sizes.

Razorpay Integration

LedgerLens supports Razorpay Test Mode ingestion.

The integration:

Connects to Razorpay Test Mode.
Retrieves payment data.
Normalizes external records.
Persists the normalized financial data.
Runs reconciliation.
Generates exceptions when financial discrepancies are detected.
Makes those exceptions available for investigation.

Razorpay API secrets are kept on the backend.

Why LedgerLens

Financial reconciliation is not only about detecting that two numbers are different.

A useful finance-control system should answer:

What went wrong?
Which records provide evidence?
What is the likely root cause?
What contradicts that hypothesis?
What does the AI recommend?
What did the human reviewer ultimately decide?
Can the entire decision be audited later?

LedgerLens is designed around that complete workflow rather than treating AI as a simple chatbot layer.

Buildathon

Razorpay AI Buildathon 2026

Track 04 — AI Finance Controller

LedgerLens combines deterministic financial controls, evidence-driven AI investigation, and explicit human decision-making into a single auditable workflow.

Project Status

Buildathon-ready release candidate

The core LedgerLens workflow has been implemented and verified end-to-end:

Authentication
User signup
Role-based access
Reconciliation
Exception detection
Duplicate settlement detection
Investigation workflows
Evidence and hypotheses
Contradiction tracking
AI investigation
Human review
Resolution and escalation
Razorpay Test Mode integration
Responsive frontend
Automated backend tests
Production frontend build