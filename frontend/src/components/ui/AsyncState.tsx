interface MessageBlockProps {
  message: string;
}

export function LoadingState({ message = "Loading…" }: Partial<MessageBlockProps>) {
  return (
    <div className="rounded-lg border border-border bg-surface p-8 text-center text-sm text-ink-muted">
      {message}
    </div>
  );
}

export function ErrorState({ message }: MessageBlockProps) {
  return (
    <div className="rounded-lg border border-danger-muted bg-danger-muted p-8 text-center text-sm text-danger">
      {message}
    </div>
  );
}

export function EmptyState({ message }: MessageBlockProps) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-surface p-8 text-center text-sm text-ink-faint">
      {message}
    </div>
  );
}
