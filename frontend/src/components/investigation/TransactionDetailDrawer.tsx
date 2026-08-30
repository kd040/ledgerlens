import { useNavigate } from "react-router-dom";
import { useDuplicateSettlements, useStartInvestigation } from "../../api/queries";
import { Drawer } from "../ui/Drawer";
import { StatusBadge } from "../ui/StatusBadge";
import { formatMoney } from "../../lib/format";
import { reconciliationStatusPresentation } from "../../lib/status";
import type { ExceptionRecord, ReconciliationResult } from "../../domain/types";
import { DuplicateSettlementsPanel } from "./DuplicateSettlementsPanel";

interface TransactionDetailDrawerProps {
  open: boolean;
  onClose: () => void;
  result: ReconciliationResult | null;
  exceptionByPayment: Map<string, ExceptionRecord>;
}

/**
 * The single "Transaction Detail" drawer for a reconciliation result row
 * -- used by the Reconciliation results table and, via the Overview
 * Financial Gap breakdown's transaction drill-down, by Overview too.
 * One drawer, reused, rather than a second detail system per page.
 */
export function TransactionDetailDrawer({
  open,
  onClose,
  result,
  exceptionByPayment,
}: TransactionDetailDrawerProps) {
  const navigate = useNavigate();
  const startInvestigation = useStartInvestigation();
  const matchedException = result ? exceptionByPayment.get(result.payment) : undefined;
  const duplicateSettlements = useDuplicateSettlements(
    result?.status === "EX03" ? matchedException?.id : undefined,
  );

  return (
    <Drawer open={open} onClose={onClose} title="Transaction Detail">
      {result && (
        <div className="flex flex-col gap-4">
          <div>
            <div className="font-mono text-xl font-medium text-ink">{result.payment}</div>
            <div className="mt-1">
              {(() => {
                const presentation = reconciliationStatusPresentation(result.status);
                return (
                  <StatusBadge
                    label={presentation.label}
                    tone={presentation.tone}
                    icon={presentation.icon}
                  />
                );
              })()}
            </div>
          </div>

          <div className="flex flex-col gap-2 border-t border-border pt-4">
            {result.category && (
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Category</span>
                <span className="text-ink">{result.category}</span>
              </div>
            )}
            {result.grossAmount !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Gross</span>
                <span className="font-mono text-ink">{formatMoney(result.grossAmount)}</span>
              </div>
            )}
            {result.expectedAmount !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Expected</span>
                <span className="font-mono text-ink">{formatMoney(result.expectedAmount)}</span>
              </div>
            )}
            {result.observedAmount !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Observed</span>
                <span className="font-mono text-ink">{formatMoney(result.observedAmount)}</span>
              </div>
            )}
            {result.difference !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Difference</span>
                <span className="font-mono text-ink">{formatMoney(result.difference)}</span>
              </div>
            )}
            {result.settlementCount !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">Settlement records</span>
                <span className="font-mono text-ink">{result.settlementCount} detected</span>
              </div>
            )}
          </div>

          {result.status === "EX03" && (
            <div className="border-t border-border pt-4">
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

          <div className="border-t border-border pt-4">
            {result.status === "RECONCILED" && (
              <p className="text-sm text-ink-muted">
                Resolved -- expected and observed amounts match, no discrepancy found for
                this payment.
              </p>
            )}
            {result.status === "SETTLEMENT_PENDING" && (
              <p className="text-sm text-ink-muted">
                Settlement is not yet available and remains within the expected settlement
                window. This is normal lag, not a missing record.
              </p>
            )}
            {result.status !== "RECONCILED" &&
              result.status !== "SETTLEMENT_PENDING" &&
              matchedException?.investigationId && (
                <button
                  type="button"
                  onClick={() =>
                    navigate(`/investigations/${matchedException.investigationId}/summary`)
                  }
                  className="w-full rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-white hover:opacity-90"
                >
                  View Investigation
                </button>
              )}
            {result.status !== "RECONCILED" &&
              result.status !== "SETTLEMENT_PENDING" &&
              matchedException &&
              !matchedException.investigationId && (
                <button
                  type="button"
                  disabled={startInvestigation.isPending}
                  onClick={() =>
                    startInvestigation.mutate(matchedException.id, {
                      onSuccess: (result) =>
                        navigate(`/investigations/${result.investigation_id}/summary`),
                    })
                  }
                  className="w-full rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {startInvestigation.isPending ? "Starting…" : "Start Investigation"}
                </button>
              )}
            {result.status !== "RECONCILED" &&
              result.status !== "SETTLEMENT_PENDING" &&
              !matchedException && (
                <p className="text-sm text-ink-faint">
                  No matching exception record found yet -- open the Exception Center after
                  reconciliation completes.
                </p>
              )}
          </div>
        </div>
      )}
    </Drawer>
  );
}
