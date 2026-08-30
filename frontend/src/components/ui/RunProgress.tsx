import { useEffect, useState } from "react";

/** The real backend pipeline for POST /reconciliation/sources/run, in
 * order -- see backend/app/datasources/router.py and *.source.py. There
 * is no server-sent progress signal, so this only advances an
 * indeterminate "current stage" pointer on a timer while the single
 * request is in flight; it never claims a stage finished before the
 * request actually resolves, and never shows a fabricated percentage. */
const STAGES = [
  "Fetching transactions",
  "Normalizing & persisting",
  "Reconciling payments",
  "Preparing results",
];

const STAGE_INTERVAL_MS = 900;

/** Mount this only while the run is actually pending -- unmounting it
 * afterwards is what resets the stage pointer for the next run, so
 * there's no state to reset inside the timer effect itself. */
export function RunProgress() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setIndex((current) => Math.min(current + 1, STAGES.length - 1));
    }, STAGE_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <ul className="flex flex-col gap-2">
        {STAGES.map((stage, i) => (
          <li key={stage} className="flex items-center gap-2 text-sm">
            {i < index ? (
              <span className="text-success" aria-hidden="true">
                ✓
              </span>
            ) : i === index ? (
              <span
                className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent"
                aria-hidden="true"
              />
            ) : (
              <span className="h-3.5 w-3.5 rounded-full border border-border" aria-hidden="true" />
            )}
            <span className={i <= index ? "text-ink" : "text-ink-faint"}>
              {stage}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
