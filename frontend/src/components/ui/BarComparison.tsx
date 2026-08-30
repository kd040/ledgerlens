import { formatMoney } from "../../lib/format";

export interface BarComparisonItem {
  label: string;
  value: number;
  color: string;
}

/** A labeled horizontal-bar comparison of independent totals -- used
 * where a donut (which implies parts of one whole) would misrepresent
 * the relationship, e.g. expected vs. observed settlement. */
export function BarComparison({ items }: { items: BarComparisonItem[] }) {
  const max = Math.max(...items.map((item) => Math.abs(item.value)), 1);

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => (
        <div key={item.label}>
          <div className="flex items-baseline justify-between text-xs">
            <span className="text-ink-muted">{item.label}</span>
            <span className="font-mono tabular-nums text-ink">
              {formatMoney(item.value)}
            </span>
          </div>
          <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(Math.abs(item.value) / max) * 100}%`,
                background: item.color,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
