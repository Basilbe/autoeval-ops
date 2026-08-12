# Phase 0 Complete — 2026-08-10

Verified against every "Task N Done When" checklist in `PHASE_0_SETUP_POWERSHELL.md` (Tasks 1-10). All 10 tasks: **PASS**. Repository pushed to GitHub, working tree clean, `origin/main` == local `HEAD` (`a556a6d`).

---

## Tech Stack (locked — see `docs/TECH_STACK.md`)

**Backend:** Python 3.11+, FastAPI, Uvicorn (ASGI), SQLAlchemy 2.0 (async), asyncpg, asyncio.Queue (MVP) / Celery (production)

**Frontend:** Next.js 14+, TypeScript, React 18+, Clerk (auth), Tailwind CSS, axios

**Database:** PostgreSQL 15+ (relational), pgvector (separate container, deferred), Redis 7+ (cache)

**Observability:** OpenTelemetry, Jaeger (local) / Datadog (prod), JSON structured logs

**DevOps:** Docker, Docker Compose (dev) / Kubernetes (prod), AWS/GCP/Vercel, GitHub Actions CI/CD

**Testing:** pytest + pytest-asyncio (backend), Jest + React Testing Library (frontend), Locust (load)

**Security:** bcrypt (API keys), AES-256-GCM (secrets), Clerk (auth)

> Per `docs/TECH_STACK.md`: **NO CHANGES AFTER THIS POINT** without explicit decision and documentation.

---

## Database Schema (as implemented in `backend/db/schema.sql`)

6 core relational tables, no vector/embeddings. Verified live via `\dt` against `autoeval_postgres`.

- **users** — id (UUID PK), email (unique), api_key, api_key_hash, created_at, updated_at
- **organizations** — id (UUID PK), user_id (FK→users), name, plan (default 'free'), created_at
- **projects** — id (UUID PK), org_id (FK→organizations), name, github_repo_url, github_token_encrypted, created_at
- **evaluations** — id (UUID PK), project_id (FK→projects), commit_hash, prompt_version, model_name, test_cases_count, status (default 'pending'), results_json (JSONB), created_at, completed_at
- **eval_results** — id (UUID PK), eval_id (FK→evaluations), metric_name, metric_value, status (default 'pass'), details (JSONB), created_at
- **traces** — id (UUID PK), eval_id (FK→evaluations), trace_data (JSONB), latency_ms, cost_usd, created_at

7 indexes created (on FKs and `evaluations.created_at`).

---

## Deliberate Deviations from Original Plan

- **pgvector / embeddings deferred.** The original roadmap listed pgvector as "built into PostgreSQL," but it does not ship in the plain `postgres:15-alpine` image. Rather than force it into `autoeval_postgres`, pgvector runs as a **separate container** (`autoeval_pgvector`, port 5433, image `ankane/pgvector`). No `CREATE EXTENSION vector` or embeddings tables exist yet — intentionally out of scope for Phase 0. Revisit when a phase actually needs vector search.

- **Phase 1 package layout.** Roadmap.md's flat `backend/core/` example was
  not followed. All Phase 1+ code lives under the src-layout package
  established in Phase 0 (`backend/src/autoeval_ops/`), i.e.
  `backend/src/autoeval_ops/core/`. CLI runs as
  `python -m autoeval_ops.core.cli`, not `python -m backend.core.cli`.
  The empty `backend/core/`, `backend/github/`, `backend/api/`,
  `backend/observability/` folders from Phase 0 are unused going forward.

- **detoxify dropped from requirements.txt.** Its dependency chain
  (transformers -> tokenizers==0.12.1 -> pyo3==0.12.4) is unmaintained
  and fails to build from source on Windows (both a Rust compile error
  on Python 3.13, and a linker "Access is denied" flake on Python 3.11).
  ToxicityEvaluator was already designed with a pluggable scorer, so the
  code needs no changes — cli.py falls back to NullToxicityScorer, and
  tests use FakeScorer, never the real model. Revisit in a later phase,
  e.g. swapping in a modern transformers+tokenizers pipeline (which do
  have current Windows wheels) pointed at a public toxicity model.

---

## Known Issues / Gotchas for Future Sessions

- **`autoeval_postgres` vs `autoeval_pgvector` split.** Don't attempt `CREATE EXTENSION vector` inside `autoeval_postgres` — it will fail (`extension "vector" is not available`). Vector work belongs in `autoeval_pgvector` on port 5433, with its own DB name (`${POSTGRES_DB}_vectors`).
- **PowerShell here-string paste issues.** Pasting `@' ... '@` blocks directly into a live PowerShell terminal can leave literal `@'`/`'@` lines in the target file instead of executing as a command. `notepad <file>` + manual paste proved more reliable for this project. Watch for stray `@'`/`'@` lines if a config/env file ever looks malformed.
- **`docker-compose.yml` still has `version: '3.8'`.** This field is obsolete in current Docker Compose and produces a harmless warning on every `docker-compose` command. Not fixed as part of Phase 0 since it doesn't block functionality — safe to strip later.
- **`.env` contains only placeholder values** (`dev_password`, empty API keys). Fine for local dev; must be replaced with real secrets before any deployment — never commit real values into `.env.example`.

---

## Next Step: Phase 1 — Core Evaluation Engine

See `Roadmap.md` (this project's `DEVELOPMENT_ROADMAP.md`) for the full task breakdown. Summary:

- Build `Evaluator` base class + concrete evaluators (Correctness, Toxicity, Hallucination, Cost, Latency) in `backend/core/`
- Build async `EvaluationPipeline` (asyncio.gather across evaluators)
- Unit tests, 95%+ coverage, mocked LLM calls
- CLI tool (`python -m backend.core.cli evaluate ...`)
- Benchmark 10/100/1000 parallel evals, document in `BENCHMARK.md`

Per `CLAUDE.md`'s golden rule: do not begin Phase 1 until this status doc is reviewed and Phase 0 is reconfirmed complete in that session.
