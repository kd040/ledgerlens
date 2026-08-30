import { formatMoney } from "../../lib/format";

interface MoneyValueProps {
  value: number | null;
  className?: string;
}

export function MoneyValue({ value, className }: MoneyValueProps) {
  return (
    <span className={`font-mono tabular-nums ${className ?? ""}`}>
      {formatMoney(value)}
    </span>
  );
}
