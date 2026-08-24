# LedgerLens — System Architecture

## 1. Architecture Objective

LedgerLens separates deterministic financial processing from AI investigation.

The architecture follows the principle:

> Deterministic systems establish financial facts. AI investigates relationships and evidence.

The system consists of:

- Next.js dashboard
- FastAPI backend
- Ingestion service
- Deterministic reconciliation engine
- AI investigation agent
- Typed investigation tools
- Supabase PostgreSQL
- Evaluation system

---

## 2. High-Level Architecture

```text
                         Next.js Dashboard
                                |
                           HTTP / JSON
                                |
                                v
                         FastAPI API Layer
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
        Ingestion          Reconciliation     Investigation
         Service               Engine             Agent
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                       Supabase PostgreSQL