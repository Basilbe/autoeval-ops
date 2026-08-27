export function SkeletonRow() {
  return (
    <div className="flex animate-pulse items-center gap-4 border-b border-ink-raised px-4 py-3">
      <div className="h-4 w-16 rounded bg-ink-raised" />
      <div className="h-4 w-32 rounded bg-ink-raised" />
      <div className="h-4 w-20 rounded bg-ink-raised" />
      <div className="h-4 flex-1 rounded bg-ink-raised" />
    </div>
  );
}