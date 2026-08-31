/**
 * Domain/UI types. Components only ever import from here (and from
 * src/domain/normalize.ts to produce them) -- never from src/api/types.
 * Decimal strings are parsed to numbers once, at the normalization
 * boundary; timestamps are parsed to Date once, at the same boundary.
 */

export type InvestigationStatus = "IN_PROGRESS" | "COMPLETED" | "ESCALATED";

export type HypothesisStatus =
  | "SUPPORTED"
  | "REJECTED"
  | "INSUFFICIENT_EVIDENCE";

export type ReconciliationStatus =
  | "RECONCILED"
  | "SETTLEMENT_PENDING"
  /** The provider never captured this payment, so no settlement is owed
   * and it is not an exception -- see NON_SETTLEABLE_PAYMENT_STATUSES in
   * backend/app/reconciliation/engine.py. */
  | "NOT_CAPTURED"
  /** The provider reported a status this engine does not classify. Not
   * reconciled, and deliberately never an exception -- see
   * SETTLEABLE_PAYMENT_STATUSES in the engine. */
  | "UNKNOWN_STATUS"
  | "EX01"
  | "EX02"
  | "EX03";

export interface FinancialAnalysis {
  grossAmount: number | null;
  feeAmount: number | null;
  taxAmount: number | null;
  adjustmentAmount: number | null;
  expectedAmount: number;
  observedAmount: number;
  difference: number;
  settlementCount: number | null;
}

export interface ExceptionRecord {
  id: string;
  exceptionCode: string;
  category: string;
  description: string;
  financialImpact: number | null;
  status: string;
  createdAt: Date;
  updatedAt: Date;
  investigationId: string | null;
  investigationStatus: InvestigationStatus | null;
  investigationRecommendation: string | null;
}

export type HumanDecision = "RESOLVED" | "ESCALATED";

export interface InvestigationSummary {
  id: string;
  exceptionId: string;
  exceptionCode: string;
  category: string;
  rootCause: string | null;
  confidence: number | null;
  recommendation: string | null;
  status: InvestigationStatus;
  startedAt: Date;
  completedAt: Date | null;
  /** The reviewer's own decision -- separate from `recommendation`,
   * which stays AI-authored. Null until a reviewer has acted. */
  humanDecision: HumanDecision | null;
}

export type UserRole = "analyst" | "reviewer";

export interface CurrentUser {
  id: string;
  email: string;
  role: UserRole;
}

/** The AI Investigator's known/likely/not-proven breakdown -- separate
 * from the short `rootCause` sentence, null until an AI investigation
 * has run (see backend migration 008). "Likely" is a reasonable
 * inference the evidence supports, never presented as fact. */
export interface RootCauseAssessment {
  known: string;
  likely: string;
  notProven: string;
}

export interface InvestigationDetail extends InvestigationSummary {
  description: string;
  financialImpact: number | null;
  financialAnalysis: FinancialAnalysis | null;
  rootCauseAssessment: RootCauseAssessment | null;
}

export interface Evidence {
  id: string;
  evidenceType: string;
  recordType: string;
  recordId: string | null;
  description: string;
  createdAt: Date;
}

export interface Hypothesis {
  id: string;
  hypothesis: string;
  status: HypothesisStatus;
  confidence: number | null;
  reasoning: string;
  createdAt: Date;
}

export interface Contradiction {
  id: string;
  description: string;
  evidenceId: string | null;
  createdAt: Date;
}

export interface ToolCall {
  id: string;
  toolName: string;
  arguments: Record<string, unknown>;
  result: unknown;
  calledAt: Date;
}

export interface ReconciliationResult {
  payment: string;
  status: ReconciliationStatus;
  category: string | null;
  grossAmount: number | null;
  feeAmount: number | null;
  taxAmount: number | null;
  adjustmentAmount: number | null;
  expectedAmount: number | null;
  observedAmount: number | null;
  difference: number | null;
  settlementCount: number | null;
  /** IST calendar date ("YYYY-MM-DD") the payment was created, for
   * day-bucketing the daily financial trend -- kept as the raw date
   * string, not a Date, since it's a label, not an instant. */
  paymentDate: string | null;
  /** The actual instant the payment was created, as reported by the
   * source provider. A real Date, unlike paymentDate's day label. */
  paymentCreatedAt: Date | null;
  /** The provider's own status for the payment ("captured", "created",
   * ...), distinct from the reconciliation outcome. */
  paymentStatus: string | null;
}

export interface DailyFinancials {
  date: string;
  grossAmount: number;
  feeAmount: number;
  taxAmount: number;
  adjustmentAmount: number;
  expectedAmount: number;
  observedAmount: number;
  difference: number;
  settlementCount: number;
}

export interface InvestigationDailyFinancials {
  availableDates: string[];
  selectedDate: string | null;
  financials: DailyFinancials | null;
}

export interface SettlementRecord {
  id: string;
  externalSettlementId: string;
  settlementAmount: number;
  currency: string;
  status: string;
  settlementDate: Date;
  reference: string;
}

export interface DuplicateSettlements {
  payment: string;
  settlements: SettlementRecord[];
}

export type DataSource = "demo" | "razorpay_test";

export interface ReconciliationCounts {
  reconciled: number;
  settlementPending: number;
  ex01: number;
  ex02: number;
  ex03: number;
  notCaptured: number;
  unknownStatus: number;
}

export interface ReconciliationRunSummary {
  source: DataSource;
  requestedPeriod: { from: Date; to: Date };
  recordsFetched: { payments: number | null; settlements: number | null };
  recordsProcessed: number;
  counts: ReconciliationCounts;
  financialImpact: number;
  durationSeconds: number;
  results: ReconciliationResult[];
}

/** The Reports page's single payload, money already parsed to numbers.
 * Mirrors backend/app/reports/store.py section for section. */
export interface ReportFinancialControl {
  totalPayments: number;
  totalPaymentValue: number;
  totalSettledValue: number;
  totalFees: number;
  totalTaxes: number;
  totalAdjustments: number;
  expectedSettlementValue: number;
  totalFinancialGap: number;
  reconciledPayments: number;
  reconciledAmount: number;
  duplicateSettledPayments: number;
  duplicateSettlementValue: number;
  unsettledPayments: number;
  unsettledPaymentValue: number;
  notCapturedPayments: number;
  notCapturedValue: number;
}

export interface ReportExceptionCode {
  code: string;
  label: string;
  count: number;
  financialImpact: number;
}

export interface ReportExceptions {
  total: number;
  byCode: ReportExceptionCode[];
  byStatus: { status: string; count: number }[];
  exceptionExposure: number;
}

export interface ReportInvestigations {
  total: number;
  aiInvestigations: number;
  awaitingHumanReview: number;
  resolved: number;
  escalated: number;
  inProgress: number;
  resolutionRate: number;
  escalationRate: number;
}

export interface ReportAiInsights {
  investigationCount: number;
  averageConfidence: number | null;
  humanReviewCount: number;
  humanDecisions: { decision: string; count: number }[];
  rootCauseCategories: { category: string; count: number }[];
}

export interface ReportSummary {
  period: { start: string | null; end: string | null };
  availablePeriod: { start: string | null; end: string | null };
  financialControl: ReportFinancialControl;
  exceptions: ReportExceptions;
  investigations: ReportInvestigations;
  ai: ReportAiInsights;
}
