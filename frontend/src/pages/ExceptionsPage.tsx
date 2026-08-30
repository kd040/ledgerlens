import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useExceptions, useStartInvestigation } from "../api/queries";
import { DataTable } from "../components/ui/DataTable";
import { StatusBadge } from "../components/ui/StatusBadge";
import { ErrorState, LoadingState, EmptyState } from "../components/ui/AsyncState";
import { formatDateTime, formatMoney } from "../lib/format";
import { extractDuplicateSettlementCount } from "../lib/payment";
import {
  EXCEPTION_CODE_LABELS,
  INVESTIGATION_LIFECYCLE_LABELS,
  RECOMMENDATION_LABELS,
  exceptionCodeLabel,
  investigationLifecycleFilter,
  investigationOutcomePresentation,
  recommendationFilter,
  type InvestigationLifecycleFilter,
  type RecommendationFilter,
} from "../lib/status";
import type { ExceptionRecord } from "../domain/types";

const CATEGORY_FILTERS: { code: string | "ALL"; label: string }[] = [
  { code: "ALL", label: "All" },
  ...Object.keys(EXCEPTION_CODE_LABELS).map((code) => ({
    code,
    label: exceptionCodeLabel(code),
  })),
];

const LIFECYCLE_FILTERS: InvestigationLifecycleFilter[] = [
  "not_started",
  "in_progress",
  "completed",
  "escalated",
];

const RECOMMENDATION_FILTERS: RecommendationFilter[] = [
  "human_review",
  "resolved",
  "no_action",
];

type SortKey = "detected" | "impact";

const NO_ROWS: ExceptionRecord[] = [];

export function ExceptionsPage() {
  const navigate = useNavigate();
  const exceptions = useExceptions();
  const startInvestigation = useStartInvestigation();
  const [category, setCategory] = useState<string | "ALL">("ALL");
  const [lifecycle, setLifecycle] = useState<InvestigationLifecycleFilter | "ALL">("ALL");
  const [recommendation, setRecommendation] = useState<RecommendationFilter | "ALL">("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("detected");

  const rows = exceptions.data ?? NO_ROWS;

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of rows) {
      counts.set(row.exceptionCode, (counts.get(row.exceptionCode) ?? 0) + 1);
    }
    return counts;
  }, [rows]);

  const filtered = useMemo(() => {
    let result = rows;
    if (category !== "ALL") {
      result = result.filter((row) => row.exceptionCode === category);
    }
    if (lifecycle !== "ALL") {
      result = result.filter(
        (row) => investigationLifecycleFilter(row.investigationId ? row.investigationStatus : null) === lifecycle,
      );
    }
    if (recommendation !== "ALL") {
      result = result.filter(
        (row) => recommendationFilter(row.investigationRecommendation) === recommendation,
      );
    }
    result = [...result].sort((a, b) => {
      if (sortKey === "impact") {
        return (b.financialImpact ?? 0) - (a.financialImpact ?? 0);
      }
      return b.createdAt.getTime() - a.createdAt.getTime();
    });
    return result;
  }, [rows, category, lifecycle, recommendation, sortKey]);

  if (exceptions.isLoading) {
    return <LoadingState message="Loading exceptions…" />;
  }

  if (exceptions.isError) {
    return <ErrorState message="Could not load exceptions from the API." />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-ink">Exception Center</h1>
        <p className="text-sm text-ink-muted">
          Financial discrepancies detected by reconciliation. Select one to
          view or start its investigation. Settlement Pending payments are
          not exceptions and appear in Reconciliation results instead.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1 border-b border-border">
        {CATEGORY_FILTERS.map((filter) => {
          const count =
            filter.code === "ALL"
              ? rows.length
              : (categoryCounts.get(filter.code) ?? 0);
          return (
            <button
              key={filter.code}
              type="button"
              onClick={() => setCategory(filter.code)}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                category === filter.code
                  ? "border-accent text-accent"
                  : "border-transparent text-ink-muted hover:text-ink"
              }`}
            >
              {filter.label}
              <span className="font-mono text-xs text-ink-faint">
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Two independent filter dimensions -- investigation lifecycle
          status and recommendation are different concepts and are never
          combined into one control. */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            Investigation status
          </span>
          <button
            type="button"
            onClick={() => setLifecycle("ALL")}
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              lifecycle === "ALL"
                ? "bg-accent-muted text-accent"
                : "text-ink-muted hover:bg-surface-muted"
            }`}
          >
            All
          </button>
          {LIFECYCLE_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setLifecycle(key)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                lifecycle === key
                  ? "bg-accent-muted text-accent"
                  : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              {INVESTIGATION_LIFECYCLE_LABELS[key]}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            Recommendation
          </span>
          <button
            type="button"
            onClick={() => setRecommendation("ALL")}
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              recommendation === "ALL"
                ? "bg-accent-muted text-accent"
                : "text-ink-muted hover:bg-surface-muted"
            }`}
          >
            All
          </button>
          {RECOMMENDATION_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setRecommendation(key)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                recommendation === key
                  ? "bg-accent-muted text-accent"
                  : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              {RECOMMENDATION_LABELS[key]}
            </button>
          ))}
        </div>
      </div>

      <div className="flex justify-end">
        <label className="flex items-center gap-1.5 text-xs text-ink-muted">
          Sort by
          <select
            value={sortKey}
            onChange={(event) => setSortKey(event.target.value as SortKey)}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
          >
            <option value="detected">Most recent</option>
            <option value="impact">Financial impact</option>
          </select>
        </label>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          message={
            rows.length === 0
              ? "No exceptions found. Run reconciliation to detect them."
              : "No exceptions match the current filters."
          }
        />
      ) : (
        <DataTable<ExceptionRecord>
          columns={[
            {
              header: "Exception",
              render: (row) => {
                const duplicateCount =
                  row.exceptionCode === "EX03"
                    ? extractDuplicateSettlementCount(row.description)
                    : null;
                return (
                  <div>
                    <div className="font-mono text-sm font-medium text-ink">
                      {exceptionCodeLabel(row.exceptionCode)}
                    </div>
                    {duplicateCount !== null && (
                      <div className="text-xs text-ink-faint">
                        {duplicateCount} settlement records detected
                      </div>
                    )}
                  </div>
                );
              },
            },
            {
              header: "Financial impact",
              render: (row) => (
                <span className="font-mono tabular-nums">
                  {formatMoney(row.financialImpact)}
                </span>
              ),
            },
            {
              header: "Status",
              render: (row) => {
                if (!row.investigationId) {
                  return <span className="text-ink-faint">Not started</span>;
                }
                const presentation = investigationOutcomePresentation(
                  row.investigationStatus ?? "IN_PROGRESS",
                  row.investigationRecommendation,
                );
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
              header: "Detected",
              render: (row) => formatDateTime(row.createdAt),
            },
            {
              header: "",
              render: (row) =>
                row.investigationId ? (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      navigate(
                        `/investigations/${row.investigationId}/summary`,
                      );
                    }}
                    className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-ink hover:bg-surface-muted"
                  >
                    View investigation
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={startInvestigation.isPending}
                    onClick={(event) => {
                      event.stopPropagation();
                      startInvestigation.mutate(row.id, {
                        onSuccess: (result) => {
                          navigate(
                            `/investigations/${result.investigation_id}/summary`,
                          );
                        },
                      });
                    }}
                    className="rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                  >
                    {startInvestigation.isPending
                      ? "Starting…"
                      : "Start investigation"}
                  </button>
                ),
            },
          ]}
          rows={filtered}
          getRowKey={(row) => row.id}
        />
      )}

      {startInvestigation.isError && (
        <ErrorState message="Could not start the investigation. Try again." />
      )}
    </div>
  );
}
