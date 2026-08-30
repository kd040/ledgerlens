import { useState } from "react";
import { useEscalateInvestigation, useResolveInvestigation } from "../../api/queries";
import { Drawer } from "../ui/Drawer";

interface ResolutionActionProps {
  investigationId: string;
  evidenceCount: number;
  hypothesisCount: number;
  contradictionCount: number;
}

/**
 * Human-in-the-loop close-out for a HUMAN_REVIEW recommendation. The
 * automated engine never marks a financially-discrepant case resolved
 * or escalated on its own (see backend/app/investigation/services/
 * completion.py) -- this is the one place a reviewer does, and both
 * actions always require a note. The reviewer reviews evidence/
 * hypotheses/financials on the existing tabs (not duplicated here);
 * this only records the final decision. Reviewer-only server-side (see
 * app/auth/dependencies.py's require_reviewer) -- the caller only
 * renders this component for a reviewer in the first place.
 */
export function ResolutionAction({
  investigationId,
  evidenceCount,
  hypothesisCount,
  contradictionCount,
}: ResolutionActionProps) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const resolve = useResolveInvestigation(investigationId);
  const escalate = useEscalateInvestigation(investigationId);

  const pending = resolve.isPending || escalate.isPending;
  const error = resolve.isError
    ? resolve.error
    : escalate.isError
      ? escalate.error
      : null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md border border-accent px-3.5 py-2 text-sm font-medium text-accent hover:bg-accent-muted"
      >
        Review &amp; Decide
      </button>

      <Drawer open={open} onClose={() => setOpen(false)} title="Review & Decide">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-ink-muted">
            This investigation was recommended for human review. Confirm
            you have reviewed the evidence, hypotheses, contradictions,
            and financial analysis (see the other tabs), then record
            your decision below.
          </p>

          <ul className="flex flex-col gap-1 rounded-md border border-border bg-surface-muted p-3 text-sm text-ink">
            <li>{evidenceCount} evidence record(s) -- Evidence tab</li>
            <li>{hypothesisCount} hypothesis/hypotheses evaluated -- Hypotheses tab</li>
            <li>{contradictionCount} contradiction(s) -- Hypotheses tab</li>
          </ul>

          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink">Note (required)</span>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={4}
              placeholder="What did you confirm, and why?"
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink"
            />
          </label>

          {error && (
            <p className="text-sm text-danger">
              {error instanceof Error
                ? error.message
                : "Could not record this decision."}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              disabled={note.trim().length === 0 || pending}
              onClick={() =>
                resolve.mutate(note, { onSuccess: () => setOpen(false) })
              }
              className="flex-1 rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {resolve.isPending ? "Resolving…" : "Mark Resolved"}
            </button>
            <button
              type="button"
              disabled={note.trim().length === 0 || pending}
              onClick={() =>
                escalate.mutate(note, { onSuccess: () => setOpen(false) })
              }
              className="flex-1 rounded-md border border-danger px-3.5 py-2 text-sm font-medium text-danger hover:bg-danger-muted disabled:opacity-50"
            >
              {escalate.isPending ? "Escalating…" : "Escalate"}
            </button>
          </div>
        </div>
      </Drawer>
    </>
  );
}
