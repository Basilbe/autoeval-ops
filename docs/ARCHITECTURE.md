# Architecture



AutoEvalOps is two deployed services sharing one Postgres database: a

FastAPI backend that does all the real work, and a Next.js dashboard

that reads from it. Everything below reflects what's actually running,

not an idealized design — six phases of real end-to-end testing shaped

several of these choices away from the original plan.



## System diagram



```

┌─────────────┐      webhook       ┌──────────────────────────┐

│   GitHub     │ ─────────────────► │   FastAPI backend         │

│ (PR events)  │                    │   (Render)                 │

└─────────────┘                    │                            │

                                    │  ┌──────────────────────┐  │

      PR comment ◄──────────────── │  │ Webhook receiver      │  │

      posted back                  │  │  → HMAC verify        │  │

                                    │  │  → enqueue job         │  │

                                    │  └──────────┬───────────┘  │

                                    │             ▼               │

                                    │  ┌──────────────────────┐  │

                                    │  │ asyncio.Queue          │  │

                                    │  │ (in-process, no        │  │

                                    │  │  external broker)      │  │

                                    │  └──────────┬───────────┘  │

                                    │             ▼               │

                                    │  ┌──────────────────────┐  │

                                    │  │ Orchestrator            │  │

                                    │  │  → find changed prompts │  │

                                    │  │  → run test cases        │  │

                                    │  │  → 5 evaluators (parallel)│ │

                                    │  └──────────┬───────────┘  │

                                    │             ▼               │

                                    │  ┌──────────────────────┐  │

                                    │  │ Persistence (best-      │  │

                                    │  │  effort — never blocks  │  │

                                    │  │  the PR comment)         │  │

                                    │  └──────────┬───────────┘  │

                                    └─────────────┼──────────────┘

                                                  ▼

                                    ┌──────────────────────────┐

                                    │   PostgreSQL (Render)      │

                                    │  users · orgs · projects   │

                                    │  evaluations · eval_results│

                                    │  traces                    │

                                    └──────────────┬─────────────┘

                                                    ▲

                                    ┌──────────────────────────┐

                                    │   Next.js dashboard        │

                                    │   (Vercel)                 │

                                    │  Clerk auth · REST calls   │

                                    │  to the FastAPI backend    │

                                    └──────────────────────────┘

```



## Components



### Evaluation engine (`core/`)



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



### GitHub integration (`github/`)



- `app_auth.py` — GitHub App JWT signing and installation token exchange

- `webhook.py` — HMAC-SHA256 signature verification, filters to

  relevant PR events only

- `queue.py` — the `asyncio.Queue` worker pool; a job failure here

  doesn't take down the worker, it logs and continues

- `orchestrator.py` — the actual per-PR flow: find changed prompt

  files, match each to its test cases, run the pipeline, format and

  post the PR comment, persist results



### Backend API (`api/`, `db/`)



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



### Observability (`observability/`)



OpenTelemetry spans wrap the orchestrator and the evaluation pipeline

— one parent span per PR evaluation, one child span per evaluator,

each carrying its metric result as a span attribute. Exported via OTLP

to Jaeger locally; disabled in production (`OTEL_ENABLED=false`) since

no hosted trace backend is deployed yet.



Aggregate metrics (`observability/metrics.py`) are computed from

Postgres on each request to `/api/v1/status` — no in-memory counters,

so a server restart doesn't reset the numbers.



### Dashboard (`dashboard/`)



Next.js App Router, Server Components fetching directly from the

FastAPI backend with a Clerk-issued bearer token. Auth is checked

per-page (`redirect()` if unauthenticated) rather than via middleware

route-matching — Clerk's own current guidance, adopted after their

middleware-based `.protect()` API was deprecated mid-project. A thin

`proxy.ts` still exists solely to establish the auth context `auth()`

reads inside each page.



## Data model



Six tables, all created in Phase 0 and evolved via Alembic migrations

since Phase 3: `users`, `organizations`, `projects`, `evaluations`,

`eval_results`, `traces`. A project is uniquely identified by its

normalized GitHub repo URL — enforced at the database level, added in

Phase 6 after a real bug where two projects silently pointed at the

same repo.



## Deliberate gaps



- **No hosted trace backend in production.** Jaeger is local-only;

  `OTEL_ENABLED=false` in deployment. The code path is fully built and

  guarded — adding a hosted backend (Tempo, Honeycomb) is a config

  change, not new code.

- **ClickHouse was never added.** The `traces` table lived in Postgres

  from Phase 0 and stayed there — a second analytics database was

  never justified by actual trace volume.

- **Free-tier hosting, not built for scale.** Render's free tier

  sleeps after inactivity; this is a portfolio deployment, not a

  production SLA. See `POSTMORTEM.md` for load test results and honest

  context on what free-tier limits actually cap out at.



## Plan vs. reality



`docs/ARCHITECTURE_ORIGINAL_PLAN.md` is the Phase 0 design doc, written

before any code existed. Most of it held up. A few things it specified

never actually got built, and are worth naming rather than quietly

dropping:



- **GitHub token encryption (AES-256-GCM).** The `projects` table has

  a `github_token_encrypted` column, but nothing in `db/repository.py`

  ever encrypts a value before writing to it — confirmed absent by

  direct search, not an oversight in this doc. In practice this hasn't

  mattered because the deployed system authenticates as a GitHub App

  (JWT + short-lived installation tokens), not long-lived per-user

  PATs, so there's no plaintext token actually being stored today. But

  the column and the original design intent exist for a future where

  that might change, and the encryption itself doesn't.

- **LLM API retry logic.** The plan specified 2 retries on a failed

  LLM call; `llm_client.py` has none — a failure propagates immediately

  rather than retrying. Real gap, not yet hit in practice because

  Gemini's free tier has been reliable during development, but worth

  fixing before this sees real traffic volume.

- **Redis + Celery** were installed as a hedge in Phase 2 but never

  used — `asyncio.Queue` was the real, final choice for the task queue,

  not a temporary MVP stand-in as the original plan framed it.

- **WebSocket-based real-time updates (planned for "Phase 6")** never

  happened — there is no Phase 7, and the dashboard uses plain

  server-rendered fetches with no live-update mechanism.

- **Datadog in production** was never wired up; see "Deliberate gaps"

  above.



Full account of what broke during development, and why each of these

decisions was made when it was, is in

[`POSTMORTEM.md`](POSTMORTEM.md).

