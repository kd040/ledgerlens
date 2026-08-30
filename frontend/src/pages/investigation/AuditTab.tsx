import { useParams } from "react-router-dom";
import { useInvestigationToolCalls } from "../../api/queries";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/AsyncState";
import { formatDateTime } from "../../lib/format";

export function AuditTab() {
  const { id } = useParams<{ id: string }>();
  const toolCalls = useInvestigationToolCalls(id);

  if (toolCalls.isLoading) return <LoadingState message="Loading audit trail…" />;
  if (toolCalls.isError) return <ErrorState message="Could not load the audit trail." />;

  const rows = toolCalls.data ?? [];

  if (rows.length === 0) {
    return <EmptyState message="No tool calls have been recorded yet." />;
  }

  return (
    <div className="ruled-paper rounded-lg border border-border bg-surface px-4">
      <ol>
        {rows.map((call, index) => (
          <li key={call.id} className="py-2.5">
            <div className="flex items-baseline gap-3">
              <span className="w-6 shrink-0 font-mono text-xs text-ink-faint">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="font-mono text-sm font-medium text-ink">
                {call.toolName}()
              </span>
              <span className="ml-auto shrink-0 font-mono text-xs text-ink-faint">
                {formatDateTime(call.calledAt)}
              </span>
            </div>
            <details className="mt-1 pl-9 text-xs">
              <summary className="cursor-pointer text-ink-muted">
                Arguments &amp; result
              </summary>
              <div className="mt-2 grid gap-2 pb-1 sm:grid-cols-2">
                <pre className="overflow-x-auto rounded-md bg-surface-muted p-3 font-mono text-ink-muted">
                  {JSON.stringify(call.arguments, null, 2)}
                </pre>
                <pre className="overflow-x-auto rounded-md bg-surface-muted p-3 font-mono text-ink-muted">
                  {JSON.stringify(call.result, null, 2)}
                </pre>
              </div>
            </details>
          </li>
        ))}
      </ol>
    </div>
  );
}
