import type { StatusTone } from "../../lib/status";
import { toneClassName } from "../../lib/status";

interface StatusBadgeProps {
  label: string;
  tone: StatusTone;
  /** An emoji status dot shown before the label. Color is never the
   * only signal, so `icon` supplements the text label -- it never
   * replaces it. */
  icon?: string;
}

/**
 * Rendered as an ink stamp, not a soft pill: SUPPORTED / REJECTED /
 * ESCALATED are verdicts on the investigation, not decorative tags.
 */
export function StatusBadge({ label, tone, icon }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[3px] border px-1.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wider ${toneClassName(tone)}`}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {label.replaceAll("_", " ")}
    </span>
  );
}
