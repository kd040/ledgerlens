import { formatMoney } from "../../lib/format";

export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

interface DonutChartProps {
  segments: DonutSegment[];
  centerLabel: string;
  /** "count" (default) for whole-number tallies like record counts;
   * "money" formats the center total and each legend value as currency
   * -- segment values are real rupee amounts (fees/tax/adjustments),
   * not counts, and float sums like 22.959999999999997 must never
   * reach the screen unformatted. */
  valueFormat?: "count" | "money";
}

/** A compact donut built from a CSS conic-gradient -- no charting
 * library needed for three or four proportions. Segments must already
 * sum to the total the chart represents (callers own that invariant so
 * the drawn proportions are never misleading). */
export function DonutChart({ segments, centerLabel, valueFormat = "count" }: DonutChartProps) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  const formatValue = (value: number) =>
    valueFormat === "money" ? formatMoney(value) : String(value);

  let cumulative = 0;
  const stops = segments
    .filter((segment) => segment.value > 0)
    .map((segment) => {
      const start = (cumulative / total) * 360;
      cumulative += segment.value;
      const end = (cumulative / total) * 360;
      return `${segment.color} ${start}deg ${end}deg`;
    });

  const background =
    total === 0
      ? "var(--color-border)"
      : `conic-gradient(${stops.join(", ")})`;

  return (
    <div className="flex items-center gap-4">
      <div className="relative h-28 w-28 shrink-0 rounded-full" style={{ background }}>
        <div
          className="absolute inset-3 flex flex-col items-center justify-center rounded-full bg-surface px-1 text-center"
        >
          <span
            className={`font-mono font-semibold tabular-nums text-ink ${
              valueFormat === "money" ? "text-sm" : "text-xl"
            }`}
          >
            {formatValue(total)}
          </span>
          <span className="text-[10px] text-ink-faint">{centerLabel}</span>
        </div>
      </div>
      <ul className="flex flex-col gap-1.5">
        {segments.map((segment) => (
          <li key={segment.label} className="flex items-center gap-2 text-xs">
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: segment.color }}
            />
            <span className="text-ink-muted">{segment.label}</span>
            <span className="ml-auto font-mono tabular-nums text-ink">
              {formatValue(segment.value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
