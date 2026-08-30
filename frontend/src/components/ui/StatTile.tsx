import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: ReactNode;
  hint?: string;
  /** When set, the tile renders as a button (hover/focus affordance)
   * instead of a static card -- used for tiles that open a drill-down. */
  onClick?: () => void;
}

export function StatTile({ label, value, hint, onClick }: StatTileProps) {
  const content = (
    <>
      <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
        {label}
      </div>
      <div className="mt-1 break-words font-mono text-2xl font-medium tabular-nums text-ink">
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-ink-muted">{hint}</div>}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="rounded-lg border border-border bg-surface p-4 text-left transition-colors hover:border-accent hover:bg-accent-muted"
      >
        {content}
      </button>
    );
  }

  return <div className="rounded-lg border border-border bg-surface p-4">{content}</div>;
}
