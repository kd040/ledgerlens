import { useRunAiInvestigation } from "../../api/queries";
import type { InvestigationDetail } from "../../domain/types";
import { formatMoney, formatPercent } from "../../lib/format";
import { ApiError } from "../../api/client";

interface AiInvestigationCardProps {
  investigationId: string;
  investigation: InvestigationDetail;
  onViewEvidence: () => void;
}

const REAL_STAGES = [
  "Gathering evidence",
  "Checking financials",
  "Evaluating hypotheses",
  "Generating conclusion",
];

const RECOMMENDATION_LABELS: Record<string, string> = {
  NO_ACTION: "No Action",
  HUMAN_REVIEW: "Human Review",
};

/**
 * The additive AI Investigator layer -- a deeper, evidence-grounded
 * explanation on top of an already-run deterministic investigation (see
 * backend/app/ai/investigator.py). Never duplicates the Evidence/
 * Hypotheses/Financials/Timeline/Audit tabs; "View Evidence" just
 * navigates to the existing tab that already shows the AI's own
 * AI_ANALYSIS-tagged rows alongside the deterministic ones.
 */
export function AiInvestigationCard({
  investigationId,
  investigation,
  onViewEvidence,
}: AiInvestigationCardProps) {
  const runAi = useRunAiInvestigation(investigationId);

  const eligible =
    investigation.financialAnalysis !== null &&
    investigation.recommendation === "HUMAN_REVIEW";
  const hasRun = investigation.rootCauseAssessment !== null;
  const gap = investigation.financialAnalysis?.difference ?? investigation.financialImpact;

  // Once a reviewer has resolved or escalated, the shared `recommendation`
  // field may no longer hold the AI's own value (resolve overwrites it to
  // "RESOLVED"; see resolution.py's _assert_eligible_for_human_decision,
  // which requires recommendation === "HUMAN_REVIEW" before either action
  // can fire) -- so whenever a human decision exists, the AI's own
  // recommendation is known with certainty to have been "HUMAN_REVIEW",
  // regardless of what the shared field currently reads. This never shows
  // RESOLVED/ESCALATED as something the AI itself recommended.
  const aiRecommendation =
    investigation.humanDecision !== null ? "HUMAN_REVIEW" : investigation.recommendation;

  const errorMessage =
    runAi.error instanceof ApiError
      ? runAi.error.message
      : runAi.isError
        ? "The AI Investigator could not complete this analysis."
        : null;

  return (
    <div className="rounded-lg border border-accent/40 bg-surface p-5">
      <div className="flex items-center gap-2">
        <span aria-hidden="true">🧠</span>
        <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
          AI Investigation
        </div>
      </div>

      {gap !== null && (
        <p className="mt-2 text-base font-medium text-ink">
          Why is there a {formatMoney(gap)} gap?
        </p>
      )}

      {runAi.isPending && (
        <div className="mt-4 flex flex-col gap-1.5 border-t border-border pt-4">
          <div className="flex items-center gap-2 text-sm font-medium text-ink">
            <span
              aria-hidden="true"
              className="h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent"
            />
            Investigating…
          </div>
          <p className="text-xs text-ink-faint">{REAL_STAGES.join(" · ")}</p>
        </div>
      )}

      {!runAi.isPending && !hasRun && (
        <div className="mt-4 flex flex-col gap-3 border-t border-border pt-4">
          <p className="text-sm text-ink-muted">
            {eligible
              ? "Ask LedgerLens's AI Investigator to analyze this case's actual evidence and explain the gap -- grounded in the payment, settlement, fee, and tax records, never invented."
              : "AI Investigation becomes available once the deterministic engine has flagged this case for human review."}
          </p>
          {errorMessage && <p className="text-sm text-danger">{errorMessage}</p>}
          <button
            type="button"
            disabled={!eligible || runAi.isPending}
            onClick={() => runAi.mutate()}
            className="self-start rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            Run AI Investigation
          </button>
        </div>
      )}

      {!runAi.isPending && hasRun && investigation.rootCauseAssessment && (
        <div className="mt-4 flex flex-col gap-4 border-t border-border pt-4">
          <div>
            <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
              Finding
            </div>
            <p className="mt-1 text-sm text-ink">
              {investigation.rootCause ?? "No conclusive finding was reached."}
            </p>
          </div>

          <dl className="flex flex-col gap-2 text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-muted">Known</dt>
              <dd className="flex-1 text-right text-ink">
                {investigation.rootCauseAssessment.known}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-muted">Likely</dt>
              <dd className="flex-1 text-right text-ink">
                {investigation.rootCauseAssessment.likely}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-ink-muted">Not Proven</dt>
              <dd className="flex-1 text-right text-ink">
                {investigation.rootCauseAssessment.notProven}
              </dd>
            </div>
          </dl>

          <div className="flex flex-wrap items-center gap-6">
            <div>
              <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                Confidence
              </div>
              <div className="mt-0.5 font-mono text-lg font-medium tabular-nums text-ink">
                {formatPercent(investigation.confidence)}
              </div>
            </div>
            <div>
              <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                AI Recommendation
              </div>
              <div className="mt-0.5 text-lg font-semibold text-accent">
                {aiRecommendation
                  ? (RECOMMENDATION_LABELS[aiRecommendation] ?? aiRecommendation)
                  : "—"}
              </div>
            </div>
          </div>

          {investigation.humanDecision === null ? (
            <p className="text-xs font-medium text-ink-faint">
              AI recommendation — human decision required.
            </p>
          ) : (
            <div className="flex flex-col gap-2 border-t border-border pt-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-success">
                <span aria-hidden="true">✓</span> Decided by human review
              </p>
              <div>
                <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                  Human Decision
                </div>
                <div className="mt-0.5 text-lg font-semibold text-ink">
                  {investigation.humanDecision}
                </div>
              </div>
            </div>
          )}

          {errorMessage && <p className="text-sm text-danger">{errorMessage}</p>}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onViewEvidence}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-muted"
            >
              View Evidence
            </button>
            <button
              type="button"
              disabled={!eligible || runAi.isPending}
              onClick={() => runAi.mutate()}
              className="rounded-md border border-accent px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent-muted disabled:opacity-50"
            >
              Re-run AI Investigation
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
