import { useState } from "react";
import { useParams } from "react-router-dom";
import { useInvestigationDailyFinancials } from "../../api/queries";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/AsyncState";
import { MoneyValue } from "../../components/ui/MoneyValue";
import { formatDate } from "../../lib/format";

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2.5 last:border-b-0">
      <span className="text-sm text-ink-muted">{label}</span>
      <MoneyValue value={value} className="text-sm font-medium text-ink" />
    </div>
  );
}

/** Day navigation across this investigation's OWN real settlement
 * dates -- never a fabricated calendar and never another payment's
 * data. Most investigations have exactly one settlement date (one
 * day); an EX03 duplicate has one date per duplicate settlement. */
export function FinancialsTab() {
  const { id } = useParams<{ id: string }>();
  const [dateOverride, setDateOverride] = useState<string | undefined>(undefined);
  const daily = useInvestigationDailyFinancials(id, dateOverride);

  if (daily.isLoading) return <LoadingState message="Loading financials…" />;
  if (daily.isError || !daily.data) {
    return <ErrorState message="Could not load financial analysis." />;
  }

  const { availableDates, selectedDate, financials } = daily.data;

  if (availableDates.length === 0 || !financials || !selectedDate) {
    return (
      <EmptyState message="No settlement records exist yet for this payment -- there is nothing to show day-by-day." />
    );
  }

  const index = availableDates.indexOf(selectedDate);
  const hasPrev = index > 0;
  const hasNext = index >= 0 && index < availableDates.length - 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-3">
        <button
          type="button"
          disabled={!hasPrev}
          onClick={() => setDateOverride(availableDates[index - 1])}
          className="rounded-md border border-border px-2.5 py-1.5 text-sm text-ink hover:bg-surface-muted disabled:opacity-40"
        >
          ← Previous Day
        </button>

        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-medium text-ink">
            {formatDate(new Date(`${selectedDate}T00:00:00Z`))}
          </span>
          {availableDates.length > 1 && (
            <select
              value={selectedDate}
              onChange={(event) => setDateOverride(event.target.value)}
              className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink"
            >
              {availableDates.map((date) => (
                <option key={date} value={date}>
                  {date}
                </option>
              ))}
            </select>
          )}
        </div>

        <button
          type="button"
          disabled={!hasNext}
          onClick={() => setDateOverride(availableDates[index + 1])}
          className="rounded-md border border-border px-2.5 py-1.5 text-sm text-ink hover:bg-surface-muted disabled:opacity-40"
        >
          Next Day →
        </button>
      </div>

      <div className="rounded-lg border border-border bg-surface p-5">
        <Row label="Gross amount" value={financials.grossAmount} />
        <Row label="Fees" value={financials.feeAmount} />
        <Row label="GST / Tax" value={financials.taxAmount} />
        <Row label="Adjustments" value={financials.adjustmentAmount} />
        <Row label="Expected settlement amount" value={financials.expectedAmount} />
        <Row label="Observed settlement amount" value={financials.observedAmount} />
        {financials.settlementCount > 1 && (
          <div className="flex items-center justify-between border-b border-border py-2.5 last:border-b-0">
            <span className="text-sm text-ink-muted">Settlement records this day</span>
            <span className="text-sm font-medium text-ink">{financials.settlementCount}</span>
          </div>
        )}
        <div className="flex items-center justify-between pt-3">
          <span className="text-sm font-semibold text-ink">Difference</span>
          <MoneyValue value={financials.difference} className="text-base font-semibold text-ink" />
        </div>
      </div>

      {availableDates.length > 1 && (
        <p className="text-xs text-ink-faint">
          This payment has settlement activity on {availableDates.length} distinct
          dates -- use Previous/Next Day to review each one, and the total across
          all of them together explains the overall gap.
        </p>
      )}
    </div>
  );
}
