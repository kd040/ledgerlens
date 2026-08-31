import { useMemo, useState } from "react";
import { useExceptions, useRunReconciliationSource } from "../api/queries";
import { ApiError } from "../api/client";
import { BarComparison } from "../components/ui/BarComparison";
import { DataTable } from "../components/ui/DataTable";
import { DonutChart } from "../components/ui/DonutChart";
import { FinancialGapBreakdown } from "../components/investigation/FinancialGapBreakdown";
import { TransactionDetailDrawer } from "../components/investigation/TransactionDetailDrawer";
import { RunProgress } from "../components/ui/RunProgress";
import { StatTile } from "../components/ui/StatTile";
import { StatusBadge } from "../components/ui/StatusBadge";
import { TrendChart } from "../components/ui/TrendChart";
import { ErrorState, EmptyState } from "../components/ui/AsyncState";
import { formatMoney } from "../lib/format";
import { useLiveSync } from "../lib/useLiveSync";
import {
  buildExceptionByPayment,
  computeCategoryFinancialImpact,
  computeDailyGrossTrend,
  computeFinancials,
  computeInvestigationOutcome,
} from "../lib/reconciliationMetrics";
import {
  formatPeriodHeading,
  periodFromCustomRange,
  periodFromPreset,
  type Period,
  type PeriodPreset,
} from "../lib/period";
import {
  exceptionCodeLabel,
  isExceptionStatus,
  reconciliationStatusPresentation,
} from "../lib/status";
import type { DataSource, ReconciliationResult } from "../domain/types";

const SOURCES: { value: DataSource; label: string; hint: string }[] = [
  {
    value: "demo",
    label: "Demo Dataset",
    hint: "Fixed 100-record deterministic benchmark.",
  },
  {
    value: "razorpay_test",
    label: "Razorpay Test Mode",
    hint: "Live test-mode API calls. No real money.",
  },
];

const PRESETS: { value: PeriodPreset; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last7", label: "Last 7 Days" },
  { value: "custom", label: "Custom Range" },
];

function toDateInputValue(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function ReconciliationPage() {
  const runReconciliation = useRunReconciliationSource();
  const liveSync = useLiveSync();
  const exceptions = useExceptions();

  const [source, setSource] = useState<DataSource>("demo");
  const [preset, setPreset] = useState<PeriodPreset>("today");
  const [customStart, setCustomStart] = useState(() =>
    toDateInputValue(new Date()),
  );
  const [customEnd, setCustomEnd] = useState(() =>
    toDateInputValue(new Date()),
  );
  const [elapsedSeconds, setElapsedSeconds] = useState<number | null>(null);
  const [selected, setSelected] = useState<ReconciliationResult | null>(null);
  const [showGapBreakdown, setShowGapBreakdown] = useState(false);

  const period: Period | null = useMemo(() => {
    if (preset === "custom") return periodFromCustomRange(customStart, customEnd);
    return periodFromPreset(preset);
  }, [preset, customStart, customEnd]);

  // Live Sync and a manual run both produce the same summary shape;
  // Live Sync takes over the display once it's running.
  const summary = liveSync.active ? liveSync.latestSummary : runReconciliation.data ?? null;

  const handleRun = () => {
    if (!period) return;
    const startedAt = performance.now();
    setElapsedSeconds(null);
    runReconciliation.mutate(
      { source, from: period.from, to: period.to },
      {
        onSettled: () => setElapsedSeconds((performance.now() - startedAt) / 1000),
      },
    );
  };

  // Cross-reference each reconciliation row against the real exceptions
  // list (already fetched, same data source ExceptionsPage uses) so the
  // drawer can offer "View Investigation" without a new endpoint.
  const exceptionByPayment = useMemo(
    () => buildExceptionByPayment(exceptions.data ?? []),
    [exceptions.data],
  );

  const investigationOutcome = useMemo(
    () => computeInvestigationOutcome(summary?.results ?? [], exceptionByPayment),
    [summary, exceptionByPayment],
  );

  const financials = useMemo(
    () => (summary ? computeFinancials(summary.results) : null),
    [summary],
  );

  const dailyTrend = useMemo(
    () => (summary ? computeDailyGrossTrend(summary.results) : []),
    [summary],
  );
  const categoryImpacts = useMemo(
    () => computeCategoryFinancialImpact(summary?.results ?? [], exceptionByPayment),
    [summary, exceptionByPayment],
  );
  // Sum of each exception's own financial_impact -- see
  // OverviewPage.tsx for why this replaces summary.financialImpact
  // (which only sums EX01's `difference` and omits EX02/EX03).
  const financialImpactTotal = categoryImpacts.reduce((total, c) => total + c.amount, 0);

  const taxLabel = summary?.source === "razorpay_test" ? "GST on processing fees" : "GST / Tax";

  const errorMessage =
    runReconciliation.error instanceof ApiError
      ? runReconciliation.error.message
      : "Reconciliation run failed. Try again.";

  const isBusy = runReconciliation.isPending;
  const showResults = summary !== null && !isBusy;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-ink">Daily Reconciliation</h1>
        <p className="text-sm text-ink-muted">
          The transaction-level pipeline -- run fetch → reconcile → exception
          detection for a source and period, then inspect and investigate
          individual payments below. For the financial control summary, use
          Overview.
        </p>
      </div>

      <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4">
        <div>
          <div className="mb-1.5 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            Data source
          </div>
          <div className="flex flex-wrap gap-2">
            {SOURCES.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setSource(option.value)}
                disabled={liveSync.active}
                className={`rounded-md border px-3 py-2 text-left text-sm transition-colors disabled:opacity-50 ${
                  source === option.value
                    ? "border-accent bg-accent-muted text-accent"
                    : "border-border text-ink hover:bg-surface-muted"
                }`}
              >
                <div className="font-medium">{option.label}</div>
                <div className="text-xs text-ink-faint">{option.hint}</div>
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-1.5 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            Period (IST)
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {PRESETS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setPreset(option.value)}
                disabled={liveSync.active}
                className={`rounded-full px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
                  preset === option.value
                    ? "bg-accent-muted text-accent"
                    : "text-ink-muted hover:bg-surface-muted"
                }`}
              >
                {option.label}
              </button>
            ))}
            {preset === "custom" && (
              <div className="flex items-center gap-1.5">
                <input
                  type="date"
                  value={customStart}
                  onChange={(event) => setCustomStart(event.target.value)}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
                />
                <span className="text-ink-faint">to</span>
                <input
                  type="date"
                  value={customEnd}
                  onChange={(event) => setCustomEnd(event.target.value)}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
                />
              </div>
            )}
          </div>
          {preset === "custom" && !period && (
            <p className="mt-1.5 text-xs text-danger">
              Choose a valid start and end date (end must be after start).
            </p>
          )}
          {source === "demo" && (
            <p className="mt-1.5 text-xs text-ink-faint">
              Demo Dataset is a fixed benchmark and does not depend on the
              selected period.
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleRun}
            disabled={isBusy || !period || liveSync.active}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {isBusy ? "Running…" : "Run Reconciliation"}
          </button>

          {source === "razorpay_test" && (
            <button
              type="button"
              onClick={() => (liveSync.active ? liveSync.stop() : liveSync.start())}
              disabled={isBusy}
              className={`rounded-md border px-4 py-2 text-sm font-medium disabled:opacity-50 ${
                liveSync.active
                  ? "border-danger text-danger hover:bg-danger-muted"
                  : "border-accent text-accent hover:bg-accent-muted"
              }`}
            >
              {liveSync.active ? "Stop Live Sync" : "Start Live Sync"}
            </button>
          )}

          {liveSync.active && (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-success">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
              LIVE · Razorpay Test Mode
            </span>
          )}
        </div>

        {liveSync.active && (
          <div className="flex flex-wrap items-center gap-4 rounded-md bg-surface-muted px-3 py-2 text-xs text-ink-muted">
            <span>
              Last sync:{" "}
              {liveSync.lastSyncAt ? liveSync.lastSyncAt.toLocaleTimeString("en-IN") : "syncing…"}
            </span>
            <span>Newly detected this sync: {liveSync.lastNewCount}</span>
            {liveSync.error && <span className="text-danger">{liveSync.error}</span>}
          </div>
        )}
      </div>

      {isBusy && <RunProgress />}

      {runReconciliation.isError && !liveSync.active && <ErrorState message={errorMessage} />}

      {showResults && summary!.recordsProcessed === 0 && (
        <EmptyState
          message={
            summary!.source === "razorpay_test"
              ? "No Razorpay Test Mode transactions were found for this period."
              : "No transactions were processed for this period."
          }
        />
      )}

      {showResults && summary!.recordsProcessed > 0 && (
        <>
          <div className="rounded-lg border border-border bg-surface p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                {formatPeriodHeading(summary!.requestedPeriod.from, summary!.requestedPeriod.to)}
                {" · "}
                {SOURCES.find((s) => s.value === summary!.source)?.label}
              </div>
              {!liveSync.active && (
                <div className="text-xs text-ink-faint">
                  Completed in {(elapsedSeconds ?? summary!.durationSeconds).toFixed(1)}s
                </div>
              )}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-5">
              <StatTile label="Transactions" value={summary!.recordsProcessed} />
              <StatTile label="Reconciled" value={summary!.counts.reconciled} />
              <StatTile
                label="Settlement pending"
                value={summary!.counts.settlementPending}
              />
              {/* Only shown when it happened -- a permanently-zero tile
                  on the demo dataset would be noise, but hiding a
                  non-zero one would stop the tiles adding up to
                  Transactions. */}
              {summary!.counts.notCaptured > 0 && (
                <StatTile
                  label="Not captured"
                  value={summary!.counts.notCaptured}
                />
              )}
              {summary!.counts.unknownStatus > 0 && (
                <StatTile
                  label="Unsupported status"
                  value={summary!.counts.unknownStatus}
                />
              )}
              <StatTile
                label="Exceptions"
                value={summary!.counts.ex01 + summary!.counts.ex02 + summary!.counts.ex03}
              />
              <StatTile
                label="Financial impact"
                value={formatMoney(financialImpactTotal)}
                hint={`${categoryImpacts.reduce((n, c) => n + c.count, 0)} exceptions · View breakdown →`}
                onClick={() => setShowGapBreakdown(true)}
              />
            </div>
          </div>

          {financials && (
            <div className="rounded-lg border border-border bg-surface p-5">
              <div className="mb-1 text-sm font-semibold text-ink">
                Financial Overview
              </div>
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

              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div>
                  <div className="mb-2 text-xs font-medium text-ink-muted">
                    Cost Composition
                  </div>
                  {financials.fees + financials.tax + Math.abs(financials.adjustments) === 0 ? (
                    <p className="text-sm text-ink-faint">No fees, tax, or adjustments this period.</p>
                  ) : (
                    <DonutChart
                      centerLabel="cost"
                      valueFormat="money"
                      segments={[
                        { label: "Fees", value: financials.fees, color: "var(--color-accent)" },
                        { label: taxLabel, value: financials.tax, color: "var(--color-warning)" },
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

                <div>
                  <div className="mb-2 text-xs font-medium text-ink-muted">
                    Daily Financial Trend
                  </div>
                  {dailyTrend.length > 1 ? (
                    <TrendChart points={dailyTrend} />
                  ) : (
                    <p className="text-sm text-ink-faint">
                      Select a multi-day range to see a daily trend.
                    </p>
                  )}
                </div>
              </div>

              {summary!.source === "demo" && (
                <p className="mt-4 border-t border-border pt-3 text-xs text-ink-faint">
                  Demo Dataset tax/fee values are synthetic seed data, not
                  computed from a real pricing formula.
                </p>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 text-sm font-semibold text-ink">
                Reconciliation Health
              </div>
              <DonutChart
                centerLabel="processed"
                segments={[
                  { label: "Resolved", value: summary!.counts.reconciled, color: "var(--color-success)" },
                  { label: "Settlement Pending", value: summary!.counts.settlementPending, color: "var(--color-warning)" },
                  // DonutChart requires its segments to sum to the total
                  // it draws, so a never-captured payment has to appear
                  // here or the chart under-reports what was processed.
                  { label: "Not Captured", value: summary!.counts.notCaptured, color: "var(--color-neutral)" },
                  { label: "Unsupported Status", value: summary!.counts.unknownStatus, color: "var(--color-warning)" },
                  {
                    label: "Exceptions",
                    value: summary!.counts.ex01 + summary!.counts.ex02 + summary!.counts.ex03,
                    color: "var(--color-danger)",
                  },
                ]}
              />
            </div>

            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 text-sm font-semibold text-ink">
                Exception Breakdown
              </div>
              {summary!.counts.ex01 + summary!.counts.ex02 + summary!.counts.ex03 === 0 ? (
                <p className="text-sm text-ink-faint">No exceptions this period.</p>
              ) : (
                <DonutChart
                  centerLabel="exceptions"
                  segments={[
                    { label: exceptionCodeLabel("EX01"), value: summary!.counts.ex01, color: "var(--color-danger)" },
                    { label: exceptionCodeLabel("EX02"), value: summary!.counts.ex02, color: "var(--color-missing)" },
                    { label: exceptionCodeLabel("EX03"), value: summary!.counts.ex03, color: "var(--color-duplicate)" },
                  ]}
                />
              )}
            </div>

            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="mb-3 text-sm font-semibold text-ink">
                Investigation Outcome
              </div>
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

          <DataTable<ReconciliationResult>
            columns={[
              {
                header: "Payment",
                render: (row) => (
                  <span className="font-mono text-sm">{row.payment}</span>
                ),
              },
              {
                header: "Status",
                render: (row) => {
                  const presentation = reconciliationStatusPresentation(row.status);
                  return (
                    <StatusBadge
                      label={presentation.label}
                      tone={presentation.tone}
                      icon={presentation.icon}
                    />
                  );
                },
              },
              {
                header: "Exception",
                render: (row) =>
                  isExceptionStatus(row.status)
                    ? exceptionCodeLabel(row.status)
                    : "—",
              },
              {
                header: "Expected",
                render: (row) => formatMoney(row.expectedAmount),
              },
              {
                header: "Observed",
                render: (row) => formatMoney(row.observedAmount),
              },
              {
                header: "Difference",
                render: (row) => formatMoney(row.difference),
              },
            ]}
            rows={summary!.results}
            getRowKey={(row) => row.payment}
            onRowClick={(row) => setSelected(row)}
          />
        </>
      )}

      <TransactionDetailDrawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        result={selected}
        exceptionByPayment={exceptionByPayment}
        source={summary?.source ?? source}
      />

      <FinancialGapBreakdown
        open={showGapBreakdown}
        onClose={() => setShowGapBreakdown(false)}
        periodLabel={
          summary ? formatPeriodHeading(summary.requestedPeriod.from, summary.requestedPeriod.to) : ""
        }
        total={financialImpactTotal}
        categories={categoryImpacts}
        results={summary?.results ?? []}
        exceptionByPayment={exceptionByPayment}
        source={summary?.source ?? source}
      />
    </div>
  );
}
