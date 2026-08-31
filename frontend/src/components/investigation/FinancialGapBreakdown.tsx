import { useState } from "react";
import { Drawer } from "../ui/Drawer";
import { TransactionDetailDrawer } from "./TransactionDetailDrawer";
import { formatMoney } from "../../lib/format";
import { exceptionCodeLabel } from "../../lib/status";
import {
  resultsForCategory,
  type CategoryFinancialImpact,
  type ExceptionCode,
} from "../../lib/reconciliationMetrics";
import type {
  DataSource,
  ExceptionRecord,
  ReconciliationResult,
} from "../../domain/types";

interface FinancialGapBreakdownProps {
  open: boolean;
  onClose: () => void;
  periodLabel: string;
  total: number;
  categories: CategoryFinancialImpact[];
  results: ReconciliationResult[];
  exceptionByPayment: Map<string, ExceptionRecord>;
  /** Forwarded to the transaction drawer so a drilled-into row names the
   * source it came from. */
  source: DataSource;
}

/**
 * "Where did this gap come from?" -- a category-level breakdown of the
 * period's financial impact, drilling into the individual transactions
 * behind each category. Transaction rows open the same
 * TransactionDetailDrawer the Reconciliation results table uses, so
 * there's one detail/investigation entry point, not two.
 */
export function FinancialGapBreakdown({
  open,
  onClose,
  periodLabel,
  total,
  categories,
  results,
  exceptionByPayment,
  source,
}: FinancialGapBreakdownProps) {
  const [drilled, setDrilled] = useState<ExceptionCode | null>(null);
  const [selectedTransaction, setSelectedTransaction] = useState<ReconciliationResult | null>(
    null,
  );

  const transactions = drilled ? resultsForCategory(results, exceptionByPayment, drilled) : [];

  function handleClose() {
    setDrilled(null);
    onClose();
  }

  return (
    <>
      <Drawer open={open} onClose={handleClose} title="Financial Impact Breakdown">
        <div className="flex flex-col gap-4">
          <div>
            <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
              {periodLabel}
            </div>
            <div className="mt-1 font-mono text-3xl font-medium tabular-nums text-ink">
              {formatMoney(total)}
            </div>
          </div>

          {!drilled && (
            <div className="flex flex-col gap-2 border-t border-border pt-4">
              {categories.map((category) => (
                <button
                  key={category.code}
                  type="button"
                  onClick={() => setDrilled(category.code)}
                  disabled={category.count === 0}
                  className="flex items-center justify-between rounded-md border border-border px-3.5 py-3 text-left hover:bg-surface-muted disabled:cursor-default disabled:opacity-50 disabled:hover:bg-transparent"
                >
                  <div>
                    <div className="text-sm font-medium text-ink">
                      {exceptionCodeLabel(category.code)}
                    </div>
                    <div className="text-xs text-ink-faint">
                      {category.count} transaction{category.count === 1 ? "" : "s"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium text-ink">
                      {formatMoney(category.amount)}
                    </span>
                    {category.count > 0 && (
                      <span className="text-ink-faint" aria-hidden="true">
                        →
                      </span>
                    )}
                  </div>
                </button>
              ))}
              <div className="flex items-center justify-between border-t border-border pt-3 text-sm">
                <span className="font-medium text-ink">Total</span>
                <span className="font-mono font-semibold text-ink">{formatMoney(total)}</span>
              </div>
            </div>
          )}

          {drilled && (
            <div className="flex flex-col gap-2 border-t border-border pt-4">
              <button
                type="button"
                onClick={() => setDrilled(null)}
                className="w-fit text-xs font-medium text-accent hover:underline"
              >
                ← Back to breakdown
              </button>
              <div className="text-sm font-medium text-ink">{exceptionCodeLabel(drilled)}</div>
              {transactions.length === 0 ? (
                <p className="text-sm text-ink-faint">
                  No transactions in this category for the selected period.
                </p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {transactions.map(({ result, financialImpact }) => (
                    <li key={result.payment}>
                      <button
                        type="button"
                        onClick={() => setSelectedTransaction(result)}
                        className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left hover:bg-surface-muted"
                      >
                        <span className="font-mono text-sm text-ink">{result.payment}</span>
                        <span className="font-mono text-sm text-ink">
                          {formatMoney(financialImpact)} gap
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </Drawer>

      <TransactionDetailDrawer
        open={selectedTransaction !== null}
        onClose={() => setSelectedTransaction(null)}
        result={selectedTransaction}
        exceptionByPayment={exceptionByPayment}
        source={source}
      />
    </>
  );
}
