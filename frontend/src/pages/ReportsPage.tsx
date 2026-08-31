import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useReportSummary } from "../api/queries";
import { DataTable } from "../components/ui/DataTable";
import { DonutChart } from "../components/ui/DonutChart";
import { BarComparison } from "../components/ui/BarComparison";
import { StatTile } from "../components/ui/StatTile";
import { ErrorState, LoadingState } from "../components/ui/AsyncState";
import { formatMoney } from "../lib/format";
import { exceptionCodeLabel } from "../lib/status";
import type { ReportSummary } from "../domain/types";

/** Exception-code colours, matching the Overview's Exception Breakdown
 * chart so the same category reads the same way on both pages. */
const CODE_COLORS: Record<string, string> = {
  EX01: "var(--color-danger)",
  EX02: "var(--color-missing)",
  EX03: "var(--color-duplicate)",
};

const STATUS_LABELS: Record<string, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In Progress",
  HUMAN_REVIEW: "Human Review",
  RESOLVED: "Resolved",
  ESCALATED: "Escalated",
};

const STATUS_COLORS: Record<string, string> = {
  OPEN: "var(--color-neutral)",
  IN_PROGRESS: "var(--color-warning)",
  HUMAN_REVIEW: "var(--color-accent)",
  RESOLVED: "var(--color-success)",
  ESCALATED: "var(--color-danger)",
};

/** RFC-4180 quoting: a field is wrapped whenever it contains a comma,
 * quote, or newline, and embedded quotes are doubled. Without this a
 * description containing a comma silently shifts every later column. */
function csvCell(value: string | number): string {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** The backend already rounds every rate and the AI confidence to one
 * decimal, so they are rendered verbatim rather than through
 * formatPercent, which rounds to whole numbers and would report a 91.7%
 * average confidence as 92%. */
function percent(value: number): string {
  return `${value}%`;
}

/** Money keeps both decimal places in the export even when they are
 * zero -- a spreadsheet column reading 273662.1 next to 263921.42 is a
 * reconciliation argument waiting to happen. */
function csvMoney(value: number): string {
  return value.toFixed(2);
}

/** Built from the same normalized object the page renders, so the export
 * and the screen cannot drift apart -- there is no second query and no
 * second set of arithmetic. */
function buildCsv(report: ReportSummary): string {
  const { financialControl: fc, exceptions, investigations, ai } = report;
  const rows: (string | number)[][] = [
    ["LedgerLens Report"],
    ["Period start", report.period.start ?? "All time"],
    ["Period end", report.period.end ?? "All time"],
    ["Generated", new Date().toISOString()],
    [],

    ["Financial Control Summary", "Value", "Basis"],
    ["Total payments", fc.totalPayments, "Payment date"],
    ["Gross processed", csvMoney(fc.totalPaymentValue), "Captured payments only"],
    ["Total settled value", csvMoney(fc.totalSettledValue), "Payment date"],
    ["Total fees", csvMoney(fc.totalFees), "Payment date"],
    ["Total taxes", csvMoney(fc.totalTaxes), "Payment date"],
    ["Total adjustments", csvMoney(fc.totalAdjustments), "Payment date"],
    [
      "Expected settlement value",
      csvMoney(fc.expectedSettlementValue),
      "Single-settlement payments",
    ],
    [
      "Total financial gap",
      csvMoney(fc.totalFinancialGap),
      "Single-settlement payments",
    ],
    ["Reconciled payments", fc.reconciledPayments, "Payment date"],
    ["Reconciled amount", csvMoney(fc.reconciledAmount), "Payment date"],
    ["Duplicate-settled payments", fc.duplicateSettledPayments, "Payment date"],
    [
      "Duplicate settlement value",
      csvMoney(fc.duplicateSettlementValue),
      "Payment date",
    ],
    ["Unsettled payments", fc.unsettledPayments, "Payment date"],
    [
      "Unsettled payment value",
      csvMoney(fc.unsettledPaymentValue),
      "Captured, not yet settled",
    ],
    ["Never-captured payments", fc.notCapturedPayments, "Payment date"],
    [
      "Never-captured value",
      csvMoney(fc.notCapturedValue),
      "Excluded from exposure",
    ],
    [
      "Exception exposure",
      csvMoney(exceptions.exceptionExposure),
      "Exception raised date",
    ],
    [],

    ["Exception Analysis by Code", "Count", "Financial impact"],
    ...exceptions.byCode.map((row) => [
      `${row.code} - ${row.label}`,
      row.count,
      csvMoney(row.financialImpact),
    ]),
    ["Total", exceptions.total, csvMoney(exceptions.exceptionExposure)],
    [],

    ["Exception Analysis by Status", "Count"],
    ...exceptions.byStatus.map((row) => [
      STATUS_LABELS[row.status] ?? row.status,
      row.count,
    ]),
    [],

    ["Investigation Outcomes", "Value"],
    ["Total investigations", investigations.total],
    ["AI investigations", investigations.aiInvestigations],
    ["Awaiting human review", investigations.awaitingHumanReview],
    ["Resolved", investigations.resolved],
    ["Escalated", investigations.escalated],
    ["In progress", investigations.inProgress],
    ["Resolution rate (%)", investigations.resolutionRate],
    ["Escalation rate (%)", investigations.escalationRate],
    [],

    ["AI Investigation Insights", "Value"],
    ["AI investigation count", ai.investigationCount],
    ["Average AI confidence (%)", ai.averageConfidence ?? "No AI investigations"],
    ["Awaiting human review", ai.humanReviewCount],
    ...ai.humanDecisions.map((row) => [`Human decision - ${row.decision}`, row.count]),
    [],

    ["Root Cause Category", "Investigations"],
    ...ai.rootCauseCategories.map((row) => [row.category, row.count]),
  ];

  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}

function downloadCsv(report: ReportSummary): void {
  const suffix =
    report.period.start && report.period.end
      ? `${report.period.start}_to_${report.period.end}`
      : "all-time";
  const blob = new Blob([buildCsv(report)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `ledgerlens-report-${suffix}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/** One labelled block. Every section states the timestamp it is scoped
 * by, because payments, exceptions, and investigations each carry only
 * their own -- saying so is the difference between an honest filter and
 * a misleading one. */
function Section({
  title,
  basis,
  children,
}: {
  title: string;
  basis: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        <p className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
          Scoped by {basis}
        </p>
      </div>
      {children}
    </section>
  );
}

export function ReportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const start = searchParams.get("start");
  const end = searchParams.get("end");
  const [exportError, setExportError] = useState<string | null>(null);

  const report = useReportSummary(start, end);

  function update(patch: Record<string, string | null>) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value === null || value === "") next.delete(key);
          else next.set(key, value);
        }
        return next;
      },
      { replace: true },
    );
  }

  const data = report.data;

  const gapItems = useMemo(
    () =>
      data
        ? [
            {
              label: "Expected settlement",
              value: data.financialControl.expectedSettlementValue,
              color: "var(--color-accent)",
            },
            {
              label: "Actually settled",
              value:
                data.financialControl.expectedSettlementValue -
                data.financialControl.totalFinancialGap,
              color: "var(--color-success)",
            },
          ]
        : [],
    [data],
  );

  function handleExport() {
    if (!data) return;
    try {
      downloadCsv(data);
      setExportError(null);
    } catch {
      setExportError("Could not generate the CSV export.");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">Reports</h1>
          <p className="max-w-2xl text-sm text-ink-muted">
            The financial control record: settled value, exception exposure,
            and investigation outcomes, aggregated from reconciliation and
            investigation results already on file. Read-only -- opening this
            page never re-runs reconciliation.
          </p>
        </div>
        <button
          type="button"
          onClick={handleExport}
          disabled={!data}
          className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-muted disabled:opacity-40"
        >
          Export CSV
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-surface p-4">
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-ink-muted">From</span>
          <input
            type="date"
            value={start ?? ""}
            min={data?.availablePeriod.start ?? undefined}
            max={data?.availablePeriod.end ?? undefined}
            onChange={(event) => update({ start: event.target.value })}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-ink-muted">To</span>
          <input
            type="date"
            value={end ?? ""}
            min={data?.availablePeriod.start ?? undefined}
            max={data?.availablePeriod.end ?? undefined}
            onChange={(event) => update({ end: event.target.value })}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
          />
        </label>
        <button
          type="button"
          onClick={() => update({ start: null, end: null })}
          disabled={!start && !end}
          className="rounded-md px-2.5 py-1.5 text-xs font-medium text-accent hover:bg-accent-muted disabled:opacity-40"
        >
          All time
        </button>
        <p className="ml-auto max-w-md text-xs text-ink-faint">
          Payments, exceptions, and investigations each carry only their own
          timestamp, so each section below is filtered on its own and says
          which one it uses.
        </p>
      </div>

      {report.isPending && <LoadingState message="Building report…" />}
      {report.isError && (
        <ErrorState message="Could not load the report for this period." />
      )}
      {exportError && <ErrorState message={exportError} />}

      {data && (
        <>
          <Section title="Financial Control Summary" basis="payment date">
            {/* One column below `sm`: these are the report's largest
                figures, and a two-up grid at 390px wraps a rupee amount
                mid-number. */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              <StatTile label="Total payments" value={data.financialControl.totalPayments} />
              <StatTile
                label="Gross processed"
                value={formatMoney(data.financialControl.totalPaymentValue)}
                hint="Captured payments only"
              />
              <StatTile
                label="Total settled value"
                value={formatMoney(data.financialControl.totalSettledValue)}
              />
              <StatTile
                label="Reconciled amount"
                value={formatMoney(data.financialControl.reconciledAmount)}
                hint={`${data.financialControl.reconciledPayments} payments fully reconciled`}
              />
              <StatTile
                label="Total fees"
                value={formatMoney(data.financialControl.totalFees)}
              />
              <StatTile
                label="Total taxes"
                value={formatMoney(data.financialControl.totalTaxes)}
              />
              <StatTile
                label="Total adjustments"
                value={formatMoney(data.financialControl.totalAdjustments)}
              />
              <StatTile
                label="Total financial gap"
                value={
                  <span
                    className={
                      data.financialControl.totalFinancialGap === 0
                        ? "text-success"
                        : "text-danger"
                    }
                  >
                    {formatMoney(data.financialControl.totalFinancialGap)}
                  </span>
                }
                hint="Expected minus settled, single-settlement payments"
              />
            </div>

            <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <div className="mb-2 text-xs font-medium text-ink-muted">
                  Expected vs Actually Settled
                </div>
                <BarComparison items={gapItems} />
                <p className="mt-2 text-xs text-ink-faint">
                  Compares only the payments with exactly one settlement --
                  the ones where the two figures are comparable. Unsettled
                  and duplicate-settled payments are reported separately
                  below.
                </p>
              </div>
              <div>
                <div className="mb-2 text-xs font-medium text-ink-muted">
                  Cost Composition
                </div>
                {data.financialControl.totalFees +
                  data.financialControl.totalTaxes +
                  Math.abs(data.financialControl.totalAdjustments) ===
                0 ? (
                  <p className="text-sm text-ink-faint">
                    No fees, tax, or adjustments in this period.
                  </p>
                ) : (
                  <DonutChart
                    centerLabel="cost"
                    valueFormat="money"
                    segments={[
                      {
                        label: "Fees",
                        value: data.financialControl.totalFees,
                        color: "var(--color-accent)",
                      },
                      {
                        label: "Taxes",
                        value: data.financialControl.totalTaxes,
                        color: "var(--color-warning)",
                      },
                      {
                        label: "Adjustments",
                        value: Math.abs(data.financialControl.totalAdjustments),
                        color: "var(--color-duplicate)",
                      },
                    ]}
                  />
                )}
              </div>
            </div>
          </Section>

          <Section title="Financial Impact" basis="exception raised date">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile
                label="Exception exposure"
                value={
                  <span className="text-danger">
                    {formatMoney(data.exceptions.exceptionExposure)}
                  </span>
                }
                hint={`${data.exceptions.total} exceptions affected`}
              />
              {data.exceptions.byCode.map((row) => (
                <StatTile
                  key={row.code}
                  label={`${row.code} exposure`}
                  value={formatMoney(row.financialImpact)}
                  hint={`${row.count} × ${row.label}`}
                />
              ))}
            </div>
            <div className="mt-5">
              <BarComparison
                items={data.exceptions.byCode.map((row) => ({
                  label: exceptionCodeLabel(row.code),
                  value: row.financialImpact,
                  color: CODE_COLORS[row.code] ?? "var(--color-neutral)",
                }))}
              />
            </div>
            <p className="mt-3 text-xs text-ink-faint">
              Each figure is the exception's own stored financial impact, as
              the reconciliation engine recorded it: EX01 carries the amount
              difference, EX02 and EX03 the full payment value at risk.
            </p>
          </Section>

          <Section title="Exception Analysis" basis="exception raised date">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div>
                <div className="mb-3 text-xs font-medium text-ink-muted">
                  By exception type
                </div>
                {data.exceptions.total === 0 ? (
                  <p className="text-sm text-ink-faint">
                    No exceptions in this period.
                  </p>
                ) : (
                  <DonutChart
                    centerLabel="exceptions"
                    segments={data.exceptions.byCode.map((row) => ({
                      label: exceptionCodeLabel(row.code),
                      value: row.count,
                      color: CODE_COLORS[row.code] ?? "var(--color-neutral)",
                    }))}
                  />
                )}
              </div>
              <div>
                <div className="mb-3 text-xs font-medium text-ink-muted">
                  By workflow status
                </div>
                {data.exceptions.total === 0 ? (
                  <p className="text-sm text-ink-faint">
                    No exceptions in this period.
                  </p>
                ) : (
                  <DonutChart
                    centerLabel="exceptions"
                    segments={data.exceptions.byStatus.map((row) => ({
                      label: STATUS_LABELS[row.status] ?? row.status,
                      value: row.count,
                      color: STATUS_COLORS[row.status] ?? "var(--color-neutral)",
                    }))}
                  />
                )}
              </div>
            </div>

            <div className="mt-5">
              <DataTable
                columns={[
                  { header: "Code", render: (row) => row.code },
                  { header: "Category", render: (row) => row.label },
                  {
                    header: "Count",
                    className: "font-mono tabular-nums",
                    render: (row) => row.count,
                  },
                  {
                    header: "Financial impact",
                    className: "font-mono tabular-nums",
                    render: (row) => formatMoney(row.financialImpact),
                  },
                ]}
                rows={data.exceptions.byCode}
                getRowKey={(row) => row.code}
              />
            </div>
            <p className="mt-3 text-xs text-ink-faint">
              An exception stores only Open, Resolved, or Escalated; In
              Progress and Human Review are read from the investigation
              attached to it, never from a status the database does not hold.
            </p>
          </Section>

          <Section title="Investigation Outcomes" basis="investigation start date">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              <StatTile
                label="Total investigations"
                value={data.investigations.total}
              />
              <StatTile
                label="AI investigations"
                value={data.investigations.aiInvestigations}
              />
              <StatTile
                label="Awaiting human review"
                value={data.investigations.awaitingHumanReview}
              />
              <StatTile label="Resolved" value={data.investigations.resolved} />
              <StatTile label="Escalated" value={data.investigations.escalated} />
              <StatTile label="In progress" value={data.investigations.inProgress} />
              <StatTile
                label="Resolution rate"
                value={percent(data.investigations.resolutionRate)}
              />
              <StatTile
                label="Escalation rate"
                value={percent(data.investigations.escalationRate)}
              />
            </div>
          </Section>

          <Section title="AI Investigation Insights" basis="investigation start date">
            {data.ai.investigationCount === 0 ? (
              <p className="text-sm text-ink-faint">
                No AI investigations have run in this period.
              </p>
            ) : (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                <StatTile
                  label="AI investigations"
                  value={data.ai.investigationCount}
                />
                <StatTile
                  label="Average AI confidence"
                  value={
                    data.ai.averageConfidence === null
                      ? "—"
                      : percent(data.ai.averageConfidence)
                  }
                />
                <StatTile
                  label="Awaiting human review"
                  value={data.ai.humanReviewCount}
                />
                {data.ai.humanDecisions.map((row) => (
                  <StatTile
                    key={row.decision}
                    label={`Decided ${STATUS_LABELS[row.decision] ?? row.decision}`}
                    value={row.count}
                  />
                ))}
              </div>
            )}

            <div className="mt-5">
              <div className="mb-3 text-xs font-medium text-ink-muted">
                Root cause categories
              </div>
              {data.ai.rootCauseCategories.length === 0 ? (
                <p className="text-sm text-ink-faint">
                  No investigations in this period.
                </p>
              ) : (
                <DataTable
                  columns={[
                    { header: "Category", render: (row) => row.category },
                    {
                      header: "Investigations",
                      className: "font-mono tabular-nums",
                      render: (row) => row.count,
                    },
                  ]}
                  rows={data.ai.rootCauseCategories}
                  getRowKey={(row) => row.category}
                />
              )}
              <p className="mt-3 text-xs text-ink-faint">
                Grouped by each investigation's exception category -- the
                stored classification. The per-investigation root-cause
                narrative is free text and lives on the investigation itself.
              </p>
            </div>
          </Section>
        </>
      )}
    </div>
  );
}
