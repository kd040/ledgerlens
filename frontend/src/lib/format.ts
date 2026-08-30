/**
 * The single place domain values get formatted for display. Components
 * call these instead of touching Intl or doing string math themselves.
 */

const currencyFormatter = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

const dateTimeFormatter = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
});

const dateFormatter = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
});

export function formatMoney(value: number | null): string {
  if (value === null) return "—";
  return currencyFormatter.format(value);
}

export function formatPercent(value: number | null): string {
  if (value === null) return "—";
  return `${value.toFixed(0)}%`;
}

export function formatDateTime(value: Date | null): string {
  if (value === null) return "—";
  return dateTimeFormatter.format(value);
}

export function formatDate(value: Date | null): string {
  if (value === null) return "—";
  return dateFormatter.format(value);
}
