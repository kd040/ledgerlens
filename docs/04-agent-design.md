# LedgerLens — AI Investigator Design

## 1. Objective

The AI Investigator investigates financial exceptions using controlled tools and structured evidence.

Its responsibility is to determine:

- What happened?
- Why did it happen?
- What evidence supports the explanation?
- Which alternative explanations were rejected?
- How confident is the investigation?
- Should the case be resolved, reviewed, or escalated?

The investigator must prefer evidence-backed uncertainty over unsupported conclusions.

---

## 2. Agent State

Each investigation maintains explicit state:

```text
InvestigationState

├── investigation_id
├── exception_id
├── exception_context
├── hypotheses[]
├── evidence[]
├── tool_calls[]
├── contradictions[]
├── financial_analysis
├── root_cause
├── confidence
├── recommendation
└── status