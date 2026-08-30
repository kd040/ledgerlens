import { useParams } from "react-router-dom";
import { useInvestigationEvidence } from "../../api/queries";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/AsyncState";
import { formatDateTime } from "../../lib/format";

export function EvidenceTab() {
  const { id } = useParams<{ id: string }>();
  const evidence = useInvestigationEvidence(id);

  if (evidence.isLoading) return <LoadingState message="Loading evidence…" />;
  if (evidence.isError) return <ErrorState message="Could not load evidence." />;

  const rows = evidence.data ?? [];

  if (rows.length === 0) {
    return <EmptyState message="No evidence has been gathered yet." />;
  }

  return (
    <div className="ruled-paper rounded-lg border border-border bg-surface px-4">
      <ul>
        {rows.map((item) => (
          <li key={item.id} className="flex items-baseline gap-3 py-2.5">
            <span className="w-40 shrink-0 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
              {item.evidenceType} · {item.recordType}
            </span>
            <p className="flex-1 text-sm text-ink">{item.description}</p>
            <span className="shrink-0 font-mono text-xs text-ink-faint">
              {formatDateTime(item.createdAt)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
