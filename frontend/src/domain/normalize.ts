/**
 * The single place API Decimal-strings and timestamps get parsed.
 * Every function here is a pure Api* -> domain-type mapping. Nothing
 * else in the app should call Number()/new Date() on API fields.
 */
import type {
  ApiContradiction,
  ApiCurrentUser,
  ApiDailyFinancials,
  ApiDuplicateSettlementsResponse,
  ApiEvidence,
  ApiException,
  ApiFinancialAnalysis,
  ApiHypothesis,
  ApiInvestigationDailyFinancialsResponse,
  ApiInvestigationDetail,
  ApiInvestigationSummary,
  ApiReconciliationResultRow,
  ApiReportSummary,
  ApiRootCauseAssessment,
  ApiRunSourceResponse,
  ApiToolCall,
} from "../api/types";
import type {
  Contradiction,
  CurrentUser,
  DailyFinancials,
  DuplicateSettlements,
  ExceptionRecord,
  Evidence,
  FinancialAnalysis,
  HumanDecision,
  Hypothesis,
  HypothesisStatus,
  InvestigationDailyFinancials,
  InvestigationDetail,
  InvestigationStatus,
  InvestigationSummary,
  ReconciliationResult,
  ReconciliationRunSummary,
  ReconciliationStatus,
  ReportSummary,
  RootCauseAssessment,
  ToolCall,
} from "./types";

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function toRequiredNumber(value: string): number {
  return Number(value);
}

export function normalizeFinancialAnalysis(
  api: ApiFinancialAnalysis,
): FinancialAnalysis {
  return {
    grossAmount: toNumber(api.gross_amount),
    feeAmount: toNumber(api.fee_amount),
    taxAmount: toNumber(api.tax_amount),
    adjustmentAmount: toNumber(api.adjustment_amount),
    expectedAmount: toRequiredNumber(api.expected_amount),
    observedAmount: toRequiredNumber(api.observed_amount),
    difference: toRequiredNumber(api.difference),
    settlementCount: api.settlement_count ?? null,
  };
}

export function normalizeException(api: ApiException): ExceptionRecord {
  return {
    id: api.id,
    exceptionCode: api.exception_code,
    category: api.category,
    description: api.description,
    financialImpact: toNumber(api.financial_impact),
    status: api.status,
    createdAt: new Date(api.created_at),
    updatedAt: new Date(api.updated_at),
    investigationId: api.investigation_id,
    investigationStatus: api.investigation_status as InvestigationStatus | null,
    investigationRecommendation: api.investigation_recommendation,
  };
}

export function normalizeInvestigationSummary(
  api: ApiInvestigationSummary,
): InvestigationSummary {
  return {
    id: api.id,
    exceptionId: api.exception_id,
    exceptionCode: api.exception_code,
    category: api.category,
    rootCause: api.root_cause,
    confidence: toNumber(api.confidence),
    recommendation: api.recommendation,
    status: api.status as InvestigationStatus,
    startedAt: new Date(api.started_at),
    completedAt: api.completed_at ? new Date(api.completed_at) : null,
    humanDecision: api.human_decision as HumanDecision | null,
  };
}

export function normalizeCurrentUser(api: ApiCurrentUser): CurrentUser {
  return { id: api.id, email: api.email, role: api.role };
}

function normalizeRootCauseAssessment(
  api: ApiRootCauseAssessment,
): RootCauseAssessment {
  return { known: api.known, likely: api.likely, notProven: api.not_proven };
}

export function normalizeInvestigationDetail(
  api: ApiInvestigationDetail,
): InvestigationDetail {
  return {
    ...normalizeInvestigationSummary(api),
    description: api.description,
    financialImpact: toNumber(api.financial_impact),
    financialAnalysis: api.financial_analysis
      ? normalizeFinancialAnalysis(api.financial_analysis)
      : null,
    rootCauseAssessment: api.root_cause_assessment
      ? normalizeRootCauseAssessment(api.root_cause_assessment)
      : null,
  };
}

export function normalizeEvidence(api: ApiEvidence): Evidence {
  return {
    id: api.id,
    evidenceType: api.evidence_type,
    recordType: api.record_type,
    recordId: api.record_id,
    description: api.description,
    createdAt: new Date(api.created_at),
  };
}

export function normalizeHypothesis(api: ApiHypothesis): Hypothesis {
  return {
    id: api.id,
    hypothesis: api.hypothesis,
    status: api.status as HypothesisStatus,
    confidence: toNumber(api.confidence),
    reasoning: api.reasoning,
    createdAt: new Date(api.created_at),
  };
}

export function normalizeContradiction(
  api: ApiContradiction,
): Contradiction {
  return {
    id: api.id,
    description: api.description,
    evidenceId: api.evidence_id,
    createdAt: new Date(api.created_at),
  };
}

export function normalizeToolCall(api: ApiToolCall): ToolCall {
  return {
    id: api.id,
    toolName: api.tool_name,
    arguments: api.arguments,
    result: api.result,
    calledAt: new Date(api.called_at),
  };
}

export function normalizeReconciliationResult(
  api: ApiReconciliationResultRow,
): ReconciliationResult {
  return {
    payment: api.payment,
    status: api.status as ReconciliationStatus,
    category: api.category ?? null,
    grossAmount: toNumber(api.gross_amount),
    feeAmount: toNumber(api.fee_amount),
    taxAmount: toNumber(api.tax_amount),
    adjustmentAmount: toNumber(api.adjustment_amount),
    expectedAmount: toNumber(api.expected_amount),
    observedAmount: toNumber(api.observed_amount),
    difference: toNumber(api.difference),
    settlementCount: api.settlement_count ?? null,
    paymentDate: api.payment_date ?? null,
  };
}

function normalizeDailyFinancials(api: ApiDailyFinancials): DailyFinancials {
  return {
    date: api.date,
    grossAmount: toRequiredNumber(api.gross_amount),
    feeAmount: toRequiredNumber(api.fee_amount),
    taxAmount: toRequiredNumber(api.tax_amount),
    adjustmentAmount: toRequiredNumber(api.adjustment_amount),
    expectedAmount: toRequiredNumber(api.expected_amount),
    observedAmount: toRequiredNumber(api.observed_amount),
    difference: toRequiredNumber(api.difference),
    settlementCount: api.settlement_count,
  };
}

export function normalizeInvestigationDailyFinancials(
  api: ApiInvestigationDailyFinancialsResponse,
): InvestigationDailyFinancials {
  return {
    availableDates: api.available_dates,
    selectedDate: api.selected_date,
    financials: api.financials ? normalizeDailyFinancials(api.financials) : null,
  };
}

export function normalizeDuplicateSettlements(
  api: ApiDuplicateSettlementsResponse,
): DuplicateSettlements {
  return {
    payment: api.payment,
    settlements: api.settlements.map((s) => ({
      id: s.id,
      externalSettlementId: s.external_settlement_id,
      settlementAmount: toRequiredNumber(s.settlement_amount),
      currency: s.currency,
      status: s.status,
      settlementDate: new Date(s.settlement_date),
      reference: s.reference,
    })),
  };
}

export function normalizeRunSourceResponse(
  api: ApiRunSourceResponse,
): ReconciliationRunSummary {
  return {
    source: api.source as ReconciliationRunSummary["source"],
    requestedPeriod: {
      from: new Date(api.requested_period.from),
      to: new Date(api.requested_period.to),
    },
    recordsFetched: {
      payments: api.records_fetched.payments,
      settlements: api.records_fetched.settlements,
    },
    recordsProcessed: api.records_processed,
    counts: {
      reconciled: api.reconciliation.reconciled,
      settlementPending: api.reconciliation.settlement_pending,
      ex01: api.reconciliation.ex01,
      ex02: api.reconciliation.ex02,
      ex03: api.reconciliation.ex03,
    },
    financialImpact: toRequiredNumber(api.financial_impact),
    durationSeconds: api.duration_seconds,
    results: api.results.map(normalizeReconciliationResult),
  };
}

/** The report's status/decision maps arrive as objects so the backend
 * owns which buckets exist and in what order; they become arrays here
 * so components render them without re-deciding that order. */
export function normalizeReportSummary(api: ApiReportSummary): ReportSummary {
  const fc = api.financial_control;
  return {
    period: api.period,
    availablePeriod: api.available_period,
    financialControl: {
      totalPayments: fc.total_payments,
      totalPaymentValue: toRequiredNumber(fc.total_payment_value),
      totalSettledValue: toRequiredNumber(fc.total_settled_value),
      totalFees: toRequiredNumber(fc.total_fees),
      totalTaxes: toRequiredNumber(fc.total_taxes),
      totalAdjustments: toRequiredNumber(fc.total_adjustments),
      expectedSettlementValue: toRequiredNumber(fc.expected_settlement_value),
      totalFinancialGap: toRequiredNumber(fc.total_financial_gap),
      reconciledPayments: fc.reconciled_payments,
      reconciledAmount: toRequiredNumber(fc.reconciled_amount),
      duplicateSettledPayments: fc.duplicate_settled_payments,
      duplicateSettlementValue: toRequiredNumber(fc.duplicate_settlement_value),
      unsettledPayments: fc.unsettled_payments,
      unsettledPaymentValue: toRequiredNumber(fc.unsettled_payment_value),
    },
    exceptions: {
      total: api.exceptions.total,
      byCode: api.exceptions.by_code.map((row) => ({
        code: row.code,
        label: row.label,
        count: row.count,
        financialImpact: toRequiredNumber(row.financial_impact),
      })),
      byStatus: Object.entries(api.exceptions.by_status).map(
        ([status, count]) => ({ status, count }),
      ),
      exceptionExposure: toRequiredNumber(api.exceptions.exception_exposure),
    },
    investigations: {
      total: api.investigations.total,
      aiInvestigations: api.investigations.ai_investigations,
      awaitingHumanReview: api.investigations.awaiting_human_review,
      resolved: api.investigations.resolved,
      escalated: api.investigations.escalated,
      inProgress: api.investigations.in_progress,
      resolutionRate: api.investigations.resolution_rate,
      escalationRate: api.investigations.escalation_rate,
    },
    ai: {
      investigationCount: api.ai.investigation_count,
      averageConfidence: toNumber(api.ai.average_confidence),
      humanReviewCount: api.ai.human_review_count,
      humanDecisions: Object.entries(api.ai.human_decisions).map(
        ([decision, count]) => ({ decision, count }),
      ),
      rootCauseCategories: api.ai.root_cause_categories,
    },
  };
}
