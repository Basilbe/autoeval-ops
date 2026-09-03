# Phase 5 Complete — 2026-08-30

Verified against every "Task N Done When" checklist in `PHASE_5_SETUP_POWERSHELL.md` (Prerequisites through Task 11). All 12 items: **PASS**. 149/149 tests passing, 98% coverage, 0 errors. Committed to `main` (`80bcc49`), working tree clean, local `main` == `origin/main`.

---

## What Was Built

**OpenTelemetry tracing bootstrap** (`observability/telemetry.py`): `configure_tracing()` builds a `TracerProvider` with an OTLP/HTTP exporter pointed at Jaeger and registers it as the global tracer provider; `instrument_app()` auto-instruments FastAPI and httpx; `get_tracer()` is the shared accessor used everywhere else. Guarded by a module-level `_configured` flag so `configure_tracing()` is idempotent — `uvicorn --reload` re-imports modules on every code change, and without the guard that would re-register the exporter and duplicate every span in Jaeger.

**Spans on the orchestrator and evaluation pipeline** — the paths that actually do work, not instrumented indiscriminately:
- `core/pipeline.py`'s `evaluate_case` emits a parent `"evaluate_case"` span plus one `"evaluator.{name}"` child span per evaluator, each child carrying `metric.name`/`metric.value`/`metric.status` attributes.
- `github/orchestrator.py`'s `handle_eval_job` emits a `"handle_eval_job"` span carrying `github.owner`/`github.repo`/`github.pr_number`/`github.commit` attributes, giving every trace full GitHub context at the root.

**The `traces` table, finally populated.** `db/repository.py`'s `create_trace` writes a row (eval id, trace data, latency, cost) on every completed evaluation. This table was created in Phase 0's schema and never written to in Phases 1–4 — Phase 5 is the first code that touches it. The write sits inside `orchestrator.py`'s existing try/except persistence block, so a trace-write failure follows the same hard rule as Phase 3's evaluation persistence: it can never block the PR comment from posting.

**Postgres-backed metrics aggregation** (`observability/metrics.py`): `StatusMetrics` + `collect_status_metrics`, computed fresh from `evaluations`/`traces` on every request — no in-memory counters, so a server restart doesn't zero the status page. Latency percentiles (p50/p95/p99) use a deliberately simple nearest-rank calculation with no numpy dependency.

**Public `/api/v1/status` endpoint** (`api/routes/status.py`) — the one deliberately unauthenticated route in the entire API. Returns only aggregate figures: counts, pass/error rates, latency percentiles, cost totals, uptime. A regression test (`test_status_exposes_no_identifying_fields`) explicitly guards against project names, repo URLs, emails, API keys, or prompt/commit data ever leaking into this response as the endpoint evolves.

**Public `/status` dashboard page** (`dashboard/src/app/status/page.tsx`), explicitly excluded from `proxy.ts`'s auth matcher via a negative lookahead — unlike every other Phase 4 page, this one renders with no Clerk session and shows a clear error state if the backend is unreachable.

**Test suite**: 149 tests (6 new files' worth of Phase 5 coverage on top of Phase 1–4's suite), **98% coverage** (971 statements, 17 missed), 0 errors.
```
pytest -v --cov=autoeval_ops --cov-report=term-missing
149 passed in 19.97s
TOTAL   971 stmts   17 missed   98%
```

---

## Scope Decisions Confirmed for This Phase

- **OTLP exporter instead of `Roadmap.md`'s `opentelemetry-exporter-jaeger`.** That exporter is deprecated and removed from current OpenTelemetry releases, so it doesn't install cleanly against the versions this project is pinned to. Modern Jaeger accepts OTLP natively — same destination (`http://localhost:16686` for the UI, `4318` for ingest), a supported path instead of a dead one.
- **ClickHouse deferred.** `Roadmap.md` marks it "optional for MVP," and the Phase-0-era `traces` table had never been written to before this phase. Standing up a second analytics database before the first one saw any real use would be real operational weight for no capability this phase actually needs. Revisit if trace volume ever outgrows a live Postgres query.
- **Sentry deferred to Phase 6.** It's fundamentally a production error-tracking tool, and there's no production deployment yet to meaningfully track errors from. Phase 6 is where that wiring will actually mean something.

---

## Real Bug Found and Fixed This Phase

**The Phase 3 fixture-scope issue resurfaced in a new test directory.** Phase 3's fix moved the `db_session` fixture up to the root `tests/conftest.py` so it would be visible to sibling directories, but `sample_user`/`sample_project` were left behind in `tests/db/conftest.py` — invisible to any directory other than `tests/db/`. This stayed dormant through Phase 3 and Phase 4 because nothing outside `tests/db/` needed those fixtures yet. The moment `tests/observability/test_metrics_integration.py` needed `sample_project`, it failed with `fixture 'sample_project' not found`. Fixed by moving both fixtures up to the root `tests/conftest.py`, alongside `db_session`.

**Pattern worth watching for going forward**: any future new test directory that needs a shared fixture should check the root `tests/conftest.py` first, not assume a fixture defined near where it's currently used is visible elsewhere. This is the second time this exact class of bug has surfaced from the same root cause (fixtures defined in a subdirectory's `conftest.py` instead of the root).

---

## Minor Cleanup Performed

The now-unused `opentelemetry-exporter-jaeger` package was uninstalled from the venv after confirming it had zero reverse dependencies (`pip show` returned an empty `Required-by:`). It had lingered as inert leftover after being removed from `requirements.txt` — `pip install -r requirements.txt` only installs what's listed, it doesn't uninstall packages that used to be listed and no longer are. Re-verified `autoeval_ops.server` and `telemetry.py`'s public functions still import cleanly after the uninstall.

---

## Task 10: Confirmed via Direct Six-Step Manual Walkthrough

Unlike Phases 2–4, where the end-to-end live test was confirmed in a follow-up message after the initial audit, Task 10 here was walked through and directly observed in real time, not inferred from database state:

1. `Invoke-RestMethod http://localhost:8001/api/v1/status` returned real JSON with `status: operational` — no authentication header sent or required.
2. `http://localhost:3000/status` opened in an Incognito window rendered the metrics grid directly, with no redirect to Clerk sign-in — genuinely public, not just unauthenticated-but-untested.
3. A fresh webhook fired against the PR and completed.
4. The resulting trace appeared in Jaeger's UI under the `autoeval-ops-backend` service: `handle_eval_job` expanding into `evaluate_case`, which expanded into five `evaluator.*` child spans — the full span tree described in Task 3, visually confirmed rather than assumed from the code.
5. A corresponding row landed in the `traces` table in Postgres.
6. Refreshing `/status` showed the evaluation counts and latency/cost figures had moved to reflect the new data.

All 12 audit items are now a clean PASS.

---

## Follow-Ups Flagged But Not Auto-Applied

- **`TECH_STACK.md` needs two additions now**, not urgent but worth batching into one update when convenient: Phase 4's `truststore` dependency (flagged then, still outstanding), plus this phase's OTLP exporter and Jaeger service.
- **The design polish pass flagged at the end of Phase 4 remains outstanding.** The `/status` page built this phase is a good candidate for that treatment — it's the most public-facing surface built so far, visible to anyone with the URL, not just logged-in users.

---

## Next Step: Phase 6 — Deployment & Polish

See `Roadmap.md` for the full task breakdown. Two things carried forward into this phase specifically because Phase 5 deferred them:

1. **Sentry** — deferred here because there was no production deployment to attach it to. Phase 6 is where that finally exists.
2. **The design polish pass** — deferred since the end of Phase 4, and the `/status` page is the natural first candidate for it given how this phase used it.

Per `CLAUDE.md`'s golden rule: do not begin Phase 6 until this status doc is reviewed and Phase 5 is reconfirmed complete in that session.
