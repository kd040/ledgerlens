export type StatusTone =
  | "success"
  | "warning"
  | "danger"
  | "missing"
  | "duplicate"
  | "accent"
  | "neutral";

const toneClasses: Record<StatusTone, string> = {
  success: "border-success text-success",
  warning: "border-warning text-warning",
  danger: "border-danger text-danger",
  missing: "border-missing text-missing",
  duplicate: "border-duplicate text-duplicate",
  accent: "border-accent text-accent",
  neutral: "border-ink-faint text-ink-muted",
};

export function toneClassName(tone: StatusTone): string {
  return toneClasses[tone];
}

export function investigationStatusTone(status: string): StatusTone {
  switch (status) {
    case "COMPLETED":
      return "success";
    case "ESCALATED":
      return "danger";
    case "IN_PROGRESS":
      return "warning";
    default:
      return "neutral";
  }
}

export function hypothesisStatusTone(status: string): StatusTone {
  switch (status) {
    case "SUPPORTED":
      return "success";
    case "REJECTED":
      return "neutral";
    case "INSUFFICIENT_EVIDENCE":
      return "warning";
    default:
      return "neutral";
  }
}

/** The three exception codes the engine ever produces, in human terms --
 * shared by the Exception Center, the reconciliation results table, and
 * the Exception Breakdown chart so the label never drifts between them. */
export const EXCEPTION_CODE_LABELS: Record<string, string> = {
  EX01: "Amount Mismatch",
  EX02: "Missing Record",
  EX03: "Duplicate Record",
};

export function exceptionCodeLabel(code: string): string {
  const category = EXCEPTION_CODE_LABELS[code];
  return category ? `${code} · ${category}` : code;
}

export interface StatusPresentation {
  icon: string;
  label: string;
  tone: StatusTone;
}

/** The explicit, always-text+color+icon status model for one
 * reconciliation result row. Color is never the only signal -- every
 * caller renders `icon label`, never a bare colored dot. */
export function reconciliationStatusPresentation(
  status: string,
): StatusPresentation {
  switch (status) {
    case "RECONCILED":
      return { icon: "🟢", label: "Resolved", tone: "success" };
    case "SETTLEMENT_PENDING":
      return { icon: "🟡", label: "Settlement Pending", tone: "warning" };
    case "EX01":
      return { icon: "🔴", label: "Amount Mismatch", tone: "danger" };
    case "EX02":
      return { icon: "🟠", label: "Missing Record", tone: "missing" };
    case "EX03":
      return { icon: "🟣", label: "Duplicate Record", tone: "duplicate" };
    default:
      return { icon: "⚪", label: status, tone: "neutral" };
  }
}

/** Kept for the few places (e.g. drawer status badges) that still want
 * the raw reconciliation status tone without the full presentation. */
export function reconciliationStatusTone(status: string): StatusTone {
  return reconciliationStatusPresentation(status).tone;
}

/**
 * The investigation's outcome, in the same explicit icon+label+tone
 * shape. Never invents a backend value: ESCALATED/COMPLETED/IN_PROGRESS
 * and the recommendation (HUMAN_REVIEW/RESOLVED/NO_ACTION) are exactly
 * what's stored -- this only picks which combination to foreground.
 * `caption` names the specific reason, since "Resolved" alone doesn't
 * distinguish an auto-resolved zero-difference case from one a human
 * closed out.
 */
export function investigationOutcomePresentation(
  status: string,
  recommendation: string | null,
  humanDecision: string | null = null,
): StatusPresentation & { caption: string } {
  if (status === "ESCALATED" && humanDecision === "ESCALATED") {
    return {
      icon: "🔴",
      label: "Escalated",
      tone: "danger",
      caption: "Escalated by human review",
    };
  }
  if (status === "ESCALATED") {
    return {
      icon: "🔴",
      label: "Escalated",
      tone: "danger",
      caption: "Escalated for human review",
    };
  }
  if (recommendation === "RESOLVED") {
    return {
      icon: "🟢",
      label: "Resolved",
      tone: "success",
      caption: "Resolved by human review",
    };
  }
  if (recommendation === "HUMAN_REVIEW") {
    return {
      icon: "🔵",
      label: "Human Review",
      tone: "accent",
      caption: "Awaiting human review",
    };
  }
  if (status === "COMPLETED" && recommendation === "NO_ACTION") {
    return {
      icon: "🟢",
      label: "Resolved",
      tone: "success",
      caption: "No discrepancy found -- no action required",
    };
  }
  return {
    icon: "⚪",
    label: "In Progress",
    tone: "neutral",
    caption: "Investigation in progress",
  };
}

/**
 * Investigation lifecycle status -- ONE concept, independent of
 * recommendation and of exception category. "Not Started" is a real
 * state (no investigation row exists yet), not an invented one.
 */
export type InvestigationLifecycleFilter =
  | "not_started"
  | "in_progress"
  | "completed"
  | "escalated";

export const INVESTIGATION_LIFECYCLE_LABELS: Record<
  InvestigationLifecycleFilter,
  string
> = {
  not_started: "Not Started",
  in_progress: "In Progress",
  completed: "Completed / Resolved",
  escalated: "Escalated",
};

export function investigationLifecycleFilter(
  investigationStatus: string | null,
): InvestigationLifecycleFilter {
  if (investigationStatus === null) return "not_started";
  if (investigationStatus === "IN_PROGRESS") return "in_progress";
  if (investigationStatus === "ESCALATED") return "escalated";
  return "completed";
}

/**
 * Recommendation -- a SEPARATE concept from lifecycle status. Only
 * meaningful once an investigation has actually concluded; a row with
 * no recommendation yet (still open/in progress) is `null` and only
 * matches the "All" filter.
 */
export type RecommendationFilter = "human_review" | "resolved" | "no_action";

export const RECOMMENDATION_LABELS: Record<RecommendationFilter, string> = {
  human_review: "Human Review",
  resolved: "Resolved",
  no_action: "No Action",
};

export function recommendationFilter(
  recommendation: string | null,
): RecommendationFilter | null {
  switch (recommendation) {
    case "HUMAN_REVIEW":
      return "human_review";
    case "RESOLVED":
      return "resolved";
    case "NO_ACTION":
      return "no_action";
    default:
      return null;
  }
}
