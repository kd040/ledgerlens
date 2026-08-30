import { useEffect, useRef, useState } from "react";
import { reconciliationApi } from "../api/reconciliation";
import { normalizeRunSourceResponse } from "../domain/normalize";
import type { ReconciliationRunSummary } from "../domain/types";

const LOOKBACK_MS = 10 * 60 * 1000;

interface LiveSyncData {
  lastSyncAt: Date | null;
  lastNewCount: number;
  latestSummary: ReconciliationRunSummary | null;
  error: string | null;
}

/** "Live Test Mode Sync": Razorpay's APIs are request-based, not a real
 * event stream, so this is honestly a poll -- it reuses the existing
 * idempotent /reconciliation/sources/run call on a fixed interval over
 * a short, recent, sliding window (never the whole database), and
 * tracks which payment references it has already seen so the UI can
 * show a genuine "newly detected" count. Stops on unmount or when the
 * caller flips `active` off -- never runs in the background silently. */
export function useLiveSync(intervalMs = 20_000) {
  const [active, setActive] = useState(false);
  const [data, setData] = useState<LiveSyncData>({
    lastSyncAt: null,
    lastNewCount: 0,
    latestSummary: null,
    error: null,
  });
  const seenPayments = useRef(new Set<string>());
  const inFlight = useRef(false);

  useEffect(() => {
    if (!active) return;

    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const to = new Date();
        const from = new Date(to.getTime() - LOOKBACK_MS);
        const response = await reconciliationApi.runSource({
          source: "razorpay_test",
          from,
          to,
        });
        const summary = normalizeRunSourceResponse(response);
        if (cancelled) return;

        const newCount = summary.results.filter(
          (row) => !seenPayments.current.has(row.payment),
        ).length;
        for (const row of summary.results) seenPayments.current.add(row.payment);

        setData({
          lastSyncAt: new Date(),
          lastNewCount: newCount,
          latestSummary: summary,
          error: null,
        });
      } catch (error) {
        if (!cancelled) {
          setData((current) => ({
            ...current,
            error: error instanceof Error ? error.message : "Live sync failed.",
          }));
        }
      } finally {
        inFlight.current = false;
      }
    }

    poll();
    const id = setInterval(poll, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [active, intervalMs]);

  return {
    active,
    start: () => {
      seenPayments.current = new Set();
      setActive(true);
    },
    stop: () => setActive(false),
    ...data,
  };
}
