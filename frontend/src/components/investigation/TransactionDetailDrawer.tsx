import { useNavigate } from "react-router-dom";
import { useDuplicateSettlements, useStartInvestigation } from "../../api/queries";
import { Drawer } from "../ui/Drawer";
import { StatusBadge } from "../ui/StatusBadge";
import { formatDateTime, formatMoney } from "../../lib/format";
import {
  dataSourceLabel,
  isExceptionStatus,
  reconciliationStatusPresentation,
} from "../../lib/status";
import type {
  DataSource,
  ExceptionRecord,
  ReconciliationResult,
} from "../../domain/types";
import { DuplicateSettlementsPanel } from "./DuplicateSettlementsPanel";

interface TransactionDetailDrawerProps {
  open: boolean;
  onClose: () => void;
  result: ReconciliationResult | null;
  exceptionByPayment: Map<string, ExceptionRecord>;
  /** The source the run that produced this row came from -- a row is
   * always from the run that fetched it (each source scopes
   * reconciliation to its own payment ids), so this names the row's
   * origin without guessing at the payment id's shape. */
  source: DataSource;
}

/** One label/value line. Values that are identifiers, amounts, or
 * timestamps render monospaced so columns of them stay scannable. */
function DetailRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="shrink-0 text-ink-muted">{label}</span>
      <span className={`text-right text-ink ${mono ? "font-mono" : ""}`}>
        {value}
      </span>
    </div>
  );
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
  source,
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

          {/* Identity: who/when/where this payment came from, before any
              reconciliation arithmetic. A Razorpay row is only
              recognisable as one if the id, the real capture timestamp,
              and the source are all stated. */}
          <div className="flex flex-col gap-2 border-t border-border pt-4">
            {/* The payment id is already the drawer's heading above --
                not repeated here. */}
            <DetailRow
              label="Payment date"
              value={
                result.paymentCreatedAt
                  ? formatDateTime(result.paymentCreatedAt)
                  : "—"
              }
              mono={result.paymentCreatedAt !== null}
            />
            <DetailRow label="Source" value={dataSourceLabel(source)} />
            {result.grossAmount !== null && (
              <DetailRow
                label="Amount"
                value={formatMoney(result.grossAmount)}
                mono
              />
            )}
            {result.paymentStatus && (
              <DetailRow
                label="Payment status"
                value={
                  <span className="font-mono uppercase">
                    {result.paymentStatus}
                  </span>
                }
              />
            )}
            {/* The settlement status is the badge under the heading
                above -- not repeated as a row. `category` is only shown
                when it says something the badge does not. */}
            {result.category &&
              result.category !==
                reconciliationStatusPresentation(result.status).label && (
                <DetailRow label="Category" value={result.category} />
              )}
          </div>

          {/* Settlement arithmetic only exists once a settlement does --
              a pending or never-captured payment has none of it, and an
              empty bordered block would read as a rendering fault. */}
          {(result.expectedAmount !== null ||
            result.observedAmount !== null ||
            result.difference !== null ||
            result.settlementCount !== null) && (
            <div className="flex flex-col gap-2 border-t border-border pt-4">
              {result.expectedAmount !== null && (
                <DetailRow
                  label="Expected"
                  value={formatMoney(result.expectedAmount)}
                  mono
                />
              )}
              {result.observedAmount !== null && (
                <DetailRow
                  label="Observed"
                  value={formatMoney(result.observedAmount)}
                  mono
                />
              )}
              {result.difference !== null && (
                <DetailRow
                  label="Difference"
                  value={formatMoney(result.difference)}
                  mono
                />
              )}
              {result.settlementCount !== null && (
                <DetailRow
                  label="Settlement records"
                  value={`${result.settlementCount} detected`}
                  mono
                />
              )}
            </div>
          )}

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
            {result.status === "NOT_CAPTURED" && (
              <p className="text-sm text-ink-muted">
                This payment was never captured, so no settlement is owed for
                it. Not a financial exception, and nothing to investigate.
              </p>
            )}
            {/* Only a genuine EX01/EX02/EX03 row has an exception record
                behind it, so only those can enter the investigation
                workflow -- see isExceptionStatus. */}
            {isExceptionStatus(result.status) &&
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
            {isExceptionStatus(result.status) &&
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
            {isExceptionStatus(result.status) && !matchedException && (
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
