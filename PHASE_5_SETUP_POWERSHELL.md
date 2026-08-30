# Phase 5: Observability & Telemetry (PowerShell Edition)

> Labels as before: **"Run in PowerShell"** or **"Paste into `filename`"**.

## Scope Decisions (confirmed before building)

- **OTLP exporter, not the Jaeger exporter.** `Roadmap.md` specifies `opentelemetry-exporter-jaeger`, which is now deprecated and removed from current OpenTelemetry releases. Modern Jaeger accepts OTLP natively, so this guide uses `opentelemetry-exporter-otlp-proto-http`. Same destination, supported path.
- **ClickHouse deferred.** `Roadmap.md` marks it "optional for MVP." Phase 0 already created a `traces` table in Postgres that has never been written to — Phase 5 finally populates it. Adding a second analytics database now would add real operational weight for no capability this phase needs. Revisit if trace volume ever outgrows Postgres.
- **Sentry deferred to Phase 6.** It's another external account signup, and it's fundamentally a *production* error-tracking tool — there's no production deployment to track errors from until Phase 6. Structured error logging is added here instead so the wiring exists.
- **The `/status` page is genuinely public.** No Clerk auth, no login. That means both a public backend endpoint and an explicit exclusion from `proxy.ts`'s matcher — this is a real change to Phase 4's auth setup, not just a new page.
- **Metrics are computed from Postgres, not held in memory.** A restart shouldn't zero the status page. Aggregates are queried from `evaluations`/`eval_results`/`traces` on request.
- **Tracing wraps the orchestrator and evaluators**, the paths that actually do work. Not every function — noise in a trace view is worse than no trace view.

---

## Prerequisites

### Start the existing stack

**Run in PowerShell (from the repo root):**
```powershell
docker-compose up -d
docker-compose ps
```
Confirm `autoeval_postgres` is `Up`.

### Update dependencies

`Roadmap.md`'s original `opentelemetry-exporter-jaeger` line must be removed — it no longer installs cleanly against current OpenTelemetry versions.

**Run in PowerShell (from `backend/`, venv active):**
```powershell
notepad requirements.txt
```
**Remove this line if present:**
```text
opentelemetry-exporter-jaeger==1.21.0
```
**Add these:**
```text
opentelemetry-exporter-otlp-proto-http
opentelemetry-instrumentation-httpx
```
Save, close.

```powershell
pip install -r requirements.txt
```

> Existing OpenTelemetry packages (`opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`) were already installed back in Phase 0 and stay as-is.

### Task Done When:
- [ ] Docker services running
- [ ] `opentelemetry-exporter-jaeger` removed from `requirements.txt`
- [ ] OTLP exporter + httpx instrumentation installed

---

## Task 1: Add Jaeger to Docker Compose

**Run in PowerShell (from the repo root):**
```powershell
notepad docker-compose.yml
```
Add this service block alongside the existing services (same indentation level as `postgres`), save, close:
```yaml
  jaeger:
    image: jaegertracing/all-in-one:latest
    container_name: autoeval_jaeger
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    ports:
      - "16686:16686"   # Jaeger UI
      - "4318:4318"     # OTLP HTTP receiver
```

**Run in PowerShell:**
```powershell
docker-compose up -d
docker-compose ps
```
Confirm `autoeval_jaeger` shows `Up`.

**Verify the UI loads:** open http://localhost:16686 in a browser — Jaeger's trace search page should appear (empty for now, since nothing has emitted a trace yet).

### Task 1 Done When:
- [ ] `autoeval_jaeger` container running
- [ ] Jaeger UI reachable at http://localhost:16686

---

## Task 2: Telemetry Bootstrap

**Run in PowerShell (from `backend/`):**
```powershell
New-Item -ItemType Directory -Force -Path src\autoeval_ops\observability
New-Item -ItemType File -Force -Path src\autoeval_ops\observability\__init__.py
notepad src\autoeval_ops\observability\telemetry.py
```

**Paste into `backend/src/autoeval_ops/observability/telemetry.py`:**
```python
"""OpenTelemetry setup: tracer provider, OTLP export to Jaeger, and
auto-instrumentation for FastAPI, SQLAlchemy, and httpx.

Uses the OTLP exporter rather than the Jaeger exporter Roadmap.md
originally specified - that exporter is deprecated and removed from
current OpenTelemetry releases; modern Jaeger accepts OTLP natively.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from autoeval_ops.config import settings

SERVICE_NAME = "autoeval-ops-backend"

_configured = False


def configure_tracing() -> None:
    """Idempotent - safe to call more than once (uvicorn --reload can
    re-import modules, and double-registering exporters duplicates spans)."""
    global _configured
    if _configured or not settings.otel_enabled:
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{settings.otel_exporter_endpoint}/v1/traces")
        )
    )
    trace.set_tracer_provider(provider)
    _configured = True


def instrument_app(app) -> None:
    """Auto-instrument FastAPI, SQLAlchemy, and httpx. Called from
    server.py after the app is created."""
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,api/v1/status")
    HTTPXClientInstrumentor().instrument()


def get_tracer(name: str):
    return trace.get_tracer(name)
```
Save, close.

**Add the settings it needs:**
```powershell
notepad src\autoeval_ops\config.py
```
Add these inside the `Settings` class (below the Clerk fields), save, close:
```python
    # Observability (Phase 5)
    otel_enabled: bool = True
    otel_exporter_endpoint: str = "http://localhost:4318"
```

**Run in PowerShell (from the repo root):**
```powershell
notepad .env.example
```
Add, save, close:
```ini
OTEL_ENABLED=true
OTEL_EXPORTER_ENDPOINT=http://localhost:4318
```
Mirror the same two lines into your real `.env`:
```powershell
notepad .env
```

### Task 2 Done When:
- [ ] `telemetry.py` created with `configure_tracing`, `instrument_app`, `get_tracer`
- [ ] `config.py` has `otel_enabled` and `otel_exporter_endpoint`
- [ ] Both `.env` and `.env.example` updated

---

## Task 3: Instrument the Evaluation Pipeline

Wraps the paths that actually do work — the orchestrator's per-job flow and each evaluator — rather than instrumenting everything indiscriminately.

**Run in PowerShell (from `backend/`):**
```powershell
notepad src\autoeval_ops\core\pipeline.py
```

Add the import near the top, alongside the existing imports:
```python
from autoeval_ops.observability.telemetry import get_tracer
```

Then find `evaluate_case` and replace it with this traced version:
```python
    async def evaluate_case(self, output: str, **kwargs: Any) -> EvaluationReport:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("evaluate_case") as span:
            span.set_attribute("evaluator.count", len(self.evaluators))

            async def _run_traced(evaluator: Evaluator):
                with tracer.start_as_current_span(f"evaluator.{evaluator.name}") as ev_span:
                    result = await evaluator.evaluate(output, **kwargs)
                    ev_span.set_attribute("metric.name", result.metric_name)
                    ev_span.set_attribute("metric.value", result.metric_value)
                    ev_span.set_attribute("metric.status", result.status)
                    return result

            results = await asyncio.gather(*[_run_traced(ev) for ev in self.evaluators])
            report = EvaluationReport(results=list(results))
            span.set_attribute("overall.status", report.overall_status)
            return report
```
Save, close.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\orchestrator.py
```

Add the import alongside the existing ones:
```python
from autoeval_ops.observability.telemetry import get_tracer
```

Then find `handle_eval_job` and wrap its body — add this as the first line inside the function, and indent the existing body one level:
```python
async def handle_eval_job(
    job: EvalJob,
    app_auth: GitHubAppAuth,
    model: str = "gpt-4",
    client_factory=GitHubClient,
    session_factory=None,
) -> None:
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("handle_eval_job") as span:
        span.set_attribute("github.owner", job.owner)
        span.set_attribute("github.repo", job.repo)
        span.set_attribute("github.pr_number", job.pr_number)
        span.set_attribute("github.commit", job.head_sha)

        # ... existing body, indented one additional level ...
```

> This one edit is fiddly because it re-indents an existing function body. If the indentation gets tangled, the safest recovery is `git checkout backend/src/autoeval_ops/github/orchestrator.py` to restore it, then retry carefully.

### Task 3 Done When:
- [ ] `pipeline.py`'s `evaluate_case` emits a parent span plus one child span per evaluator
- [ ] `orchestrator.py`'s `handle_eval_job` emits a span with GitHub context attributes
- [ ] Both files still import cleanly (`python -c "import autoeval_ops.github.orchestrator"`)

---

## Task 4: Persist Traces to Postgres

Phase 0 created a `traces` table that has never been written to. This finally populates it — giving the status page real latency/cost data to aggregate without needing a separate analytics store.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\db\repository.py
```
Add this function alongside the other evaluation functions, save, close:
```python
async def create_trace(
    db: AsyncSession,
    eval_id: uuid.UUID,
    trace_data: dict[str, Any],
    latency_ms: int,
    cost_usd: float,
) -> Trace:
    trace = Trace(
        eval_id=eval_id,
        trace_data=trace_data,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
    db.add(trace)
    await db.flush()
    return trace
```

Also add `Trace` to the model imports at the top of the file:
```python
from autoeval_ops.db.models import (
    EvalResult,
    Evaluation,
    Organization,
    Project,
    Trace,
    User,
)
```

**Now write a trace row when an evaluation completes.**
```powershell
notepad src\autoeval_ops\github\orchestrator.py
```
Inside `handle_eval_job`'s persistence block, right after the `complete_evaluation` call and before `await db.commit()`, add:
```python
                    metrics_by_name = {r["metric_name"]: r["metric_value"] for r in metric_rows}
                    await repository.create_trace(
                        db,
                        eval_id=evaluation.id,
                        trace_data={
                            "prompt_version": prompt_path,
                            "model": model,
                            "case_count": len(test_cases),
                            "overall_status": overall,
                        },
                        latency_ms=int(metrics_by_name.get("latency", 0.0)),
                        cost_usd=float(metrics_by_name.get("cost", 0.0)),
                    )
```
Save, close.

### Task 4 Done When:
- [ ] `create_trace` exists in `repository.py`
- [ ] `orchestrator.py` writes a trace row alongside each completed evaluation
- [ ] Persistence is still inside the existing try/except (a trace-write failure must not block PR commenting)

---

## Task 5: Metrics Aggregation

Computed from Postgres on request, so a server restart doesn't reset the numbers.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\observability\metrics.py
```

**Paste into `backend/src/autoeval_ops/observability/metrics.py`:**
```python
"""Aggregate metrics for the public status page.

Computed from Postgres on each request rather than held in memory, so
restarts don't zero the numbers. At current volume a live query is
cheap; revisit with a rollup table if evaluation counts grow large.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.db.models import Evaluation, Trace


@dataclass
class StatusMetrics:
    total_evaluations: int = 0
    evaluations_24h: int = 0
    pass_rate: float = 0.0
    error_rate: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    avg_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    status_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total_evaluations": self.total_evaluations,
            "evaluations_24h": self.evaluations_24h,
            "pass_rate": round(self.pass_rate, 4),
            "error_rate": round(self.error_rate, 4),
            "latency": {
                "p50_ms": round(self.latency_p50_ms, 2),
                "p95_ms": round(self.latency_p95_ms, 2),
                "p99_ms": round(self.latency_p99_ms, 2),
            },
            "cost": {
                "avg_usd": round(self.avg_cost_usd, 6),
                "total_usd": round(self.total_cost_usd, 6),
            },
            "status_counts": self.status_counts,
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Deliberately simple - no numpy dependency
    for what is a handful of arithmetic operations."""
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, int(round(pct * len(sorted_values) + 0.5)) - 1))
    return sorted_values[index]


async def collect_status_metrics(db: AsyncSession) -> StatusMetrics:
    metrics = StatusMetrics()

    total = await db.execute(select(func.count()).select_from(Evaluation))
    metrics.total_evaluations = total.scalar_one()

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    recent = await db.execute(
        select(func.count()).select_from(Evaluation).where(Evaluation.created_at >= cutoff)
    )
    metrics.evaluations_24h = recent.scalar_one()

    status_rows = await db.execute(
        select(Evaluation.status, func.count()).group_by(Evaluation.status)
    )
    counts = {status: count for status, count in status_rows.all() if status}
    metrics.status_counts = counts

    completed = sum(counts.values())
    if completed:
        metrics.pass_rate = counts.get("pass", 0) / completed
        metrics.error_rate = counts.get("failed", 0) / completed

    latency_rows = await db.execute(
        select(Trace.latency_ms).where(Trace.latency_ms.is_not(None)).order_by(Trace.latency_ms)
    )
    latencies = [float(v) for v in latency_rows.scalars().all()]
    if latencies:
        metrics.latency_p50_ms = _percentile(latencies, 0.50)
        metrics.latency_p95_ms = _percentile(latencies, 0.95)
        metrics.latency_p99_ms = _percentile(latencies, 0.99)

    cost_rows = await db.execute(
        select(func.avg(Trace.cost_usd), func.sum(Trace.cost_usd)).where(
            Trace.cost_usd.is_not(None)
        )
    )
    avg_cost, total_cost = cost_rows.one()
    metrics.avg_cost_usd = float(avg_cost or 0.0)
    metrics.total_cost_usd = float(total_cost or 0.0)

    return metrics
```
Save, close.

### Task 5 Done When:
- [ ] `metrics.py` created with `StatusMetrics` and `collect_status_metrics`
- [ ] Imports cleanly

---

## Task 6: Public Status Endpoint

**Deliberately unauthenticated** — no `Depends(get_current_user)`. This is the one endpoint in the API that anyone can hit.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\routes\status.py
```

**Paste into `backend/src/autoeval_ops/api/routes/status.py`:**
```python
"""Public status endpoint - deliberately unauthenticated.

This is the only route in the API without an auth dependency. It exposes
aggregate operational metrics only: counts, percentiles, and costs. No
project names, repo URLs, prompt contents, user emails, or per-evaluation
detail - nothing that identifies a customer or leaks evaluation content.
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.db.session import get_db
from autoeval_ops.observability.metrics import collect_status_metrics

router = APIRouter(prefix="/api/v1", tags=["status"])

_STARTED_AT = datetime.now(timezone.utc)


@router.get("/status")
async def public_status(db: AsyncSession = Depends(get_db)) -> dict:
    metrics = await collect_status_metrics(db)
    uptime_seconds = (datetime.now(timezone.utc) - _STARTED_AT).total_seconds()
    return {
        "service": "AutoEvalOps",
        "status": "operational",
        "uptime_seconds": int(uptime_seconds),
        "metrics": metrics.as_dict(),
    }
```
Save, close.

**Register it and wire up tracing in `server.py`:**
```powershell
notepad src\autoeval_ops\server.py
```

Add the telemetry import near the top (after the existing `truststore` lines, before other app imports):
```python
from autoeval_ops.observability.telemetry import configure_tracing, instrument_app

configure_tracing()
```

Add the status router import alongside the others:
```python
from autoeval_ops.api.routes.status import router as status_router
```

Then, after `app = FastAPI(...)` is created, add:
```python
instrument_app(app)
```

And register the router with the rest:
```python
app.include_router(status_router)
```

Also **update CORS** to allow the status page to be fetched from anywhere (it's public data by design):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Leave this as-is for now — the dashboard's own `/status` page is served from the same origin, so no change is needed. (If you later host the status page separately, this is the line to revisit.)

Save, close.

### Task 6 Done When:
- [ ] `status.py` route created, no auth dependency
- [ ] `server.py` calls `configure_tracing()` at import and `instrument_app(app)` after app creation
- [ ] Status router registered

---

## Task 7: Make `/status` Public in the Dashboard

Phase 4's `proxy.ts` protects every route. The status page has to be explicitly excluded, or visitors get bounced to Clerk's sign-in.

**Run in PowerShell (from `dashboard/`):**
```powershell
notepad src\proxy.ts
```

**Paste (full replacement):**
```typescript
import { clerkMiddleware } from "@clerk/nextjs/server";

export default clerkMiddleware();

export const config = {
  // /status is deliberately excluded - it's a public page, no auth.
  matcher: ["/((?!_next|status|.*\\..*).*)", "/(api|trpc)(.*)"],
};
```
Save, close.

### Task 7 Done When:
- [ ] `proxy.ts`'s matcher excludes `/status`

---

## Task 8: Status Page UI

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path src\app\status
notepad src\app\status\page.tsx
```

**Paste into `dashboard/src/app/status/page.tsx`:**
```tsx
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
```
Save, close.

### Task 8 Done When:
- [ ] `/status` page created
- [ ] Renders without auth
- [ ] Shows a clear error state if the backend is unreachable

---

## Task 9: Tests

**Run in PowerShell (from `backend/`):**
```powershell
New-Item -ItemType Directory -Force -Path tests\observability
New-Item -ItemType File -Force -Path tests\observability\__init__.py
notepad tests\observability\test_metrics.py
```

**Paste into `backend/tests/observability/test_metrics.py`:**
```python
"""Percentile maths - pure functions, no database needed."""
from autoeval_ops.observability.metrics import StatusMetrics, _percentile


def test_percentile_of_empty_list_is_zero():
    assert _percentile([], 0.95) == 0.0


def test_percentile_p50_of_simple_range():
    assert _percentile([10.0, 20.0, 30.0, 40.0, 50.0], 0.50) == 30.0


def test_percentile_p99_returns_near_max():
    values = [float(i) for i in range(1, 101)]
    assert _percentile(values, 0.99) >= 99.0


def test_percentile_never_indexes_out_of_range():
    assert _percentile([5.0], 0.99) == 5.0


def test_status_metrics_as_dict_shape():
    metrics = StatusMetrics(total_evaluations=3, pass_rate=0.6667)
    data = metrics.as_dict()
    assert data["total_evaluations"] == 3
    assert data["pass_rate"] == 0.6667
    assert "latency" in data and "cost" in data


def test_status_metrics_defaults_are_zero():
    data = StatusMetrics().as_dict()
    assert data["total_evaluations"] == 0
    assert data["latency"]["p95_ms"] == 0.0
```
Save, close.

**Run in PowerShell:**
```powershell
notepad tests\observability\test_status_route.py
```

**Paste into `backend/tests/observability/test_status_route.py`:**
```python
"""Verifies /api/v1/status is genuinely public (no auth) and exposes only
aggregate data - no project names, repo URLs, emails, or prompt content."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autoeval_ops.api.routes.status import router as status_router
from autoeval_ops.db.session import get_db
from autoeval_ops.observability.metrics import StatusMetrics


@pytest.fixture
def client(monkeypatch):
    async def _fake_metrics(db):
        return StatusMetrics(
            total_evaluations=5,
            evaluations_24h=2,
            pass_rate=0.8,
            error_rate=0.2,
            latency_p50_ms=120.0,
            latency_p95_ms=300.0,
            latency_p99_ms=450.0,
            avg_cost_usd=0.0006,
            total_cost_usd=0.003,
            status_counts={"pass": 4, "fail": 1},
        )

    monkeypatch.setattr(
        "autoeval_ops.api.routes.status.collect_status_metrics", _fake_metrics
    )

    app = FastAPI()
    app.include_router(status_router)

    async def _no_db():
        yield None

    app.dependency_overrides[get_db] = _no_db
    return TestClient(app)


def test_status_requires_no_authentication(client):
    # No X-API-Key, no Authorization header - must still succeed.
    assert client.get("/api/v1/status").status_code == 200


def test_status_reports_operational(client):
    body = client.get("/api/v1/status").json()
    assert body["status"] == "operational"
    assert body["service"] == "AutoEvalOps"


def test_status_includes_expected_metric_shape(client):
    metrics = client.get("/api/v1/status").json()["metrics"]
    assert metrics["total_evaluations"] == 5
    assert metrics["latency"]["p95_ms"] == 300.0
    assert metrics["cost"]["total_usd"] == 0.003


def test_status_exposes_no_identifying_fields(client):
    """Regression guard: this endpoint is public, so it must never start
    leaking project/repo/user data as it evolves."""
    body = client.get("/api/v1/status").text.lower()
    for leaked in ["github_repo_url", "email", "api_key", "prompt_version", "commit_hash"]:
        assert leaked not in body


def test_status_includes_uptime(client):
    body = client.get("/api/v1/status").json()
    assert "uptime_seconds" in body
    assert body["uptime_seconds"] >= 0
```
Save, close.

**Add an integration test for real metric aggregation:**

> `sample_project` (and `sample_user`, which it depends on) must live in the **root** `tests/conftest.py`, not `tests/db/conftest.py`. Phase 3's fixture-scope fix only moved `db_session` up to the root — `sample_project` stayed behind in `tests/db/`, invisible to sibling directories like `tests/observability/`. Check now:
> ```powershell
> Select-String -Path tests\conftest.py -Pattern "def sample_project"
> ```
> If that returns nothing, cut `sample_user` and `sample_project`'s fixture definitions out of `tests/db/conftest.py` and paste them into the root `tests/conftest.py` instead, before continuing — otherwise this test file (and any future one outside `tests/db/`) will fail with `fixture 'sample_project' not found`.

```powershell
notepad tests\observability\test_metrics_integration.py
```

**Paste into `backend/tests/observability/test_metrics_integration.py`:**
```python
"""Metrics aggregation against real Postgres.
Run with: pytest -m integration   (requires docker-compose up -d)
"""
from __future__ import annotations

import pytest

from autoeval_ops.db import repository
from autoeval_ops.observability.metrics import collect_status_metrics

pytestmark = pytest.mark.integration


async def test_metrics_on_empty_slice_do_not_error(db_session):
    metrics = await collect_status_metrics(db_session)
    assert metrics.total_evaluations >= 0
    assert metrics.latency_p95_ms >= 0.0


async def test_metrics_count_a_created_evaluation(db_session, sample_project):
    before = await collect_status_metrics(db_session)
    await repository.create_evaluation(
        db_session,
        project_id=sample_project.id,
        commit_hash="c" * 40,
        prompt_version="prompts/x.txt",
        model_name="gpt-4",
        test_cases_count=1,
    )
    after = await collect_status_metrics(db_session)
    assert after.total_evaluations == before.total_evaluations + 1


async def test_trace_row_feeds_latency_and_cost(db_session, sample_project):
    evaluation = await repository.create_evaluation(
        db_session,
        project_id=sample_project.id,
        commit_hash="d" * 40,
        prompt_version="prompts/x.txt",
        model_name="gpt-4",
        test_cases_count=1,
    )
    await repository.create_trace(
        db_session,
        eval_id=evaluation.id,
        trace_data={"model": "gpt-4"},
        latency_ms=250,
        cost_usd=0.0012,
    )
    metrics = await collect_status_metrics(db_session)
    assert metrics.latency_p50_ms > 0
    assert metrics.total_cost_usd > 0
```
Save, close.

### Task 9 Done When:
- [ ] Three test files created
- [ ] `pytest -m "not integration"` passes
- [ ] `pytest -m integration` passes with Docker running

---

## Task 10: Run Everything and Verify Traces

### Step 10.1: Start the stack

**Tab 1 — backend** (from `backend/`, venv active):
```powershell
python -m uvicorn autoeval_ops.server:app --reload --port 8001
```

**Tab 2 — dashboard** (from `dashboard/`):
```powershell
npm run dev
```

**Tab 3 — tunnel** (only needed for the webhook test in Step 10.4):
```powershell
cloudflared tunnel --url http://localhost:8001
```

### Step 10.2: Confirm the status endpoint works

**Run in PowerShell (new tab):**
```powershell
Invoke-RestMethod http://localhost:8001/api/v1/status
```
Should return real JSON with `status: operational` and metrics reflecting whatever's in your database — **and notably, no authentication header was needed**. That's the point.

### Step 10.3: Confirm the public status page

Open http://localhost:3000/status — **in an Incognito window**, to genuinely prove it's public rather than relying on your existing session. It should render the metrics grid without redirecting to sign-in.

### Step 10.4: Generate a trace

Update the GitHub App's webhook URL to Tab 3's fresh tunnel URL (+ `/github/webhook`), then trigger a PR the same way as Phase 4 — either a new commit on an existing PR branch, or **Redeliver** from the App's **Advanced → Recent Deliveries**.

### Step 10.5: View the trace in Jaeger

Open http://localhost:16686:
1. In the **Service** dropdown, select `autoeval-ops-backend`
2. Click **Find Traces**
3. You should see a trace for the webhook request, expanding into `handle_eval_job` → `evaluate_case` → one span per evaluator (`evaluator.correctness`, `evaluator.toxicity`, etc.), each with its metric attributes

This is the phase's real payoff — a complete, visual trace of one evaluation from webhook to per-metric result.

### Step 10.6: Confirm the trace row landed in Postgres

**Run in PowerShell:**
```powershell
docker exec -it autoeval_postgres psql -U autoeval_user -d autoeval_dev -c "SELECT id, eval_id, latency_ms, cost_usd, created_at FROM traces ORDER BY created_at DESC LIMIT 5;"
```
Should show a real row — the `traces` table finally in use after being created back in Phase 0.

### Step 10.7: Confirm the status page reflects it

Refresh http://localhost:3000/status — evaluation counts and latency/cost figures should have moved.

### Task 10 Done When:
- [ ] `/api/v1/status` returns data with no auth
- [ ] `/status` page renders in Incognito (genuinely public)
- [ ] A full trace is visible in Jaeger with per-evaluator spans
- [ ] A `traces` row exists in Postgres
- [ ] Status page metrics reflect the new evaluation

---

## Task 11: Final Commit

**Run in PowerShell (from the repo root):**
```powershell
cd backend
.venv\Scripts\Activate.ps1
pytest -v --cov=autoeval_ops --cov-report=term-missing
deactivate
cd ..
git status
```

```powershell
git add -A
git commit -m "[PHASE 5] Observability: OpenTelemetry tracing, metrics, public status page

- Jaeger added to docker-compose; OTLP exporter (not the deprecated
  Jaeger exporter Roadmap.md specified)
- Tracing on the orchestrator and evaluation pipeline, one span per
  evaluator with metric attributes
- traces table (created in Phase 0, never used until now) finally
  populated on each completed evaluation
- Metrics aggregated from Postgres on request, so restarts don't reset
  the status page
- Public /api/v1/status endpoint - the only unauthenticated route -
  exposing aggregate figures only, with a regression test guarding
  against identifying data leaking into it
- /status dashboard page, explicitly excluded from proxy.ts's matcher
- ClickHouse deferred (Roadmap.md marks it optional; Postgres is
  sufficient at this volume). Sentry deferred to Phase 6, where there's
  actually a production deployment to monitor.
- Breaking changes: NO"
git push origin main
```

### Final Checklist:
- [ ] Jaeger running, traces visible
- [ ] `traces` table populated
- [ ] Public status endpoint and page working without auth
- [ ] All tests passing, coverage ≥95%
- [ ] Committed and pushed

---

## Next Step

Write `PHASE_5_STATUS.md` (same audit pattern as prior phases), then **Phase 6: Deployment & Polish**.

Two things to carry forward into Phase 6:
1. **Sentry** was deliberately deferred here — it belongs with the production deployment.
2. **The design polish pass** flagged at the end of Phase 4 is still outstanding. Phase 6's "Polish" scope is the natural home for it, and the `/status` page built here is a good candidate for that treatment since it's public-facing.

---

## Troubleshooting Log (Phase 5)

| Symptom | Cause | Fix |
|---|---|---|
| `pip install` fails on `opentelemetry-exporter-jaeger` | That exporter is deprecated and removed from current OpenTelemetry releases | Remove it from `requirements.txt`; use `opentelemetry-exporter-otlp-proto-http` instead (Prerequisites) |
| Jaeger UI loads but shows no services | Nothing has emitted a span yet, or the OTLP endpoint is wrong | Trigger a real request first. Confirm `OTEL_EXPORTER_ENDPOINT` is `http://localhost:4318` and that `autoeval_jaeger` is `Up` with port 4318 published |
| Spans appear duplicated in Jaeger | `configure_tracing()` ran more than once — `uvicorn --reload` can re-import modules, registering the exporter twice | The `_configured` guard in `telemetry.py` prevents this; if you see duplicates, confirm that guard wasn't removed |
| `/status` redirects to Clerk sign-in | `proxy.ts`'s matcher still protects it | Confirm Task 7's matcher includes `status` in the negative lookahead group |
| Status page shows "backend unreachable" | `NEXT_PUBLIC_API_URL` doesn't match the port uvicorn is actually on | Confirm both agree (`8001` throughout these guides) and restart `npm run dev` — Next.js only reads env vars at startup |
| `traces` table stays empty after an evaluation | The trace write is inside the orchestrator's persistence block, which is skipped entirely for unregistered repos | Confirm the repo is registered as a project (see Phase 3/4), and check the uvicorn log for the "not a registered project" line |
| `fixture 'sample_project' not found` when running `tests/observability/test_metrics_integration.py` | Phase 3's fixture-scope fix only moved `db_session` to the root `tests/conftest.py` — `sample_user`/`sample_project` stayed in `tests/db/conftest.py`, invisible to sibling directories | Move both fixtures to the root `tests/conftest.py` (Task 9, already noted above) — this affects any future test directory outside `tests/db/`, not just this one |
