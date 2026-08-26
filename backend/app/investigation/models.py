from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class Hypothesis:
    hypothesis: str
    status: str = "OPEN"
    confidence: Decimal | None = None
    reasoning: str | None = None


@dataclass
class Evidence:
    evidence_type: str
    record_type: str
    record_id: str | None = None
    description: str | None = None


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class Contradiction:
    description: str
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class FinancialAnalysis:
    expected_amount: Decimal | None = None
    observed_amount: Decimal | None = None
    difference: Decimal | None = None
