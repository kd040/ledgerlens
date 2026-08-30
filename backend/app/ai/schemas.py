"""The AI Investigator's structured output contract. The model's final
turn must call the submit_investigation_findings tool (see tools.py)
with input matching this shape exactly -- validated here with Pydantic
before anything is persisted or shown. Malformed output is rejected, not
repaired (see investigator.py)."""

from typing import Literal

from pydantic import BaseModel, Field

HypothesisStatus = Literal["SUPPORTED", "WEAKENED", "REJECTED", "INCONCLUSIVE"]
Recommendation = Literal["NO_ACTION", "HUMAN_REVIEW", "ESCALATE"]


class AiSummary(BaseModel):
    exception_code: str
    payment_reference: str
    financial_gap: str


class AiFinancialAnalysis(BaseModel):
    expected_amount: str
    observed_amount: str
    difference: str


class AiEvidenceReviewed(BaseModel):
    record_type: str
    record_id: str | None = None
    summary: str


class AiHypothesis(BaseModel):
    title: str
    status: HypothesisStatus
    confidence: int = Field(ge=0, le=100)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)


class AiContradiction(BaseModel):
    description: str


class AiRootCauseAssessment(BaseModel):
    known: str
    likely: str
    not_proven: str


class AiInvestigationResult(BaseModel):
    summary: AiSummary
    financial_analysis: AiFinancialAnalysis
    evidence_reviewed: list[AiEvidenceReviewed] = Field(default_factory=list)
    hypotheses: list[AiHypothesis] = Field(default_factory=list)
    contradictions: list[AiContradiction] = Field(default_factory=list)
    root_cause_assessment: AiRootCauseAssessment
    confidence: int = Field(ge=0, le=100)
    recommendation: Recommendation
