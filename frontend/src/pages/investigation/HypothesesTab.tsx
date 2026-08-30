import { useParams } from "react-router-dom";
import {
  useInvestigationContradictions,
  useInvestigationHypotheses,
} from "../../api/queries";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/AsyncState";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { formatDateTime, formatPercent } from "../../lib/format";
import { hypothesisStatusTone } from "../../lib/status";

export function HypothesesTab() {
  const { id } = useParams<{ id: string }>();
  const hypotheses = useInvestigationHypotheses(id);
  const contradictions = useInvestigationContradictions(id);

  if (hypotheses.isLoading || contradictions.isLoading) {
    return <LoadingState message="Loading hypotheses…" />;
  }
  if (hypotheses.isError || contradictions.isError) {
    return <ErrorState message="Could not load hypotheses." />;
  }

  const hypothesisRows = hypotheses.data ?? [];
  const contradictionRows = contradictions.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      {hypothesisRows.length === 0 ? (
        <EmptyState message="No hypotheses have been evaluated yet." />
      ) : (
        <ul className="flex flex-col gap-2">
          {hypothesisRows.map((hypothesis) => (
            <li
              key={hypothesis.id}
              className="rounded-lg border border-border bg-surface p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-ink">
                  {hypothesis.hypothesis}
                </p>
                <StatusBadge
                  label={hypothesis.status}
                  tone={hypothesisStatusTone(hypothesis.status)}
                />
              </div>
              <p className="mt-1.5 text-sm text-ink-muted">
                {hypothesis.reasoning}
              </p>
              <div className="mt-2 text-xs text-ink-faint">
                Confidence: {formatPercent(hypothesis.confidence)}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-ink">
          Contradictions
        </h2>
        <p className="mb-2 text-xs text-ink-faint">
          Contradictory evidence qualifies the hypotheses above -- it is why
          a supported hypothesis can still be escalated for human review
          instead of accepted outright.
        </p>
        {contradictionRows.length === 0 ? (
          <EmptyState message="No contradictory evidence was found." />
        ) : (
          <ul className="flex flex-col gap-2">
            {contradictionRows.map((contradiction) => (
              <li
                key={contradiction.id}
                className="rounded-lg border border-danger-muted bg-danger-muted p-4"
              >
                <p className="text-sm text-danger">
                  {contradiction.description}
                </p>
                <div className="mt-1.5 text-xs text-ink-faint">
                  {formatDateTime(contradiction.createdAt)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
