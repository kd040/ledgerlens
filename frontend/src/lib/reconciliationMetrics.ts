/**
 * Derived-metrics helpers shared by ReconciliationPage and OverviewPage
 * -- both render the same `ReconciliationRunSummary.results` shape, so
 * the financials/trend/outcome math lives here once instead of being
 * duplicated per page.
 */
import type {
  ExceptionRecord,
  InvestigationSummary,
  ReconciliationResult,
} from "../domain/types";
import { extractPaymentReference } from "./payment";
import { investigationOutcomePresentation } from "./status";

function sum(values: (number | null)[]): number {
  return values.reduce((total: number, value) => total + (value ?? 0), 0);
}

export interface PeriodFinancials {
  gross: number;
  fees: number;
  tax: number;
  adjustments: number;
  expected: number;
  observed: number;
  gap: number;
}

export function computeFinancials(
  results: ReconciliationResult[],
): PeriodFinancials {
  const gross = sum(results.map((r) => r.grossAmount));
  const fees = sum(results.map((r) => r.feeAmount));
  const tax = sum(results.map((r) => r.taxAmount));
  const adjustments = sum(results.map((r) => r.adjustmentAmount));
  const expected = sum(results.map((r) => r.expectedAmount));
  const observed = sum(results.map((r) => r.observedAmount));
  return {
    gross,
    fees,
    tax,
    adjustments,
    expected,
    observed,
    gap: expected - observed,
  };
}

export interface DailyPoint {
  /** IST calendar date ("YYYY-MM-DD") this point summarizes -- carried
   * through so a chart can report back which day was clicked. */
  isoDate: string;
  label: string;
  value: number;
}

const shortDayFormatter = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  timeZone: "Asia/Kolkata",
});

function dailyTrend(
  results: ReconciliationResult[],
  valueOf: (row: ReconciliationResult) => number,
): DailyPoint[] {
  const byDay = new Map<string, number>();
  for (const row of results) {
    if (!row.paymentDate) continue;
    byDay.set(row.paymentDate, (byDay.get(row.paymentDate) ?? 0) + valueOf(row));
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([isoDate, value]) => ({
      isoDate,
      label: shortDayFormatter.format(new Date(`${isoDate}T00:00:00Z`)),
      value,
    }));
}

export function computeDailyGrossTrend(
  results: ReconciliationResult[],
): DailyPoint[] {
  return dailyTrend(results, (row) => row.grossAmount ?? 0);
}

export function computeDailyTransactionTrend(
  results: ReconciliationResult[],
): DailyPoint[] {
  return dailyTrend(results, () => 1);
}

export interface InvestigationOutcomeCounts {
  resolved: number;
  humanReview: number;
  escalated: number;
  pending: number;
}

export function computeInvestigationOutcome(
  results: ReconciliationResult[],
  exceptionByPayment: Map<string, ExceptionRecord>,
): InvestigationOutcomeCounts {
  const counts: InvestigationOutcomeCounts = {
    resolved: 0,
    humanReview: 0,
    escalated: 0,
    pending: 0,
  };
  for (const row of results) {
    if (row.status === "RECONCILED" || row.status === "SETTLEMENT_PENDING") continue;
    const record = exceptionByPayment.get(row.payment);
    if (!record) {
      counts.pending += 1;
      continue;
    }
    const outcome = investigationOutcomePresentation(
      record.investigationStatus ?? "IN_PROGRESS",
      record.investigationRecommendation,
    );
    if (outcome.label === "Resolved") counts.resolved += 1;
    else if (outcome.label === "Human Review") counts.humanReview += 1;
    else if (outcome.label === "Escalated") counts.escalated += 1;
    else counts.pending += 1;
  }
  return counts;
}

/** The investigations backing this period's own exceptions -- cross-
 * referenced against `results` the same way computeInvestigationOutcome
 * is, instead of filtering the global investigations list by a raw
 * startedAt date range. A date-range filter alone can't tell one data
 * source's investigations apart from another's (investigations carry no
 * source field), so it could show a previous source's rows the moment
 * their timestamps happened to fall inside the selected window. Scoping
 * through the current run's own result rows makes that impossible. */
export function computeRecentInvestigations(
  results: ReconciliationResult[],
  exceptionByPayment: Map<string, ExceptionRecord>,
  investigations: InvestigationSummary[],
  limit = 8,
): InvestigationSummary[] {
  const exceptionIds = new Set<string>();
  for (const row of results) {
    const record = exceptionByPayment.get(row.payment);
    if (record) exceptionIds.add(record.id);
  }
  return investigations
    .filter((row) => exceptionIds.has(row.exceptionId))
    .sort((a, b) => b.startedAt.getTime() - a.startedAt.getTime())
    .slice(0, limit);
}

/** Cross-references reconciliation result rows against the exceptions
 * list (fetched once, shared across pages) by the payment reference
 * embedded in each exception's description. */
export function buildExceptionByPayment(
  exceptions: ExceptionRecord[],
): Map<string, ExceptionRecord> {
  const map = new Map<string, ExceptionRecord>();
  for (const row of exceptions) {
    const ref = extractPaymentReference(row.description);
    if (ref) map.set(ref, row);
  }
  return map;
}

export type ExceptionCode = "EX01" | "EX02" | "EX03";
const EXCEPTION_CODES: ExceptionCode[] = ["EX01", "EX02", "EX03"];

export interface CategoryFinancialImpact {
  code: ExceptionCode;
  amount: number;
  count: number;
}

/**
 * The financial gap broken down by exception category, using each
 * exception's own `financial_impact` (computed once, per category, by
 * the backend's `create_exception` calls in reconciliation/engine.py --
 * EX01 gets the mismatch difference, EX02/EX03 get the full payment
 * amount) rather than re-deriving it from expected/observed sums, which
 * aren't populated the same way for every category. Scoped to the
 * period's own result rows so a stale/unrelated exception never leaks
 * into a period it didn't occur in. */
export function computeCategoryFinancialImpact(
  results: ReconciliationResult[],
  exceptionByPayment: Map<string, ExceptionRecord>,
): CategoryFinancialImpact[] {
  const totals: Record<ExceptionCode, { amount: number; count: number }> = {
    EX01: { amount: 0, count: 0 },
    EX02: { amount: 0, count: 0 },
    EX03: { amount: 0, count: 0 },
  };
  for (const row of results) {
    if (row.status !== "EX01" && row.status !== "EX02" && row.status !== "EX03") continue;
    const impact = exceptionByPayment.get(row.payment)?.financialImpact ?? 0;
    totals[row.status].amount += impact;
    totals[row.status].count += 1;
  }
  return EXCEPTION_CODES.map((code) => ({ code, ...totals[code] }));
}

/** The individual result rows for one exception category, each paired
 * with the same per-exception financial impact the category total is
 * built from -- so a transaction drill-down always sums back to the
 * category total shown above it. */
export function resultsForCategory(
  results: ReconciliationResult[],
  exceptionByPayment: Map<string, ExceptionRecord>,
  code: ExceptionCode,
): { result: ReconciliationResult; financialImpact: number }[] {
  return results
    .filter((row) => row.status === code)
    .map((result) => ({
      result,
      financialImpact: exceptionByPayment.get(result.payment)?.financialImpact ?? 0,
    }));
}

/** Narrows a multi-day summary's results down to one IST calendar day --
 * used to drill an aggregate range view into a single day without a
 * second network request. */
export function filterResultsByDate(
  results: ReconciliationResult[],
  isoDate: string,
): ReconciliationResult[] {
  return results.filter((row) => row.paymentDate === isoDate);
}
