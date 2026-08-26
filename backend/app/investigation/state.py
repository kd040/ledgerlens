from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.investigation.models import (
    Contradiction,
    Evidence,
    FinancialAnalysis,
    Hypothesis,
    ToolCall,
)


@dataclass
class InvestigationState:
    investigation_id: str
    exception_id: str
    exception_context: dict[str, Any] = field(default_factory=dict)

    hypotheses: list[Hypothesis] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)

    financial_analysis: FinancialAnalysis | None = None

    root_cause: str | None = None
    confidence: Decimal | None = None
    recommendation: str | None = None
    status: str = "IN_PROGRESS"
