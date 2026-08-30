import { formatDateTime, formatMoney } from "../../lib/format";
import type { SettlementRecord } from "../../domain/types";

interface DuplicateSettlementsPanelProps {
  payment: string;
  settlements: SettlementRecord[];
}

interface FieldRow {
  label: string;
  render: (settlement: SettlementRecord) => string;
}

/** Real settlement fields only -- no UTR or anything else the schema
 * doesn't actually persist (see backend/app/investigation/tools/settlements.py). */
const FIELDS: FieldRow[] = [
  { label: "Settlement ID", render: (s) => s.externalSettlementId },
  { label: "Amount", render: (s) => formatMoney(s.settlementAmount) },
  { label: "Currency", render: (s) => s.currency },
  { label: "Status", render: (s) => s.status },
  { label: "Settlement date", render: (s) => formatDateTime(s.settlementDate) },
  { label: "Reference", render: (s) => s.reference },
];

function recordLabel(index: number): string {
  return String.fromCharCode(65 + index); // A, B, C, ...
}

/**
 * Shows every settlement record behind an EX03 exception, individually
 * and side by side -- not hardcoded to two, works for 3+ duplicates.
 * Reused wherever an EX03 result surfaces (reconciliation drawer,
 * investigation summary) so there's one duplicate-comparison UI, not two.
 */
export function DuplicateSettlementsPanel({
  payment,
  settlements,
}: DuplicateSettlementsPanelProps) {
  if (settlements.length === 0) {
    return (
      <p className="text-sm text-ink-faint">
        No underlying settlement records were found for this payment.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
          Duplicate records
        </div>
        <p className="mt-1 text-sm text-ink">
          <span aria-hidden="true">🟣</span>{" "}
          {settlements.length} settlement record{settlements.length === 1 ? "" : "s"} detected
          for payment <span className="font-mono">{payment}</span>
        </p>
      </div>

      {/* Individual records -- the mobile-friendly, stacked view. */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {settlements.map((settlement, index) => (
          <div
            key={settlement.id}
            className="rounded-lg border border-border bg-surface p-4"
          >
            <div className="mb-2 text-sm font-semibold text-ink">
              Settlement Record {recordLabel(index)}
            </div>
            <dl className="flex flex-col gap-1.5">
              {FIELDS.map((field) => (
                <div key={field.label} className="flex justify-between gap-3 text-sm">
                  <dt className="text-ink-muted">{field.label}</dt>
                  <dd className="text-right font-mono text-ink">
                    {field.render(settlement)}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>

      {/* Comparison table -- field-by-field, with an explicit
          match/difference indicator so nothing relies on color alone. */}
      {settlements.length > 1 && (
        <div>
          <div className="mb-2 text-sm font-semibold text-ink">Comparison</div>
          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full min-w-max text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-muted">
                  <th className="px-4 py-2.5 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                    Field
                  </th>
                  {settlements.map((_, index) => (
                    <th
                      key={index}
                      className="px-4 py-2.5 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint"
                    >
                      Record {recordLabel(index)}
                    </th>
                  ))}
                  <th className="px-4 py-2.5 font-mono text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                    Result
                  </th>
                </tr>
              </thead>
              <tbody>
                {FIELDS.map((field) => {
                  const values = settlements.map((s) => field.render(s));
                  const allMatch = values.every((v) => v === values[0]);
                  return (
                    <tr key={field.label} className="border-b border-border last:border-b-0">
                      <td className="px-4 py-3 font-medium text-ink">{field.label}</td>
                      {values.map((value, index) => (
                        <td key={index} className="px-4 py-3 font-mono text-ink">
                          {value}
                        </td>
                      ))}
                      <td className="px-4 py-3">
                        {allMatch ? (
                          <span className="inline-flex items-center gap-1 text-success">
                            <span aria-hidden="true">✓</span> Match
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 font-medium text-warning">
                            <span aria-hidden="true">⚠</span> Different
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
