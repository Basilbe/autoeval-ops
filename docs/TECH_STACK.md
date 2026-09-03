# AutoEvalOps Tech Stack

> The original version of this document (`TECH_STACK_ORIGINAL_LOCK.md`)
> was written in Phase 0, before any code existed, and marked itself
> "LOCKED — no changes without explicit decision and documentation."
> Several things changed anyway, for real reasons, each logged in its
> phase's status doc as it happened. This version reflects what's
> actually running. The original is kept alongside it, not deleted —
> the gap between the two is itself part of the record.

## Backend
- **Language:** Python 3.11
- **Framework:** FastAPI
- **Server:** Uvicorn (ASGI)
- **ORM:** SQLAlchemy 2.0 (async) + Alembic migrations
- **Database driver:** asyncpg
- **Task queue:** `asyncio.Queue` — this is the real, final choice, not
  an "MVP" stand-in as originally framed. Celery and Redis are
  installed (`requirements.txt`, `docker-compose.yml`) but never used;
  kept as a documented dead weight rather than removed, in case
  horizontal scaling ever makes the queue need to survive a process
  restart.

## Frontend
- **Framework:** Next.js — originally targeted 14+, actually running
  **16.3.3** after `@clerk/nextjs` v5+'s peer dependency forced an
  upgrade in Phase 4
- **Language:** TypeScript
- **UI:** React 19 (via Next 16)
- **Auth:** Clerk
- **Styling:** Tailwind CSS **v4** — a real architecture change from
  v3 (no `tailwind.config.js`; tokens live in `globals.css`'s
  `@theme` block instead)
- **HTTP client:** native `fetch`, not axios as originally planned —
  `lib/api.ts` never needed anything beyond what `fetch` provides

## Database
- **Relational:** PostgreSQL 15 (`postgres:15-alpine` locally; managed
  Postgres on Render in production)
- **Vector DB:** pgvector — deferred in Phase 0, never added. The
  hallucination evaluator uses lexical overlap instead of embeddings;
  see `docs/ARCHITECTURE.md`'s "Deliberate gaps" for the trade-off.
- **Cache:** Redis 7 — present in `docker-compose.yml`, never actually
  used by any code path (see task queue, above)

## Observability
- **Tracing:** OpenTelemetry, exported via **OTLP** — not the Jaeger
  exporter originally specified, which is deprecated and removed from
  current OpenTelemetry releases
- **Tracing backend:** Jaeger, **local development only**. Datadog was
  never wired up for production; `OTEL_ENABLED=false` in the deployed
  environment is a documented, deliberate gap, not a silent omission.
- **Metrics:** not the OpenTelemetry Metrics API as originally
  planned — `observability/metrics.py` computes aggregate figures
  directly from Postgres on each request instead, which fit the
  public `/api/v1/status` endpoint's needs more directly.
- **Logging:** plain `uvicorn`/Python logging, not structured JSON as
  originally planned. `python-json-logger` appears in the installed
  dependency list (a transitive dependency, not something this project
  configured) but confirmed absent from both `server.py` and
  `config.py` by direct search — never actually wired up. A real,
  minor gap: log lines are human-readable in a terminal but not
  structured for a log aggregator to parse.

## DevOps
- **Containerization:** Docker
- **Orchestration:** Docker Compose (dev only). Kubernetes, as
  originally planned for production, was never built — the deployed
  footprint is two managed platform services (below), not a cluster.
- **Deployment:** **Render** (backend) + **Vercel** (dashboard) — not
  AWS/GCP as originally scoped. Render specifically because the
  `asyncio.Queue` worker pool needs a persistent process, which
  serverless platforms can't provide. Render's free tier runs
  `WEB_CONCURRENCY=1` — see `docs/POSTMORTEM.md`'s load test section
  for what that caps throughput at.
- **CI/CD:** GitHub Actions — **planned, not yet built.**
  `.github/workflows/test.yml` doesn't exist yet; this is Phase 6's
  remaining Task 14, still open as of this writing. Tests currently
  only run manually, locally.

## Testing
- **Backend:** pytest + pytest-asyncio, unit and Postgres-backed
  integration suites
- **Frontend:** none. Jest + React Testing Library were planned in
  the original stack lock but never set up — confirmed by direct
  search, no config file and no test files exist anywhere under
  `dashboard/`. The frontend has zero automated test coverage; every
  verification of dashboard behavior across all six phases was a live,
  manual browser walkthrough. A real gap, worth closing before this
  sees any real usage beyond a portfolio demo.
- **Load testing:** Locust, added Phase 6, targeting the public status
  endpoint specifically (not the evaluation pipeline — see
  `docs/POSTMORTEM.md` for why)

## Security
- **API keys:** bcrypt hashing
- **Secrets:** AES-256-GCM encryption for GitHub tokens — **planned,
  never built.** Confirmed absent by direct search of
  `db/repository.py`. In practice this has mattered less than it
  sounds: the deployed system authenticates via GitHub App JWT +
  short-lived installation tokens, not stored long-lived PATs, so
  there's no plaintext secret actually sitting in the
  `github_token_encrypted` column today. Full context in
  `docs/POSTMORTEM.md`.
- **Authentication:** Clerk (dashboard), bcrypt-hashed API keys
  (machine-to-machine)

## Additions After the Original Lock (documented deviations)
- **PyJWT[crypto]** (Phase 2) — GitHub App JWT signing
- **truststore** (Phase 4) — trusts Windows' native certificate store,
  fixing TLS interception by local HTTPS-scanning antivirus
- **OpenTelemetry OTLP exporter** (Phase 5) — see Observability, above
- **google-generativeai** (Phase 6) — Google AI Studio's Gemini API,
  checked first by `build_llm_client`; free tier (rate-limited, not
  metered) fits a demo evaluated occasionally better than paying
  OpenAI per call. `OPENAI_API_KEY` still works as a documented
  alternative via the same `LLMClient` protocol.

---

Changes from here forward should still be a deliberate decision, not a
drift — but "deliberate and documented" is the actual bar this project
has held, not "never changes." Log new deviations in the relevant
phase's status doc as they happen, the same way every change above was
handled.