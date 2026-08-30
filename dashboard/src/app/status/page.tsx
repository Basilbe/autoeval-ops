const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

interface StatusResponse {
  service: string;
  status: string;
  uptime_seconds: number;
  metrics: {
    total_evaluations: number;
    evaluations_24h: number;
    pass_rate: number;
    error_rate: number;
    latency: { p50_ms: number; p95_ms: number; p99_ms: number };
    cost: { avg_usd: number; total_usd: number };
    status_counts: Record<string, number>;
  };
}

// Always fetch fresh - this is a live status page, caching defeats the point.
export const dynamic = "force-dynamic";

function Stat({ label, value, unit }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="rounded border border-ink-raised px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-bone-dim">{label}</div>
      <div className="mt-1 text-xl tabular-nums">
        {value}
        {unit ? <span className="ml-1 text-sm text-bone-dim">{unit}</span> : null}
      </div>
    </div>
  );
}

export default async function StatusPage() {
  let data: StatusResponse | null = null;
  let error: string | null = null;

  try {
    const res = await fetch(`${API_URL}/api/v1/status`, { cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status}`);
    data = await res.json();
  } catch (e) {
    error = e instanceof Error ? e.message : "unreachable";
  }

  if (error || !data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-lg font-medium tracking-tight">AutoEvalOps Status</h1>
        <div className="mt-6 rounded border border-fail/40 px-6 py-10 text-center text-fail">
          Status unavailable &mdash; backend unreachable ({error}).
        </div>
      </main>
    );
  }

  const m = data.metrics;
  const uptimeHours = (data.uptime_seconds / 3600).toFixed(1);

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-lg font-medium tracking-tight">AutoEvalOps Status</h1>
        <span className="rounded bg-acid/20 px-2 py-0.5 text-xs uppercase tracking-wide text-acid">
          {data.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Evaluations" value={m.total_evaluations} />
        <Stat label="Last 24h" value={m.evaluations_24h} />
        <Stat label="Uptime" value={uptimeHours} unit="h" />
        <Stat label="Pass rate" value={(m.pass_rate * 100).toFixed(1)} unit="%" />
        <Stat label="Error rate" value={(m.error_rate * 100).toFixed(1)} unit="%" />
        <Stat label="Total cost" value={`$${m.cost.total_usd.toFixed(4)}`} />
      </div>

      <h2 className="mb-3 mt-8 text-sm uppercase tracking-wide text-bone-dim">Latency</h2>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="p50" value={m.latency.p50_ms} unit="ms" />
        <Stat label="p95" value={m.latency.p95_ms} unit="ms" />
        <Stat label="p99" value={m.latency.p99_ms} unit="ms" />
      </div>

      <p className="mt-8 text-xs text-bone-dim">
        Aggregate metrics only. No project, repository, or prompt data is exposed here.
      </p>
    </main>
  );
}