"use client";

const STYLES: Record<string, string> = {
  pending: "bg-bone-dim/20 text-bone-dim",
  running: "bg-acid/20 text-acid animate-pulse",
  pass: "bg-acid/20 text-acid",
  fail: "bg-fail/20 text-fail",
  warning: "bg-warn/20 text-warn",
};

export function StatusPill({ status }: { status: string }) {
  const style = STYLES[status] ?? STYLES.pending;
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium uppercase tracking-wide transition-colors duration-200 ${style}`}
    >
      {status}
    </span>
  );
}