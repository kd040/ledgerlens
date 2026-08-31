import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  useExceptions,
  useInvestigations,
  useRunReconciliationSource,
} from "../api/queries";
import { DataTable } from "../components/ui/DataTable";
import { DonutChart } from "../components/ui/DonutChart";
import { BarComparison } from "../components/ui/BarComparison";
import { FinancialGapBreakdown } from "../components/investigation/FinancialGapBreakdown";
import { RunProgress } from "../components/ui/RunProgress";
import { StatTile } from "../components/ui/StatTile";
import { StatusBadge } from "../components/ui/StatusBadge";
import { TrendChart } from "../components/ui/TrendChart";
import { ErrorState, EmptyState } from "../components/ui/AsyncState";
import { formatDateTime, formatMoney } from "../lib/format";
import {
  buildExceptionByPayment,
  computeCategoryFinancialImpact,
  computeDailyGrossTrend,
  computeDailyTransactionTrend,
  computeFinancials,
  computeInvestigationOutcome,
  computeRecentInvestigations,
} from "../lib/reconciliationMetrics";
import {
  formatPeriodHeading,
  istDateString,
  periodFromCustomRange,
  periodFromPreset,
  shiftIsoDate,
  type Period,
} from "../lib/period";
import { exceptionCodeLabel, investigationOutcomePresentation } from "../lib/status";
import type { DataSource, InvestigationSummary } from "../domain/types";

const SOURCES: { value: DataSource; label: string }[] = [
  { value: "demo", label: "Demo Dataset" },
  { value: "razorpay_test", label: "Razorpay Test Mode" },
];

type ViewMode = "day" | "range";
type RangeKind = "last7" | "custom";

function todayIso(): string {
  return istDateString(new Date());
}

/** Reads/writes every piece of Overview selection state as URL search
 * params -- so refreshing or sharing the page returns to the same
 * period instead of silently falling back to a different one. */
function useOverviewState() {
  const [searchParams, setSearchParams] = useSearchParams();

  const source = (searchParams.get("source") as DataSource | null) ?? "demo";
  const mode = (searchParams.get("mode") as ViewMode | null) ?? "day";
  const range = (searchParams.get("range") as RangeKind | null) ?? "last7";
  const date = searchParams.get("date") ?? todayIso();
  const start = searchParams.get("start") ?? date;
  const end = searchParams.get("end") ?? date;
  const drilled = searchParams.get("drilled") === "1";

  function update(patch: Record<string, string | null>) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value === null) next.delete(key);
          else next.set(key, value);
        }
        return next;
      },
      { replace: true },
    );
  }

  return { source, mode, range, date, start, end, drilled, update };
}

export function OverviewPage() {
  const navigate = useNavigate();
  const { source, mode, range, date, start, end, drilled, update } = useOverviewState();

  const exceptions = useExceptions();
  const investigations = useInvestigations();
  const runReconciliation = useRunReconciliationSource();
  const lastRequestKey = useRef<string | null>(null);

  const period: Period | null = useMemo(() => {
    if (mode === "day") return periodFromCustomRange(date, date);
    if (range === "last7") return periodFromPreset("last7");
    return periodFromCustomRange(start, end);
  }, [mode, date, range, start, end]);

  useEffect(() => {
    if (!period) return;
    // Demo Dataset is a fixed, period-independent benchmark (see
    // backend/app/datasources/demo.py) -- re-running it on every period
    // click would repeat the same ~20s reconciliation for byte-identical
    // results, so it's keyed by source alone here, not by period.
    const key =
      source === "demo"
        ? "demo"
        : `${source}|${period.from.toISOString()}|${period.to.toISOString()}`;
    if (lastRequestKey.current === key) return;
    lastRequestKey.current = key;
    runReconciliation.mutate({ source, from: period.from, to: period.to });
  }, [source, period, runReconciliation]);

  const today = todayIso();
  const activePreset =
    mode === "day" && date === today
      ? "today"
      : mode === "day" && date === shiftIsoDate(today, -1)
        ? "yesterday"
        : mode === "range" && range === "last7"
          ? "last7"
          : mode === "range" && range === "custom"
            ? "custom"
            : null;

  const summary = runReconciliation.data;

  const exceptionByPayment = useMemo(
    () => buildExceptionByPayment(exceptions.data ?? []),
    [exceptions.data],
  );
  const financials = useMemo(
    () => (summary ? computeFinancials(summary.results) : null),
    [summary],
  );
  const investigationOutcome = useMemo(
    () => computeInvestigationOutcome(summary?.results ?? [], exceptionByPayment),
    [summary, exceptionByPayment],
  );
  const transactionTrend = useMemo(
    () => (summary ? computeDailyTransactionTrend(summary.results) : []),
    [summary],
  );
  const financialTrend = useMemo(
    () => (summary ? computeDailyGrossTrend(summary.results) : []),
    [summary],
  );
  const categoryImpacts = useMemo(
    () => computeCategoryFinancialImpact(summary?.results ?? [], exceptionByPayment),
    [summary, exceptionByPayment],
  );
  // The "Financial impact" tile is the sum of each exception's own
  // financial_impact (see reconciliationMetrics.computeCategoryFinancialImpact)
  // rather than the backend's summary.financialImpact, which only sums
  // EX01's `difference` field and silently omits EX02/EX03 -- this way
  // the number on the tile always equals what the breakdown drawer sums to.
  const financialImpactTotal = categoryImpacts.reduce((total, c) => total + c.amount, 0);
  const [showGapBreakdown, setShowGapBreakdown] = useState(false);

  const recentInvestigations = useMemo(
    () =>
      computeRecentInvestigations(
        summary?.results ?? [],
        exceptionByPayment,
        investigations.data ?? [],
      ),
    [summary, exceptionByPayment, investigations.data],
  );

  const isBusy = runReconciliation.isPending;
  const isFirstLoad = isBusy && !summary;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-ink">Overview</h1>
        <p className="text-sm text-ink-muted">
          The financial control summary -- health, exceptions, and financial
          impact at a glance, for the source and period you choose below. For
          the transaction-level pipeline and individual payments, use
          Reconciliation.
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex gap-1.5">
            {SOURCES.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => update({ source: option.value })}
                className={`rounded-md px-2.5 py-1.5 text-xs font-medium ${
                  source === option.value
                    ? "bg-accent-muted text-accent"
                    : "text-ink-muted hover:bg-surface-muted"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="h-5 w-px bg-border" aria-hidden="true" />
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => update({ mode: "day", date: today, drilled: null })}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                activePreset === "today" ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              Today
            </button>
            <button
              type="button"
              onClick={() =>
                update({ mode: "day", date: shiftIsoDate(today, -1), drilled: null })
              }
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                activePreset === "yesterday" ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              Yesterday
            </button>
            <button
              type="button"
              onClick={() => update({ mode: "range", range: "last7", drilled: null })}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                activePreset === "last7" ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              Last 7 Days
            </button>
            <button
              type="button"
              onClick={() =>
                update({ mode: "range", range: "custom", start: date, end: date, drilled: null })
              }
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                activePreset === "custom" ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              Custom Range
            </button>
            {mode === "range" && range === "custom" && (
              <div className="flex items-center gap-1.5">
                <input
                  type="date"
                  value={start}
                  onChange={(event) => update({ start: event.target.value })}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
                />
                <span className="text-ink-faint">to</span>
                <input
                  type="date"
                  value={end}
                  onChange={(event) => update({ end: event.target.value })}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
                />
              </div>
            )}
          </div>

          {mode === "day" && (
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={() => update({ mode: "day", date: shiftIsoDate(date, -1) })}
                className="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface-muted"
              >
                ← Previous Day
              </button>
              <span className="min-w-[9rem] text-center font-mono text-xs font-medium text-ink">
                {period ? formatPeriodHeading(period.from, period.to) : date}
              </span>
              <button
                type="button"
                onClick={() => update({ mode: "day", date: shiftIsoDate(date, 1) })}
                disabled={date >= today}
                className="rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface-muted disabled:opacity-40"
              >
                Next Day →
              </button>
            </div>
          )}
        </div>

        {mode === "day" && drilled && (
          <button
            type="button"
            onClick={() => update({ mode: "range", drilled: null })}
            className="w-fit text-xs font-medium text-accent hover:underline"
          >
            ← Back to range view
          </button>
        )}

        {source === "demo" && (
          <p className="text-xs text-ink-faint">
            Demo Dataset is a fixed deterministic benchmark and does not
            change with the selected period.
          </p>
        )}
        {mode === "range" && range === "custom" && !period && (
          <p className="text-xs text-danger">
            Choose a valid start and end date (end must be after start).
          </p>
        )}
      </div>

      {isFirstLoad && <RunProgress />}

      {runReconciliation.isError && (
        <ErrorState message="Could not load reconciliation data for this period." />
      )}

      {summary && summary.recordsProcessed === 0 && (
        <EmptyState
          message={
            summary.source === "razorpay_test"
              ? "No Razorpay Test Mode transactions were found for this period."
              : "No transactions were processed for this period."
          }
        />
      )}

      {summary && summary.recordsProcessed > 0 && financials && (
        <>
          <div className="rounded-lg border border-border bg-surface p-5">
            <div className="mb-3 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
              {formatPeriodHeading(period!.from, period!.to)}
              {" · "}
              {SOURCES.find((s) => s.value === summary.source)?.label}
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <StatTile label="Transactions" value={summary.recordsProcessed} />
              <StatTile label="Resolved" value={summary.counts.reconciled} />
              <StatTile label="Settlement pending" value={summary.counts.settlementPending} />
              {summary.counts.notCaptured > 0 && (
                <StatTile label="Not captured" value={summary.counts.notCaptured} />
              )}
              {summary.counts.unknownStatus > 0 && (
                <StatTile
                  label="Unsupported status"
                  value={summary.counts.unknownStatus}
                />
              )}
              <StatTile
                label="Exceptions"
                value={summary.counts.ex01 + summary.counts.ex02 + summary.counts.ex03}
              />
              <StatTile
                label="Financial impact"
                value={formatMoney(financialImpactTotal)}
                hint={`${categoryImpacts.reduce((n, c) => n + c.count, 0)} exceptions · View breakdown →`}
                onClick={() => setShowGapBreakdown(true)}
              />
            </div>
          </div>

          <div className="rounded-lg border border-border bg-surface p-5">
            <div className="mb-4 text-sm font-semibold text-ink">Financial Overview</div>
            <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatTile label="Gross processed" value={formatMoney(financials.gross)} />
              <StatTile label="Expected settlement" value={formatMoney(financials.expected)} />
              <StatTile label="Actual settlement" value={formatMoney(financials.observed)} />
              <StatTile
                label="Financial gap"
                value={
                  <span className={financials.gap === 0 ? "text-success" : "text-danger"}>
                    {formatMoney(financials.gap)}
                  </span>
                }
              />
            </div>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <div className="mb-2 text-xs font-medium text-ink-muted">Cost Composition</div>
                {financials.fees + financials.tax + Math.abs(financials.adjustments) === 0 ? (
                  <p className="text-sm text-ink-faint">No fees, tax, or adjustments this period.</p>
                ) : (
                  <DonutChart
                    centerLabel="cost"
                    valueFormat="money"
                    segments={[
                      { label: "Fees", value: financials.fees, color: "var(--color-accent)" },
                      {
                        label: summary.source === "razorpay_test" ? "GST on processing fees" : "GST / Tax",
                        value: financials.tax,
                        color: "var(--color-warning)",
                      },
                      {
                        label: "Adjustments",
                        value: Math.abs(financials.adjustments),
                        color: "var(--color-duplicate)",
                      },
                    ]}
                  />
                )}
              </div>
              <div>
                <div className="mb-2 text-xs font-medium text-ink-muted">
                  Expected vs Observed Settlement
                </div>
                <BarComparison
                  items={[
                    { label: "Expected", value: financials.expected, color: "var(--color-accent)" },
                    { label: "Observed", value: financials.observed, color: "var(--color-success)" },
                  ]}
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 text-sm font-semibold text-ink">Reconciliation Health</div>
              <DonutChart
                centerLabel="processed"
                segments={[
                  { label: "Resolved", value: summary.counts.reconciled, color: "var(--color-success)" },
                  {
                    label: "Settlement Pending",
                    value: summary.counts.settlementPending,
                    color: "var(--color-warning)",
                  },
                  // Keeps the segments summing to recordsProcessed --
                  // see DonutChart's own invariant.
                  {
                    label: "Not Captured",
                    value: summary.counts.notCaptured,
                    color: "var(--color-neutral)",
                  },
                  {
                    label: "Unsupported Status",
                    value: summary.counts.unknownStatus,
                    color: "var(--color-warning)",
                  },
                  {
                    label: "Exceptions",
                    value: summary.counts.ex01 + summary.counts.ex02 + summary.counts.ex03,
                    color: "var(--color-danger)",
                  },
                ]}
              />
            </div>
            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 text-sm font-semibold text-ink">Exception Breakdown</div>
              {summary.counts.ex01 + summary.counts.ex02 + summary.counts.ex03 === 0 ? (
                <p className="text-sm text-ink-faint">No exceptions this period.</p>
              ) : (
                <DonutChart
                  centerLabel="exceptions"
                  segments={[
                    { label: exceptionCodeLabel("EX01"), value: summary.counts.ex01, color: "var(--color-danger)" },
                    { label: exceptionCodeLabel("EX02"), value: summary.counts.ex02, color: "var(--color-missing)" },
                    { label: exceptionCodeLabel("EX03"), value: summary.counts.ex03, color: "var(--color-duplicate)" },
                  ]}
                />
              )}
            </div>
            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 text-sm font-semibold text-ink">Investigation Outcome</div>
              {investigationOutcome.resolved +
                investigationOutcome.humanReview +
                investigationOutcome.escalated +
                investigationOutcome.pending ===
              0 ? (
                <p className="text-sm text-ink-faint">No exceptions this period.</p>
              ) : (
                <DonutChart
                  centerLabel="exceptions"
                  segments={[
                    { label: "Resolved", value: investigationOutcome.resolved, color: "var(--color-success)" },
                    { label: "Human Review", value: investigationOutcome.humanReview, color: "var(--color-accent)" },
                    { label: "Escalated", value: investigationOutcome.escalated, color: "var(--color-danger)" },
                    { label: "Not Yet Investigated", value: investigationOutcome.pending, color: "var(--color-neutral)" },
                  ]}
                />
              )}
            </div>
          </div>

          {mode === "range" && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-border bg-surface p-4">
                <div className="mb-2 text-sm font-semibold text-ink">Daily Transactions</div>
                {transactionTrend.length > 1 ? (
                  <TrendChart
                    points={transactionTrend.map((p) => ({ ...p, key: p.isoDate }))}
                    valueFormat="count"
                    selectedKey={date}
                    onPointClick={(point) => point.key && update({ mode: "day", date: point.key, drilled: "1" })}
                  />
                ) : (
                  <p className="text-sm text-ink-faint">Select a multi-day range to see a daily trend.</p>
                )}
              </div>
              <div className="rounded-lg border border-border bg-surface p-4">
                <div className="mb-2 text-sm font-semibold text-ink">Daily Financial Trend (Gross)</div>
                {financialTrend.length > 1 ? (
                  <TrendChart
                    points={financialTrend.map((p) => ({ ...p, key: p.isoDate }))}
                    selectedKey={date}
                    onPointClick={(point) => point.key && update({ mode: "day", date: point.key, drilled: "1" })}
                  />
                ) : (
                  <p className="text-sm text-ink-faint">Select a multi-day range to see a daily trend.</p>
                )}
              </div>
            </div>
          )}

          <div>
            <h2 className="mb-2 text-sm font-semibold text-ink">Recent investigations</h2>
            {recentInvestigations.length === 0 ? (
              <p className="text-sm text-ink-faint">No investigations started in this period.</p>
            ) : (
              <DataTable<InvestigationSummary>
                columns={[
                  { header: "Exception", render: (row) => row.exceptionCode },
                  { header: "Category", render: (row) => row.category },
                  {
                    header: "Status",
                    render: (row) => {
                      const presentation = investigationOutcomePresentation(row.status, row.recommendation);
                      return (
                        <StatusBadge label={presentation.label} tone={presentation.tone} icon={presentation.icon} />
                      );
                    },
                  },
                  { header: "Root cause", render: (row) => row.rootCause ?? "—" },
                  { header: "Started", render: (row) => formatDateTime(row.startedAt) },
                ]}
                rows={recentInvestigations}
                getRowKey={(row) => row.id}
                onRowClick={(row) => navigate(`/investigations/${row.id}/summary`)}
              />
            )}
          </div>
        </>
      )}

      <FinancialGapBreakdown
        open={showGapBreakdown}
        onClose={() => setShowGapBreakdown(false)}
        periodLabel={period ? formatPeriodHeading(period.from, period.to) : ""}
        total={financialImpactTotal}
        categories={categoryImpacts}
        results={summary?.results ?? []}
        exceptionByPayment={exceptionByPayment}
        source={summary?.source ?? source}
      />
    </div>
  );
}
