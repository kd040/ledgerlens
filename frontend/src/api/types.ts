/**
 * Raw API response shapes -- mirror the FastAPI JSON exactly (snake_case
 * fields, Decimal values serialized as strings). Nothing outside src/api
 * and src/domain should import from this file: components consume the
 * normalized domain types instead (see src/domain/types.ts).
 */

export interface ApiFinancialAnalysis {
  gross_amount?: string;
  fee_amount?: string;
  tax_amount?: string;
  adjustment_amount?: string;
  expected_amount: string;
  observed_amount: string;
  difference: string;
  settlement_count?: number;
}

export interface ApiException {
  id: string;
  exception_code: string;
  category: string;
  description: string;
  financial_impact: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  investigation_id: string | null;
  investigation_status: string | null;
  investigation_recommendation: string | null;
}

export interface ApiInvestigationSummary {
  id: string;
  exception_id: string;
  exception_code: string;
  category: string;
  root_cause: string | null;
  confidence: string | null;
  recommendation: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  /** The reviewer's own decision -- RESOLVED / ESCALATED -- kept apart
   * from the AI's `recommendation` (see backend migration 007). Null
   * until a reviewer has acted. */
  human_decision: string | null;
}

/** The AI Investigator's known/likely/not-proven breakdown (backend
 * migration 008) -- separate from the short `root_cause` sentence,
 * null until an AI investigation has actually run. */
export interface ApiRootCauseAssessment {
  known: string;
  likely: string;
  not_proven: string;
}

export interface ApiInvestigationDetail extends ApiInvestigationSummary {
  description: string;
  financial_impact: string | null;
  financial_analysis: ApiFinancialAnalysis | null;
  root_cause_assessment: ApiRootCauseAssessment | null;
}

export interface ApiCreateInvestigationResponse {
  id: string;
  exception_id: string;
  status: string;
}

export interface ApiRunInvestigationResponse {
  investigation_id: string;
  exception_code: string;
  payment: string;
  status: string;
  root_cause: string | null;
  financial_analysis: ApiFinancialAnalysis;
  confidence: string;
  recommendation: string;
  reason: string;
  difference: string;
}

export interface ApiEvidence {
  id: string;
  evidence_type: string;
  record_type: string;
  record_id: string | null;
  description: string;
  created_at: string;
}

export interface ApiHypothesis {
  id: string;
  hypothesis: string;
  status: string;
  confidence: string | null;
  reasoning: string;
  created_at: string;
}

export interface ApiContradiction {
  id: string;
  description: string;
  evidence_id: string | null;
  created_at: string;
}

export interface ApiToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  result: unknown;
  called_at: string;
}

/**
 * /reconciliation/run returns a row shape that varies by status -- see
 * backend/app/reconciliation/engine.py. Only `payment` and `status` are
 * guaranteed; the rest are present depending on which branch produced
 * the row.
 */
export interface ApiReconciliationResultRow {
  payment: string;
  status: string;
  category?: string;
  gross_amount?: string;
  fee_amount?: string;
  tax_amount?: string;
  adjustment_amount?: string;
  expected_amount?: string;
  observed_amount?: string;
  difference?: string;
  settlement_count?: number;
  payment_date?: string | null;
}

export interface ApiReconciliationRunResponse {
  status: string;
  results: ApiReconciliationResultRow[];
}

export interface ApiDailyFinancials {
  date: string;
  gross_amount: string;
  fee_amount: string;
  tax_amount: string;
  adjustment_amount: string;
  expected_amount: string;
  observed_amount: string;
  difference: string;
  settlement_count: number;
}

/** GET /investigations/{id}/financials/daily -- the investigation's own
 * real settlement dates only; available_dates is empty when there's
 * nothing to navigate (e.g. an EX02 investigation with no settlement). */
export interface ApiInvestigationDailyFinancialsResponse {
  available_dates: string[];
  selected_date: string | null;
  financials: ApiDailyFinancials | null;
}

/** GET /exceptions/{id}/duplicate-settlements -- the individual
 * settlement rows behind an EX03 exception (same fields the
 * duplicate-record investigation runner already retrieves). */
export interface ApiSettlementRecord {
  id: string;
  external_settlement_id: string;
  settlement_amount: string;
  currency: string;
  status: string;
  settlement_date: string;
  reference: string;
}

export interface ApiDuplicateSettlementsResponse {
  payment: string;
  settlements: ApiSettlementRecord[];
}

export interface ApiCurrentUser {
  id: string;
  email: string;
  role: "analyst" | "reviewer";
}

/** POST /reconciliation/sources/run -- fetch + normalize + persist +
 * scoped reconcile for one data source over one period, in one call. */
export interface ApiRunSourceResponse {
  source: string;
  requested_period: { from: string; to: string };
  records_fetched: { payments: number | null; settlements: number | null };
  records_processed: number;
  reconciliation: {
    reconciled: number;
    settlement_pending: number;
    ex01: number;
    ex02: number;
    ex03: number;
  };
  financial_impact: string;
  duration_seconds: number;
  results: ApiReconciliationResultRow[];
}

/** GET /reports/summary -- one aggregated Finance Controller payload
 * (see backend/app/reports/store.py). Every money field is a Decimal
 * string, as everywhere else; rates are already-rounded percentages. */
export interface ApiReportFinancialControl {
  total_payments: number;
  total_payment_value: string;
  total_settled_value: string;
  total_fees: string;
  total_taxes: string;
  total_adjustments: string;
  expected_settlement_value: string;
  total_financial_gap: string;
  reconciled_payments: number;
  reconciled_amount: string;
  duplicate_settled_payments: number;
  duplicate_settlement_value: string;
  unsettled_payments: number;
  unsettled_payment_value: string;
}

export interface ApiReportExceptionCode {
  code: string;
  label: string;
  count: number;
  financial_impact: string;
}

export interface ApiReportExceptions {
  total: number;
  by_code: ApiReportExceptionCode[];
  by_status: Record<string, number>;
  exception_exposure: string;
}

export interface ApiReportInvestigations {
  total: number;
  ai_investigations: number;
  awaiting_human_review: number;
  resolved: number;
  escalated: number;
  in_progress: number;
  resolution_rate: number;
  escalation_rate: number;
}

export interface ApiReportAiInsights {
  investigation_count: number;
  average_confidence: string | null;
  human_review_count: number;
  human_decisions: Record<string, number>;
  root_cause_categories: { category: string; count: number }[];
}

export interface ApiReportSummary {
  period: { start: string | null; end: string | null };
  available_period: { start: string | null; end: string | null };
  financial_control: ApiReportFinancialControl;
  exceptions: ApiReportExceptions;
  investigations: ApiReportInvestigations;
  ai: ApiReportAiInsights;
}
