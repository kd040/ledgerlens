import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useInvestigations } from "../api/queries";
import { DataTable } from "../components/ui/DataTable";
import { StatusBadge } from "../components/ui/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/AsyncState";
import { formatDateTime, formatPercent } from "../lib/format";
import {
  INVESTIGATION_LIFECYCLE_LABELS,
  RECOMMENDATION_LABELS,
  investigationLifecycleFilter,
  investigationOutcomePresentation,
  recommendationFilter,
  type InvestigationLifecycleFilter,
  type RecommendationFilter,
} from "../lib/status";
import type { InvestigationSummary } from "../domain/types";

const NO_ROWS: InvestigationSummary[] = [];

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

export function InvestigationsListPage() {
  const navigate = useNavigate();
  const investigations = useInvestigations();
  const [lifecycle, setLifecycle] = useState<InvestigationLifecycleFilter | "ALL">("ALL");
  const [recommendation, setRecommendation] = useState<RecommendationFilter | "ALL">("ALL");

  const rows = investigations.data ?? NO_ROWS;

  const filtered = useMemo(() => {
    let result = rows;
    if (lifecycle !== "ALL") {
      result = result.filter((row) => investigationLifecycleFilter(row.status) === lifecycle);
    }
    if (recommendation !== "ALL") {
      result = result.filter((row) => recommendationFilter(row.recommendation) === recommendation);
    }
    return result;
  }, [rows, lifecycle, recommendation]);

  if (investigations.isLoading) {
    return <LoadingState message="Loading investigations…" />;
  }

  if (investigations.isError) {
    return <ErrorState message="Could not load investigations from the API." />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-ink">Investigation Center</h1>
        <p className="text-sm text-ink-muted">
          Every investigation opened against a detected exception, with its
          conclusion and confidence.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            Investigation status
          </span>
          <button
            type="button"
            onClick={() => setLifecycle("ALL")}
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              lifecycle === "ALL" ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
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
                lifecycle === key ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
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
              recommendation === "ALL" ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
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
                recommendation === key ? "bg-accent-muted text-accent" : "text-ink-muted hover:bg-surface-muted"
              }`}
            >
              {RECOMMENDATION_LABELS[key]}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          message={rows.length === 0 ? "No investigations yet." : "No investigations match the current filters."}
        />
      ) : (
        <DataTable<InvestigationSummary>
          columns={[
            { header: "Exception", render: (row) => row.exceptionCode },
            { header: "Category", render: (row) => row.category },
            {
              header: "Status",
              render: (row) => {
                const presentation = investigationOutcomePresentation(
                  row.status,
                  row.recommendation,
                  row.humanDecision,
                );
                return (
                  <StatusBadge label={presentation.label} tone={presentation.tone} icon={presentation.icon} />
                );
              },
            },
            { header: "Root cause", render: (row) => row.rootCause ?? "—" },
            {
              header: "Confidence",
              render: (row) => formatPercent(row.confidence),
            },
            {
              header: "Started",
              render: (row) => formatDateTime(row.startedAt),
            },
          ]}
          rows={filtered}
          getRowKey={(row) => row.id}
          onRowClick={(row) => navigate(`/investigations/${row.id}/summary`)}
        />
      )}
    </div>
  );
}
