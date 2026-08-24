# LedgerLens — Evaluation Plan

## 1. Evaluation Objective

The evaluation system measures whether LedgerLens can correctly reconcile financial records, detect exceptions, investigate their root causes, retrieve supporting evidence, and make safe resolution or escalation decisions.

Evaluation must use hidden ground truth that is unavailable to the AI investigator.

---

## 2. Benchmark Size

The initial benchmark contains 200 cases.

| Category | Cases |
|---|---:|
| Normal / correctly reconciled | 60 |
| Amount mismatch | 20 |
| Missing record | 20 |
| Duplicate record | 15 |
| Timing mismatch | 15 |
| Partial settlement | 20 |
| Refund mismatch | 15 |
| Fee/tax discrepancy | 15 |
| Ambiguous / insufficient evidence | 20 |
| **Total** | **200** |

---

## 3. Difficulty Distribution

Cases will span four difficulty levels.

### Level 1 — Deterministic

The root cause can be established from a small number of records using deterministic calculations.

### Level 2 — Multi-record

The investigator must retrieve and correlate multiple related records.

### Level 3 — Multi-hypothesis

Multiple plausible explanations exist and the investigator must gather evidence to eliminate unsupported hypotheses.

### Level 4 — Ambiguous

Available evidence is insufficient or contradictory.

The correct outcome is escalation rather than a forced conclusion.

---

## 4. Ground Truth

Every benchmark case contains hidden ground truth.

Ground truth includes:

- Case ID
- Exception category
- Root cause
- Financial impact
- Relevant record IDs
- Supporting evidence IDs
- Alternative hypotheses
- Correct resolution state
- Expected explanation

Ground truth must not be exposed to the AI investigator.

---

## 5. Evaluation Metrics

### Reconciliation

Measure:

- Precision
- Recall
- F1 score
- False match rate

### Exception Detection

Measure:

- Exception detection precision
- Exception detection recall
- Exception classification accuracy

### Root Cause

Measure:

- Root-cause accuracy
- Per-category precision
- Per-category recall

### Evidence

Measure:

- Evidence retrieval precision
- Evidence retrieval recall
- Evidence sufficiency
- Unsupported evidence rate

### Investigation

Measure:

- Correct hypothesis selection
- Alternative hypothesis rejection
- Unsupported conclusion rate
- Contradictory evidence handling

### Resolution

Measure:

- Automatic-resolution precision
- False-resolution rate
- Human-review rate
- Escalation accuracy

### Safety

Measure:

- Hallucinated evidence rate
- False-resolution rate
- Incorrect confidence rate
- Cases incorrectly resolved despite insufficient evidence

### System Performance

Measure:

- Investigation latency
- Batch processing time
- Cost per investigation
- Audit-trail completeness

---

## 6. Benchmark Case Structure

Each case should contain:

```text
case_id
difficulty
source_records
hidden_ground_truth
expected_evidence
expected_resolution
financial_impact