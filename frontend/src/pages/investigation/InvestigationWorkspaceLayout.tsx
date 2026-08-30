import { useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { useInvestigation } from "../../api/queries";
import { ErrorState, LoadingState } from "../../components/ui/AsyncState";
import { Drawer } from "../../components/ui/Drawer";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { extractPaymentReference } from "../../lib/payment";
import { investigationOutcomePresentation } from "../../lib/status";
import { AuditTab } from "./AuditTab";
import { TimelineTab } from "./TimelineTab";

const TABS = [
  { label: "Summary", to: "summary" },
  { label: "Evidence", to: "evidence" },
  { label: "Hypotheses", to: "hypotheses" },
  { label: "Financials", to: "financials" },
];

export function InvestigationWorkspaceLayout() {
  const { id } = useParams<{ id: string }>();
  const investigation = useInvestigation(id);
  const [drawer, setDrawer] = useState<"timeline" | "audit" | null>(null);

  if (investigation.isLoading) {
    return <LoadingState message="Loading investigation…" />;
  }

  if (investigation.isError || !investigation.data) {
    return <ErrorState message="Investigation not found." />;
  }

  const data = investigation.data;
  const paymentReference = extractPaymentReference(data.description);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4">
        <div>
          {paymentReference && (
            <h1 className="font-mono text-xl font-medium text-ink">
              {paymentReference}
            </h1>
          )}
          <div className="mt-0.5 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
            {data.exceptionCode} · {data.category}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setDrawer("timeline")}
            className="text-xs font-medium text-ink-muted underline decoration-border underline-offset-4 hover:text-ink"
          >
            History
          </button>
          <button
            type="button"
            onClick={() => setDrawer("audit")}
            className="text-xs font-medium text-ink-muted underline decoration-border underline-offset-4 hover:text-ink"
          >
            View audit trail
          </button>
          {(() => {
            const presentation = investigationOutcomePresentation(
              data.status,
              data.recommendation,
              data.humanDecision,
            );
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

      <nav className="flex gap-1 border-b border-border">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "border-accent text-accent"
                  : "border-transparent text-ink-muted hover:text-ink"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />

      <Drawer
        open={drawer === "timeline"}
        onClose={() => setDrawer(null)}
        title="Investigation Timeline"
      >
        <TimelineTab />
      </Drawer>
      <Drawer
        open={drawer === "audit"}
        onClose={() => setDrawer(null)}
        title="Audit Trail"
      >
        <AuditTab />
      </Drawer>
    </div>
  );
}
