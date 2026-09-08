# Phase 6 Complete — 2026-09-08

Verified against every "Task N Done When" checklist in `PHASE_6_SETUP_POWERSHELL.md` (Task 1 through Task 14; Task 13 deliberately deferred by user decision — see below). All items either **PASS** or **DEFERRED BY USER DECISION**, with the two flagged gaps from the initial audit (doc-encoding corruption, missing 409 test coverage) since fixed and reconfirmed. **152/152 tests passing, 98% coverage (982 statements, 18 missed), 0 warnings.** Committed to `main` (`5871f2b`), working tree clean, local `main` == `origin/main`.

This closes the project. All six phases from `Roadmap.md` are now complete.

---

## What Was Built

**Deployment.** Backend on Render, dashboard on Vercel, permanent webhook URL. Render specifically because the `asyncio.Queue` worker pool needs a persistent process, which serverless platforms can't provide — a managed Postgres database runs alongside it. This ended the `cloudflared` tunnel dance that every prior phase's webhook testing depended on; the GitHub App's webhook URL now points at a stable domain that never changes between sessions.

**Self-service.** The Add Project UI (`AddProjectForm.tsx` + a `"use server"` action in `actions.ts`) replaces four phases of hand-typed `Invoke-RestMethod` calls with a Clerk token copied out of DevTools. The token now stays server-side end to end.

**Real evaluation.** `GeminiLLMClient` added alongside `OpenAILLMClient`, both behind the `LLMClient` protocol built in Phase 1 specifically for this kind of swap. `build_llm_client` checks `GOOGLE_API_KEY` first. Every score across the previous five phases came from `EchoLLMClient`'s placeholder `50` — this is the first phase producing genuine, varying scores from a real model.

**Correctness.** A unique constraint on `projects.github_repo_url`, fixing the Phase 4 bug where two projects silently collided on one repo and evaluations were attributed to the wrong one. `POST /api/v1/projects` now returns `409` instead of a raw database error, and the whole path is covered by three tests added this phase — including the normalized-URL case (`https://github.com/o/r` vs. `o/r`), the form most likely to regress.

**Observability/ops.** Sentry, deferred from Phase 5 because there was no production deployment to attach it to — that deployment now exists. CI (`.github/workflows/test.yml`) runs the backend suite against a Postgres service container on every push and PR to `main`. Load testing against the live deployed backend. A focused security pass (rate limiting, CORS, webhook HMAC, bcrypt-hashed API keys, secret-history scan).

**Documentation.** `README.md`, `docs/ARCHITECTURE.md`, and `docs/POSTMORTEM.md` written from scratch this phase; `docs/TECH_STACK.md` reconciled against what actually shipped, with the original Phase 0 lock preserved alongside it for comparison.

---

## Scope Decision Confirmed for This Phase

`Roadmap.md`'s Phase 6 is written as a SaaS launch checklist — CI/CD, custom domain, 500+ RPS load testing, a full security audit, a marketing/pricing page. That's the right list for an actual product launch, but this project's real goal was narrower and sharper: **a stranger should be able to see this work in under two minutes, and use it on their own repo without anyone sitting next to them running PowerShell.**

The phase was resequenced around that goal rather than `Roadmap.md`'s original ordering, and documented as such in the setup guide's Scope Decisions section rather than done silently: friction-removal was front-loaded (permanent deployment, the Add Project UI, a real LLM API key, the repo-uniqueness fix), the showcase items came second (README, POSTMORTEM, the deferred design pass), and the remaining roadmap items — Sentry, security, load testing, CI — were kept in scope but not over-indexed on, since none of them make or break a two-minute first impression.

---

## Real Bugs Found and Fixed This Phase

1. **`DATABASE_URL` scheme mismatch.** Render hands out `postgresql://`; this project's asyncpg driver needs `postgresql+asyncpg://`. The same root cause as Phase 3's local `.env` issue, resurfacing in a new environment. Fixed with an `async_database_url` property on `Settings` so the platform's value can be used verbatim, with both `db/session.py` and `alembic/env.py` reading through it.

2. **A real `GOOGLE_API_KEY` was committed to `.env.example`.** Caught by GitHub's push protection before it ever reached the remote. Fixed by amending the commit before pushing; the key was rotated regardless, on the assumption that anything that touched a local commit should be treated as potentially exposed.

3. **Sentry's init block was placed above the `settings` import**, producing `NameError: name 'settings' is not defined` on deploy — caught immediately from Render's log, not from local testing (Sentry only meaningfully initializes with a real `SENTRY_DSN`, which wasn't set locally). Fixed by moving the init block after the settings import and before `configure_tracing()`.

4. **Render's Blueprint flow prompted for a credit card** even on the free tier, specific to provisioning a web service and a database together via Blueprint. Resolved by creating the database and web service individually through Render's dashboard forms instead, entering `render.yaml`'s values by hand — confirmed not to prompt for a card.

5. **Clerk's Domains page turned out to be irrelevant** — it only applies to Production Clerk instances requiring a DNS-verified custom domain, not to the Development instance this project runs on. A step in the original setup guide assumed it was needed for the Vercel deployment; that assumption was wrong and has been corrected in the guide.

---

## Load Testing Results

Full detail, including both tables, is in `docs/POSTMORTEM.md`. In brief: zero failures at both 5 and 200 concurrent users against the live deployed backend, but throughput plateaued at roughly **47 RPS** regardless of concurrent load, with median latency on `/api/v1/status` rising 27x (180ms → 5,000ms) between the two runs. Root cause confirmed directly from Render's own deploy log, not inferred:

```
==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
```

A single worker process on a single CPU. Against `Roadmap.md`'s original 500+ RPS target, this deployment reaches roughly 9% of that under load — a hosting-tier ceiling, not an application defect, and fixable with infrastructure spend (a paid tier, `WEB_CONCURRENCY` above 1, multiple instances behind a load balancer) rather than a rewrite.

---

## Known Gaps — Deliberately Deferred, Not Hidden

- **Task 13 (design polish pass)** — deferred by user decision to after all phases are complete, not skipped and not a FAIL.
- **The frontend has zero automated tests.** Jest + React Testing Library were in the original Phase 0 tech stack lock and never actually set up — surfaced during Task 9's `TECH_STACK.md` reconciliation, confirmed by direct search (no config file, no test files anywhere under `dashboard/`), and logged in `docs/POSTMORTEM.md`.
- **GitHub token AES-256-GCM encryption and LLM API retry logic** were both in the Phase 0 plan and never built. Both confirmed absent by direct search of `db/repository.py` and `llm_client.py` respectively, and both documented in `docs/ARCHITECTURE.md`'s "Plan vs. reality" section.
- **No hosted trace backend in production** — `OTEL_ENABLED=false` in the deployed environment; Jaeger remains local-development-only.
- **`routes/projects.py` line 43** (the `GET /api/v1/projects` list-endpoint body) remains untested — a pre-existing gap, unrelated to this phase's changes, and not part of what this phase set out to fix.

---

## Final Test Suite

```
cd backend
.venv\Scripts\Activate.ps1
pytest -v --cov=autoeval_ops --cov-report=term-missing

152 passed in 80.75s
TOTAL   982 stmts   18 missed   98%
```

`routes/projects.py` specifically improved from 93% to 96% this phase (27 stmts, 2 missed → 1 missed) — the 409 duplicate-repo branch added in Task 1 is now covered by three dedicated tests, including the normalized-URL case.

---

## What This Project Is Now

A deployed, self-service CI/CD platform for LLM prompts: a stranger can sign up, install the GitHub App, add a project, and get real evaluation scores on their own pull requests without ever touching a terminal. Six phases of honestly-documented engineering sit behind it — including a preserved record of where the original Phase 0 plan and the built reality diverged, and why, rather than a quietly rewritten history that pretends the plan was followed exactly.
