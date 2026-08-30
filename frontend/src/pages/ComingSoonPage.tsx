interface ComingSoonPageProps {
  title: string;
}

export function ComingSoonPage({ title }: ComingSoonPageProps) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface p-12 text-center">
      <h1 className="text-lg font-semibold text-ink">{title}</h1>
      <p className="mt-2 text-sm text-ink-muted">
        This area of LedgerLens is coming soon.
      </p>
    </div>
  );
}
