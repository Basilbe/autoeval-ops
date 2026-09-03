\# Architecture



AutoEvalOps is two deployed services sharing one Postgres database: a

FastAPI backend that does all the real work, and a Next.js dashboard

that reads from it. Everything below reflects what's actually running,

not an idealized design — six phases of real end-to-end testing shaped

several of these choices away from the original plan.



\## System diagram



```

┌─────────────┐      webhook       ┌──────────────────────────┐

│   GitHub     │ ─────────────────► │   FastAPI backend         │

│ (PR events)  │                    │   (Render)                 │

└─────────────┘                    │                            │

&#x20;                                   │  ┌──────────────────────┐  │

&#x20;     PR comment ◄──────────────── │  │ Webhook receiver      │  │

&#x20;     posted back                  │  │  → HMAC verify        │  │

&#x20;                                   │  │  → enqueue job         │  │

&#x20;                                   │  └──────────┬───────────┘  │

&#x20;                                   │             ▼               │

&#x20;                                   │  ┌──────────────────────┐  │

&#x20;                                   │  │ asyncio.Queue          │  │

&#x20;                                   │  │ (in-process, no        │  │

&#x20;                                   │  │  external broker)      │  │

&#x20;                                   │  └──────────┬───────────┘  │

&#x20;                                   │             ▼               │

&#x20;                                   │  ┌──────────────────────┐  │

&#x20;                                   │  │ Orchestrator            │  │

&#x20;                                   │  │  → find changed prompts │  │

&#x20;                                   │  │  → run test cases        │  │

&#x20;                                   │  │  → 5 evaluators (parallel)│ │

&#x20;                                   │  └──────────┬───────────┘  │

&#x20;                                   │             ▼               │

&#x20;                                   │  ┌──────────────────────┐  │

&#x20;                                   │  │ Persistence (best-      │  │

&#x20;                                   │  │  effort — never blocks  │  │

&#x20;                                   │  │  the PR comment)         │  │

&#x20;                                   │  └──────────┬───────────┘  │

&#x20;                                   └─────────────┼──────────────┘

&#x20;                                                 ▼

&#x20;                                   ┌──────────────────────────┐

&#x20;                                   │   PostgreSQL (Render)      │

&#x20;                                   │  users · orgs · projects   │

&#x20;                                   │  evaluations · eval\_results│

&#x20;                                   │  traces                    │

&#x20;                                   └──────────────┬─────────────┘

&#x20;                                                   ▲

&#x20;                                   ┌──────────────────────────┐

&#x20;                                   │   Next.js dashboard        │

&#x20;                                   │   (Vercel)                 │

&#x20;                                   │  Clerk auth · REST calls   │

&#x20;                                   │  to the FastAPI backend    │

&#x20;                                   └──────────────────────────┘

```



\## Components



\### Evaluation engine (`core/`)



Five evaluators, each implementing a shared `Evaluator` interface:

correctness (LLM-as-judge scoring against an expected output),

toxicity, hallucination (lexical overlap between output and provided

context — embeddings/pgvector deliberately deferred), cost (character-

based token estimate), and latency. They run concurrently via

`asyncio.gather` inside `EvaluationPipeline`, bounded by a semaphore.



The model itself is abstracted behind an `LLMClient` protocol —

`EchoLLMClient` (a fixed placeholder, used when no API key is

configured) and real clients for Gemini and OpenAI are interchangeable.

Nothing above this layer knows which one is active.



\### GitHub integration (`github/`)



\- `app\_auth.py` — GitHub App JWT signing and installation token exchange

\- `webhook.py` — HMAC-SHA256 signature verification, filters to

&#x20; relevant PR events only

\- `queue.py` — the `asyncio.Queue` worker pool; a job failure here

&#x20; doesn't take down the worker, it logs and continues

\- `orchestrator.py` — the actual per-PR flow: find changed prompt

&#x20; files, match each to its test cases, run the pipeline, format and

&#x20; post the PR comment, persist results



\### Backend API (`api/`, `db/`)



REST endpoints for users, organizations, projects, and evaluations,

secured by two independent auth paths that converge on the same

`User` model: bcrypt-hashed API keys (machine-to-machine, e.g. this

documentation's local curl examples) and Clerk JWT verification (the

dashboard). A Clerk login with no matching backend user is

auto-provisioned on first sight rather than rejected — signing up

through the dashboard is enough; no separate registration step.



`db/repository.py` centralizes every database access — routes and the

orchestrator both go through it, never touching SQLAlchemy sessions

directly.



\### Observability (`observability/`)



OpenTelemetry spans wrap the orchestrator and the evaluation pipeline

— one parent span per PR evaluation, one child span per evaluator,

each carrying its metric result as a span attribute. Exported via OTLP

to Jaeger locally; disabled in production (`OTEL\_ENABLED=false`) since

no hosted trace backend is deployed yet.



Aggregate metrics (`observability/metrics.py`) are computed from

Postgres on each request to `/api/v1/status` — no in-memory counters,

so a server restart doesn't reset the numbers.



\### Dashboard (`dashboard/`)



Next.js App Router, Server Components fetching directly from the

FastAPI backend with a Clerk-issued bearer token. Auth is checked

per-page (`redirect()` if unauthenticated) rather than via middleware

route-matching — Clerk's own current guidance, adopted after their

middleware-based `.protect()` API was deprecated mid-project. A thin

`proxy.ts` still exists solely to establish the auth context `auth()`

reads inside each page.



\## Data model



Six tables, all created in Phase 0 and evolved via Alembic migrations

since Phase 3: `users`, `organizations`, `projects`, `evaluations`,

`eval\_results`, `traces`. A project is uniquely identified by its

normalized GitHub repo URL — enforced at the database level, added in

Phase 6 after a real bug where two projects silently pointed at the

same repo.



\## Deliberate gaps



\- \*\*No hosted trace backend in production.\*\* Jaeger is local-only;

&#x20; `OTEL\_ENABLED=false` in deployment. The code path is fully built and

&#x20; guarded — adding a hosted backend (Tempo, Honeycomb) is a config

&#x20; change, not new code.

\- \*\*ClickHouse was never added.\*\* The `traces` table lived in Postgres

&#x20; from Phase 0 and stayed there — a second analytics database was

&#x20; never justified by actual trace volume.

\- \*\*Free-tier hosting, not built for scale.\*\* Render's free tier

&#x20; sleeps after inactivity; this is a portfolio deployment, not a

&#x20; production SLA. See `POSTMORTEM.md` for load test results and honest

&#x20; context on what free-tier limits actually cap out at.



\## Plan vs. reality



`docs/ARCHITECTURE\_ORIGINAL\_PLAN.md` is the Phase 0 design doc, written

before any code existed. Most of it held up. A few things it specified

never actually got built, and are worth naming rather than quietly

dropping:



\- \*\*GitHub token encryption (AES-256-GCM).\*\* The `projects` table has

&#x20; a `github\_token\_encrypted` column, but nothing in `db/repository.py`

&#x20; ever encrypts a value before writing to it — confirmed absent by

&#x20; direct search, not an oversight in this doc. In practice this hasn't

&#x20; mattered because the deployed system authenticates as a GitHub App

&#x20; (JWT + short-lived installation tokens), not long-lived per-user

&#x20; PATs, so there's no plaintext token actually being stored today. But

&#x20; the column and the original design intent exist for a future where

&#x20; that might change, and the encryption itself doesn't.

\- \*\*LLM API retry logic.\*\* The plan specified 2 retries on a failed

&#x20; LLM call; `llm\_client.py` has none — a failure propagates immediately

&#x20; rather than retrying. Real gap, not yet hit in practice because

&#x20; Gemini's free tier has been reliable during development, but worth

&#x20; fixing before this sees real traffic volume.

\- \*\*Redis + Celery\*\* were installed as a hedge in Phase 2 but never

&#x20; used — `asyncio.Queue` was the real, final choice for the task queue,

&#x20; not a temporary MVP stand-in as the original plan framed it.

\- \*\*WebSocket-based real-time updates (planned for "Phase 6")\*\* never

&#x20; happened — there is no Phase 7, and the dashboard uses plain

&#x20; server-rendered fetches with no live-update mechanism.

\- \*\*Datadog in production\*\* was never wired up; see "Deliberate gaps"

&#x20; above.



Full account of what broke during development, and why each of these

decisions was made when it was, is in

\[`POSTMORTEM.md`](POSTMORTEM.md).

