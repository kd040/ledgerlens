import { useParams } from "react-router-dom";
import {
  useInvestigationContradictions,
  useInvestigationEvidence,
  useInvestigationHypotheses,
  useInvestigationToolCalls,
} from "../../api/queries";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/AsyncState";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { formatDateTime } from "../../lib/format";
import { hypothesisStatusTone, type StatusTone } from "../../lib/status";

interface TimelineEntry {
  at: Date;
  kind: "Tool call" | "Evidence" | "Hypothesis" | "Contradiction";
  tone: StatusTone;
  title: string;
  detail: string;
}

export function TimelineTab() {
  const { id } = useParams<{ id: string }>();
  const toolCalls = useInvestigationToolCalls(id);
  const evidence = useInvestigationEvidence(id);
  const hypotheses = useInvestigationHypotheses(id);
  const contradictions = useInvestigationContradictions(id);

  const queries = [toolCalls, evidence, hypotheses, contradictions];
  if (queries.some((q) => q.isLoading)) {
    return <LoadingState message="Building audit timeline…" />;
  }
  if (queries.some((q) => q.isError)) {
    return <ErrorState message="Could not load the timeline." />;
  }

  const entries: TimelineEntry[] = [
    ...(toolCalls.data ?? []).map((row) => ({
      at: row.calledAt,
      kind: "Tool call" as const,
      tone: "neutral" as StatusTone,
      title: row.toolName,
      detail: "Deterministic tool call against persisted financial data.",
    })),
    ...(evidence.data ?? []).map((row) => ({
      at: row.createdAt,
      kind: "Evidence" as const,
      tone: "accent" as StatusTone,
      title: `${row.evidenceType} · ${row.recordType}`,
      detail: row.description,
    })),
    ...(hypotheses.data ?? []).map((row) => ({
      at: row.createdAt,
      kind: "Hypothesis" as const,
      tone: hypothesisStatusTone(row.status),
      title: `${row.hypothesis} — ${row.status.replaceAll("_", " ")}`,
      detail: row.reasoning,
    })),
    ...(contradictions.data ?? []).map((row) => ({
      at: row.createdAt,
      kind: "Contradiction" as const,
      tone: "danger" as StatusTone,
      title: "Contradiction detected",
      detail: row.description,
    })),
  ].sort((a, b) => a.at.getTime() - b.at.getTime());

  if (entries.length === 0) {
    return <EmptyState message="Nothing has happened in this investigation yet." />;
  }

  return (
    <ol className="flex flex-col gap-3 border-l border-border pl-4">
      {entries.map((entry, index) => (
        <li key={index} className="relative">
          <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-border" />
          <div className="flex items-center gap-2">
            <StatusBadge label={entry.kind} tone={entry.tone} />
            <span className="text-sm font-medium text-ink">{entry.title}</span>
            <span className="ml-auto text-xs text-ink-faint">
              {formatDateTime(entry.at)}
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-muted">{entry.detail}</p>
        </li>
      ))}
    </ol>
  );
}
