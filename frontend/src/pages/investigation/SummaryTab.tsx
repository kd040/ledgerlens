import { useNavigate, useParams } from "react-router-dom";
import {
  useDuplicateSettlements,
  useInvestigation,
  useInvestigationContradictions,
  useInvestigationEvidence,
  useInvestigationHypotheses,
  useMe,
} from "../../api/queries";
import { AiInvestigationCard } from "../../components/investigation/AiInvestigationCard";
import { DuplicateSettlementsPanel } from "../../components/investigation/DuplicateSettlementsPanel";
import { ResolutionAction } from "../../components/investigation/ResolutionAction";
import { ErrorState, LoadingState } from "../../components/ui/AsyncState";
import { MoneyValue } from "../../components/ui/MoneyValue";
import { StatTile } from "../../components/ui/StatTile";
import { StatusBadge } from "../../components/ui/StatusBadge";
import type { FinancialAnalysis, Hypothesis } from "../../domain/types";
import { formatMoney, formatPercent } from "../../lib/format";
import { investigationOutcomePresentation, investigationStatusTone } from "../../lib/status";

function FormulaRow({
  label,
  value,
  operator,
}: {
  label: string;
  value: number;
  operator: "−" | "+" | "=";
}) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-4 font-mono text-sm text-ink-faint">{operator}</span>
      <span className="flex-1 text-sm text-ink-muted">{label}</span>
      <MoneyValue value={value} className="text-sm text-ink" />
    </div>
  );
}

/** Why the discrepancy exists, walked from the actual persisted
 * financial_analysis -- only rendered when the breakdown fields the
 * amount-mismatch calculation produces are actually present. */
function DiscrepancyFormula({ fa }: { fa: FinancialAnalysis }) {
  const hasBreakdown =
    fa.grossAmount !== null ||
    fa.feeAmount !== null ||
    fa.taxAmount !== null ||
    fa.adjustmentAmount !== null;

  if (!hasBreakdown) return null;

  return (
    <div className="flex flex-col gap-1.5 border-b border-border pb-4">
      {fa.grossAmount !== null && (
        <div className="flex items-baseline gap-3">
          <span className="w-4" />
          <span className="flex-1 text-sm text-ink-muted">Gross payment</span>
          <MoneyValue value={fa.grossAmount} className="text-sm text-ink" />
        </div>
      )}
      {fa.feeAmount !== null && (
        <FormulaRow label="Fees" value={fa.feeAmount} operator="−" />
      )}
      {fa.taxAmount !== null && (
        <FormulaRow label="Taxes" value={fa.taxAmount} operator="−" />
      )}
      {fa.adjustmentAmount !== null && (
        <FormulaRow label="Adjustments" value={fa.adjustmentAmount} operator="+" />
      )}
      <div className="mt-1 flex items-baseline gap-3 border-t border-border pt-1.5">
        <span className="w-4 font-mono text-sm text-ink-faint">=</span>
        <span className="flex-1 text-sm font-medium text-ink">
          Expected settlement
        </span>
        <MoneyValue
          value={fa.expectedAmount}
          className="text-sm font-medium text-ink"
        />
      </div>
    </div>
  );
}

function findSupportedHypothesis(hypotheses: Hypothesis[]): Hypothesis | null {
  return hypotheses.find((h) => h.status === "SUPPORTED") ?? null;
}

function recommendationExplanation(
  status: string,
  recommendation: string | null,
  confidence: number | null,
  humanDecision: string | null,
): string | null {
  if (humanDecision === "ESCALATED") {
    return "Escalated by human review -- see the escalation note in Evidence.";
  }
  if (humanDecision === "RESOLVED") {
    return "Resolved by human review -- see the resolution note in Evidence.";
  }
  if (status === "ESCALATED") {
    return "Conflicting evidence prevents an automatic conclusion. This case has been escalated for human review.";
  }
  if (status === "COMPLETED" && recommendation === "HUMAN_REVIEW") {
    return `LedgerLens is ${formatPercent(confidence)} confident in the identified root cause. Human approval is required before financial action is taken.`;
  }
  if (status === "COMPLETED" && recommendation === "NO_ACTION") {
    return "No financial discrepancy was identified. No action is required.";
  }
  return null;
}

export function SummaryTab() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const me = useMe();
  const investigation = useInvestigation(id);
  const evidence = useInvestigationEvidence(id);
  const hypotheses = useInvestigationHypotheses(id);
  const contradictions = useInvestigationContradictions(id);
  const duplicateSettlements = useDuplicateSettlements(
    investigation.data?.exceptionCode === "EX03"
      ? investigation.data.exceptionId
      : undefined,
  );

  if (investigation.isLoading) return <LoadingState message="Loading summary…" />;
  if (investigation.isError || !investigation.data)
    return <ErrorState message="Could not load investigation summary." />;

  const data = investigation.data;
  const fa = data.financialAnalysis;
  const supportedHypothesis = findSupportedHypothesis(hypotheses.data ?? []);
  const contradictionCount = contradictions.data?.length ?? 0;
  const explanation = recommendationExplanation(
    data.status,
    data.recommendation,
    data.confidence,
    data.humanDecision,
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
          Exception
        </div>
        <p className="mt-1 text-sm text-ink">{data.description}</p>
      </div>

      {/* LEVEL 1 -- the financial discrepancy, immediately scannable */}
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
          Financial discrepancy
        </div>
        <div className="mt-1 font-mono text-4xl font-medium tabular-nums text-ink">
          {formatMoney(data.financialImpact)}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatTile label="Expected" value={formatMoney(fa?.expectedAmount ?? null)} />
          <StatTile label="Observed" value={formatMoney(fa?.observedAmount ?? null)} />
          <StatTile label="Difference" value={formatMoney(fa?.difference ?? null)} />
        </div>
      </div>

      {/* WHY -- the discrepancy explained from real investigation data */}
      {fa && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            Why does this differ?
          </div>
          <div className="mt-3 flex flex-col gap-4">
            <DiscrepancyFormula fa={fa} />
            <div className="flex items-baseline gap-3">
              <span className="w-4" />
              <span className="flex-1 text-sm text-ink-muted">
                Observed settlement
              </span>
              <MoneyValue value={fa.observedAmount} className="text-sm text-ink" />
            </div>
            <div className="flex items-baseline gap-3 border-t border-border pt-2">
              <span className="w-4 font-mono text-sm text-danger">→</span>
              <span className="flex-1 text-sm font-medium text-ink">
                Remaining discrepancy
              </span>
              <MoneyValue
                value={fa.difference}
                className="text-sm font-semibold text-danger"
              />
            </div>
          </div>

          {supportedHypothesis && (
            <p className="mt-4 border-t border-border pt-4 text-sm text-ink-muted">
              <span className="font-medium text-ink">
                {supportedHypothesis.hypothesis}
              </span>{" "}
              {supportedHypothesis.reasoning}
            </p>
          )}

          {!supportedHypothesis && data.status !== "IN_PROGRESS" && (
            <p className="mt-4 border-t border-border pt-4 text-sm text-ink-muted">
              {contradictionCount > 0
                ? "No hypothesis could be treated as conclusive -- contradictory evidence was found. See Hypotheses for detail."
                : "No hypothesis was fully supported by the available evidence. LedgerLens does not invent an explanation when the evidence is insufficient."}
            </p>
          )}
        </div>
      )}

      {/* Root cause, confidence, recommendation -- and why both can be true */}
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
          Root cause
        </div>
        <p className="mt-1 text-base font-medium text-ink">
          {data.rootCause ?? "Not yet determined"}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-6">
          <div>
            <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
              Confidence
            </div>
            <div className="mt-0.5 font-mono text-lg font-medium tabular-nums text-ink">
              {formatPercent(data.confidence)}
            </div>
          </div>
          <div>
            <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
              Status
            </div>
            <div className="mt-1">
              <StatusBadge
                label={data.status}
                tone={investigationStatusTone(data.status)}
              />
            </div>
          </div>
          <div>
            <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
              Recommendation
            </div>
            <div className="mt-0.5 text-lg font-semibold text-accent">
              {data.recommendation ?? "—"}
            </div>
          </div>
        </div>

        {data.recommendation === "HUMAN_REVIEW" && data.humanDecision === null && id && (
          <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4">
            <p className="text-sm text-ink-muted">
              This case needs a human decision before it can be closed out.
              {me.data && me.data.role !== "reviewer" && (
                <> Only a Reviewer can resolve or escalate it.</>
              )}
            </p>
            {me.data?.role === "reviewer" ? (
              <ResolutionAction
                investigationId={id}
                evidenceCount={evidence.data?.length ?? 0}
                hypothesisCount={hypotheses.data?.length ?? 0}
                contradictionCount={contradictionCount}
              />
            ) : (
              <StatusBadge
                label="Reviewer authorization required"
                tone="accent"
                icon="🔒"
              />
            )}
          </div>
        )}

        {data.humanDecision !== null &&
          (() => {
            const presentation = investigationOutcomePresentation(
              data.status,
              data.recommendation,
              data.humanDecision,
            );
            return (
              <div className="mt-4 flex items-center gap-2 border-t border-border pt-4">
                <StatusBadge
                  label={presentation.label}
                  tone={presentation.tone}
                  icon={presentation.icon}
                />
                <span className="text-sm text-ink-muted">{presentation.caption}</span>
              </div>
            );
          })()}

        {explanation && (
          <p className="mt-4 border-t border-border pt-4 text-sm text-ink-muted">
            {explanation}
          </p>
        )}
      </div>

      {id && (
        <AiInvestigationCard
          investigationId={id}
          investigation={data}
          onViewEvidence={() => navigate(`/investigations/${id}/evidence`)}
        />
      )}

      {data.exceptionCode === "EX03" && (
        <div className="rounded-lg border border-border bg-surface p-5">
          {duplicateSettlements.isLoading && (
            <p className="text-sm text-ink-faint">Loading duplicate records…</p>
          )}
          {duplicateSettlements.isError && (
            <p className="text-sm text-danger">
              Could not load the underlying settlement records.
            </p>
          )}
          {duplicateSettlements.data && (
            <DuplicateSettlementsPanel
              payment={duplicateSettlements.data.payment}
              settlements={duplicateSettlements.data.settlements}
            />
          )}
        </div>
      )}
    </div>
  );
}
