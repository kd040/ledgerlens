/**
 * Period selection for the daily reconciliation workflow. India has one
 * fixed offset (+05:30, no DST), so wall-clock IST math is just a
 * constant shift -- no timezone library needed. Every preset resolves
 * to explicit UTC instants; nothing here is cosmetic, the resolved
 * `from`/`to` are exactly what's sent to the backend.
 */

const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

export type PeriodPreset = "today" | "yesterday" | "last7" | "custom";

export interface Period {
  from: Date;
  to: Date;
  label: string;
}

/** UTC instant for IST midnight, `daysAgo` days before the IST calendar
 * date of `reference`. */
function istMidnight(reference: Date, daysAgo: number): Date {
  const ist = new Date(reference.getTime() + IST_OFFSET_MS);
  const wallMidnight = Date.UTC(
    ist.getUTCFullYear(),
    ist.getUTCMonth(),
    ist.getUTCDate() - daysAgo,
  );
  return new Date(wallMidnight - IST_OFFSET_MS);
}

export function periodFromPreset(
  preset: Exclude<PeriodPreset, "custom">,
  now: Date = new Date(),
): Period {
  if (preset === "today") {
    return { from: istMidnight(now, 0), to: now, label: "Today" };
  }
  if (preset === "yesterday") {
    return {
      from: istMidnight(now, 1),
      to: istMidnight(now, 0),
      label: "Yesterday",
    };
  }
  return { from: istMidnight(now, 6), to: now, label: "Last 7 Days" };
}

/** `startDate`/`endDate` are "YYYY-MM-DD" values from a native date
 * input, read as IST calendar dates. The end boundary is capped at
 * `now` so a future end date can't request data that can't exist. */
export function periodFromCustomRange(
  startDate: string,
  endDate: string,
  now: Date = new Date(),
): Period | null {
  if (!startDate || !endDate) return null;
  const start = new Date(`${startDate}T00:00:00+05:30`);
  const endExclusive = new Date(
    new Date(`${endDate}T00:00:00+05:30`).getTime() + 24 * 60 * 60 * 1000,
  );
  if (Number.isNaN(start.getTime()) || Number.isNaN(endExclusive.getTime())) {
    return null;
  }
  if (endExclusive <= start) return null;
  const to = endExclusive < now ? endExclusive : now;
  return { from: start, to, label: `${startDate} to ${endDate}` };
}

/** The IST calendar date ("YYYY-MM-DD") a given instant falls on --
 * used to anchor single-day navigation (Previous/Next Day) to a plain
 * date string instead of juggling instants everywhere. */
export function istDateString(reference: Date): string {
  const ist = new Date(reference.getTime() + IST_OFFSET_MS);
  return ist.toISOString().slice(0, 10);
}

/** Shifts an IST calendar date string by `days` (negative moves back). */
export function shiftIsoDate(isoDate: string, days: number): string {
  const shifted = new Date(`${isoDate}T00:00:00Z`);
  shifted.setUTCDate(shifted.getUTCDate() + days);
  return shifted.toISOString().slice(0, 10);
}

const istDateFormatter = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "long",
  timeZone: "Asia/Kolkata",
});

/** A human heading for the period actually sent to the backend, e.g.
 * "26 August 2026" for a single IST day or "20 – 26 August 2026" for a
 * range -- read back from the real from/to instants, not the preset
 * label, so it stays correct even after a custom range or a period
 * whose `to` was capped at "now". */
export function formatPeriodHeading(from: Date, to: Date): string {
  const fromLabel = istDateFormatter.format(from);
  const toLabel = istDateFormatter.format(new Date(to.getTime() - 1));
  return fromLabel === toLabel ? fromLabel : `${fromLabel} – ${toLabel}`;
}
