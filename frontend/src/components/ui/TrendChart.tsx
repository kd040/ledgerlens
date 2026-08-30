import { formatMoney } from "../../lib/format";

export interface TrendPoint {
  label: string;
  value: number;
  /** Opaque key (e.g. an ISO date) handed back to `onPointClick` -- lets
   * a caller identify which point was selected without re-deriving it
   * from the label text. */
  key?: string;
}

interface TrendChartProps {
  points: TrendPoint[];
  /** When set, each bar becomes a button and the selected point (if its
   * key matches `selectedKey`) is drawn distinctly -- used for drilling
   * a multi-day range down into one day. When omitted, bars render as
   * plain (non-interactive) trend data, same as before. */
  onPointClick?: (point: TrendPoint) => void;
  selectedKey?: string;
  /** Format the hover/selection value as money (default) or a plain
   * count, e.g. for a daily transaction-count trend. */
  valueFormat?: "money" | "count";
}

/** A minimal day-by-day bar trend -- only meaningful once a period
 * spans more than one calendar day. */
export function TrendChart({
  points,
  onPointClick,
  selectedKey,
  valueFormat = "money",
}: TrendChartProps) {
  const max = Math.max(...points.map((point) => point.value), 1);
  const formatValue = (value: number) =>
    valueFormat === "money" ? formatMoney(value) : String(value);

  return (
    <div className="flex h-32 items-end gap-2">
      {points.map((point) => {
        const selected = onPointClick && point.key !== undefined && point.key === selectedKey;
        return (
          <div
            key={point.key ?? point.label}
            role={onPointClick ? "button" : undefined}
            tabIndex={onPointClick ? 0 : undefined}
            onClick={onPointClick ? () => onPointClick(point) : undefined}
            onKeyDown={
              onPointClick
                ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onPointClick(point);
                    }
                  }
                : undefined
            }
            className={`group relative flex flex-1 flex-col items-center gap-1.5 ${
              onPointClick ? "cursor-pointer" : ""
            }`}
          >
            <div className="pointer-events-none absolute -top-6 hidden whitespace-nowrap rounded-md bg-ink px-1.5 py-0.5 font-mono text-[10px] text-white group-hover:block">
              {formatValue(point.value)}
            </div>
            {/* A fixed-height track so the bar's percentage height has a
                definite containing block to resolve against -- inside an
                `items-end` flex item (auto height), a bare `height: X%`
                bar silently collapses to 0 instead of scaling. */}
            <div className="flex h-24 w-full items-end">
              <div
                className={`w-full min-w-[6px] rounded-t-sm ${selected ? "bg-accent" : onPointClick ? "bg-accent/50 group-hover:bg-accent" : "bg-accent"}`}
                style={{ height: `${Math.max((point.value / max) * 100, 2)}%` }}
              />
            </div>
            <span className={`text-[9px] ${selected ? "font-semibold text-ink" : "text-ink-faint"}`}>
              {point.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
