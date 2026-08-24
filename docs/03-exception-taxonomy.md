# LedgerLens — Exception Taxonomy

## 1. Purpose

This document defines the financial exception categories that LedgerLens must detect, investigate, classify, and resolve or escalate.

Each benchmark exception should have:

- A known ground-truth category
- A known root cause
- Supporting evidence
- Expected financial impact
- Expected resolution state

The taxonomy is designed to support deterministic reconciliation and objective evaluation of the AI investigator.

---

## 2. Exception Categories

### EX01 — Amount Mismatch

The expected financial amount and observed financial amount differ without an immediately explainable adjustment.

Example:

Payment:
₹1,000

Expected settlement:
₹970

Observed settlement:
₹950

Difference:
₹20

Possible causes include:

- Incorrect settlement amount
- Missing fee
- Incorrect adjustment
- Data corruption

Expected investigation:

The investigator must retrieve the related payment, settlement, fee, tax, refund, and adjustment records before determining the root cause.

---

### EX02 — Missing Record

A financial record expected by the reconciliation relationship cannot be found.

Examples:

- Payment without settlement
- Settlement without bank transaction
- Refund without corresponding payment

Expected investigation:

Determine whether the record is genuinely missing, delayed, or represented under another identifier.

Expected action:

- Resolve if reliable evidence establishes the explanation
- Escalate if the missing record cannot be explained

---

### EX03 — Duplicate Record

Multiple records appear to represent the same financial event.

Example:

Payment:
PAY-1001
₹500

Settlement A:
SET-2001
₹500

Settlement B:
SET-2002
₹500

Potential exposure:
₹500 duplicate settlement

Expected investigation:

Compare:

- Payment identifiers
- Amounts
- Timestamps
- Settlement references
- Bank references

Expected action:

Escalate unless deterministic evidence establishes that one record is a legitimate separate transaction.

---

### EX04 — Timing Mismatch

Related financial records exist but occur outside the expected processing or settlement window.

Example:

Payment captured:
1 August, 10:00

Normal settlement window:
1–2 August

Settlement observed:
7 August

Expected investigation:

Check:

- Payment status
- Settlement status
- Processing dates
- Batch identifiers
- Related adjustments
- Bank transaction timing

The investigator should distinguish a legitimate delayed settlement from an unexplained timing anomaly.

---

### EX05 — Partial Settlement

A payment is settled through multiple records or only part of the expected amount is settled.

Example:

Payment:
₹1,000

Settlement A:
₹600

Settlement B:
₹300

Total settled:
₹900

Unsettled amount:
₹100

Expected investigation:

Determine whether the remaining amount is explained by:

- Fee
- Tax
- Refund
- Adjustment
- Delayed settlement
- Missing settlement

The investigator must not automatically classify the difference as an error.

---

### EX06 — Refund Mismatch

A refund exists but does not reconcile with the original payment or settlement.

Example:

Payment:
₹1,000

Refund:
₹200

Expected remaining financial exposure:
₹800

Observed settlement:
₹1,000

Expected investigation:

Retrieve:

- Original payment
- Refund records
- Settlement records
- Bank transaction
- Related adjustments

Determine whether the refund was:

- Processed
- Pending
- Reversed
- Reflected elsewhere
- Missing from settlement reconciliation

---

### EX07 — Fee / Tax Discrepancy

Fees or taxes do not reconcile with the expected settlement calculation.

Expected formula:

net_amount =
gross_amount
- fees
- taxes
+ adjustments

Example:

Gross:
₹1,000

Expected fee:
₹20

Expected tax:
₹3.60

Expected net:
₹976.40

Observed net:
₹980.00

Potential discrepancy:
₹3.60

Expected investigation:

Retrieve all fee, tax, and adjustment records and compare them with the deterministic calculation.

---

### EX08 — Ambiguous / Unknown

Available evidence does not support a sufficiently reliable root-cause determination.

Example:

Payment exists.

Settlement exists.

Bank transaction exists.

Amounts differ.

No fee, tax, refund, or adjustment explains the difference.

Multiple plausible explanations remain.

Expected action:

Escalate.

The system must not fabricate an explanation simply to produce a resolution.

---

## 3. Root-Cause Categories

Each exception should ultimately map to a root cause where sufficient evidence exists.

Initial root causes include:

- Missing settlement
- Delayed settlement
- Incorrect settlement amount
- Duplicate settlement
- Partial settlement
- Missing refund
- Delayed refund
- Incorrect refund amount
- Incorrect fee
- Missing fee
- Incorrect tax
- Missing tax
- Incorrect adjustment
- Missing adjustment
- Duplicate transaction
- Data quality issue
- Unknown / insufficient evidence

---

## 4. Expected Resolution States

Every investigated exception must end in one of:

### RESOLVED

The root cause is sufficiently supported by evidence and the case satisfies the resolution policy.

### HUMAN_REVIEW

The evidence is sufficient to narrow the issue but policy requires human confirmation.

### ESCALATED

The evidence is insufficient, contradictory, or the case falls outside the approved automatic-resolution scope.

---

## 5. Evidence Requirements

An investigation should reference the records used to support its conclusion.

Potential evidence includes:

- Order records
- Payment records
- Settlement records
- Refund records
- Fee records
- Tax records
- Adjustment records
- Bank transactions
- Timestamps
- Amount calculations
- Reconciliation relationships

Evidence must be traceable to actual stored records.

---

## 6. Investigation Ground Truth

Each synthetic exception will contain hidden ground truth used only by the evaluation system.

Ground truth should include:

- Exception category
- Root cause
- Expected financial impact
- Expected resolution state
- Relevant record IDs
- Evidence IDs
- Plausible alternative hypotheses
- Correct hypothesis

The AI investigator must not have access to hidden ground truth during investigation.

---

## 7. Benchmark Design Principle

The benchmark should contain both:

### Easy cases

Cases where deterministic evidence clearly establishes the root cause.

### Medium cases

Cases requiring multiple related records to establish the explanation.

### Hard cases

Cases involving:

- Multiple possible explanations
- One-to-many relationships
- Many-to-one relationships
- Delayed records
- Conflicting evidence
- Partial settlements

### Adversarial cases

Cases intentionally designed to test whether the investigator:

- Hallucinates evidence
- Ignores contradictory records
- Incorrectly resolves ambiguous cases
- Confuses correlation with causation
- Overestimates confidence

---

## 8. Core Safety Principle

> If the evidence does not support a conclusion, escalation is the correct outcome.

A benchmark should therefore reward correct escalation rather than forcing every case into a root-cause category.