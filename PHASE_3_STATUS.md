# Phase 3 Complete — 2026-08-19

Verified against every "Task N Done When" checklist in `PHASE_3_SETUP_POWERSHELL.md` (Prerequisites through Task 17). All tasks: **PASS**. 131/131 tests passing, 98% coverage, 0 warnings. Committed to `main`, working tree clean, local `main` == `origin/main`.

---

## What Was Built

**SQLAlchemy ORM models** (`db/models.py`): all 6 Phase 0 tables (`users`, `organizations`, `projects`, `evaluations`, `eval_results`, `traces`), with nullability, defaults, and index names matching `db/schema.sql` exactly.

**Async session management** (`db/session.py`): lazily-created `AsyncEngine` (importing the module never opens a connection), pooled (`pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`), with `get_db()` as the FastAPI dependency (commit-on-success / rollback-on-exception) and `dispose_engine()` for clean shutdown.

**Alembic migrations** (`alembic/`): adopted in place of piping `schema.sql` into `docker exec`. The baseline migration is hand-authored with explicit `op.create_table` calls for all 6 tables rather than a thin `--autogenerate` diff. `db/schema.sql` is kept as a marked historical artifact.

**Repository layer** (`db/repository.py`): every database access for the phase goes through this module — `normalize_repo()` plus CRUD functions for users, organizations, projects, and evaluations. Routes and the orchestrator never write raw queries.

**Dual authentication** (`api/security.py`, `api/clerk.py`, `api/deps.py`): bcrypt-hashed API keys (`X-API-Key` header) as the fully-testable machine-to-machine path now, and Clerk JWT verification via JWKS (`Authorization: Bearer ...`) built and unit-tested against mocks/an injectable `http_client`, with live verification deferred to Phase 4.

**Four REST route groups** (`api/routes/`): users (register, `/me`, API key rotation), organizations, projects, and evaluations — all behind `get_current_user`.

**Orchestrator retrofit** (`github/orchestrator.py`): persists every evaluation run (project lookup, `create_evaluation`, `complete_evaluation`) alongside the existing Phase 2 PR-comment behavior, without replacing it.

**server.py expanded, not replaced**: adds the four API routers, CORS, and `slowapi` rate limiting on top of Phase 2's webhook router and queue lifespan.

**Test suite**: **131 tests**, **98% coverage** (842 statements, 18 missed), **0 warnings**.
```
pytest -v --cov=autoeval_ops --cov-report=term-missing
131 passed in ~20-55s (varies with greenlet+thread coverage tracing overhead)
TOTAL   842 stmts   18 missed   98%
```

---

## Scope Decisions Confirmed for This Phase

- **Projects must be pre-registered.** A webhook for an unregistered `owner/repo` is logged and skipped — it never auto-creates a `projects` row. Letting an unauthenticated webhook write to the database would let anyone point a webhook at the server and create arbitrary records.
- **Alembic adopted over ad-hoc `schema.sql` application.** All schema changes now go through migrations; `schema.sql` stays only as a historical record of what Phase 0 originally created.
- **Hybrid testing.** Business logic keeps using fakes (fast, no Docker required). A `@pytest.mark.integration` set hits real Postgres, each test wrapped in a transaction that rolls back (`tests/conftest.py`'s `db_session` fixture). Day-to-day, the fast set runs alone; the phase gate requires both, plus the full coverage run.
- **Both auth paths built now, but Clerk's live verification is deferred to Phase 4.** A real dashboard login is needed to produce genuine session tokens to verify against. Phase 3 tests Clerk's logic thoroughly — JWKS caching, cache-freshness/expiry, JWT signature verification, unknown-`kid` rejection — against a throwaway RSA keypair and an injectable `http_client` (`tests/api/test_clerk.py`), not a live Clerk account.

---

## Persistence Design Principle: A Database Failure Can Never Block a PR Comment

This isn't just documented as an intention — it's proven by a dedicated test, `test_comment_still_posts_when_database_is_unreachable` (`tests/github/test_orchestrator_persistence.py`), which points the orchestrator at a session factory that raises `ConnectionError` on every call and asserts the PR comment still posts exactly once.

---

## Real Bugs Found and Fixed Along the Way

1. **`DATABASE_URL` used the sync `postgresql://` scheme instead of `postgresql+asyncpg://`.** Phase 0's `.env` template used the scheme for the sync `psycopg2` driver; this project uses `asyncpg`. Nothing before Phase 3 actually opened a database connection, so this stayed invisible until Alembic and the API tried to connect. Fixed in both `.env` and `.env.example`.

2. **`alembic revision --autogenerate` against the live Phase-0-created database produced only ALTER-style diffs**, not a true from-scratch baseline — implicit `NOT NULL` mismatches, unnamed vs. named indexes, and `TEXT` vs. `String` type drift between what `schema.sql` created and what the ORM models declared. Resolved by hand-authoring the baseline migration with explicit `op.create_table` calls matching `schema.sql` exactly, and aligning `models.py`'s nullability, index names, and column types to match. `alembic check` now reports zero drift, and the migration can build the schema from nothing, not just diff against an already-populated database.

3. **`tests/test_server.py` and `tests/api/test_routes_auth.py` failed to collect** with `ImportError: email-validator is not installed`. `schemas.py`'s `UserCreate.email: EmailStr` requires the optional `email-validator` package, not bundled with base `pydantic`. Added to `requirements.txt`.

4. **`test_invalid_uuid_path_returns_422` failed (got 401 instead of 422)** — a FastAPI dependency-resolution ordering quirk, not an application bug. `get_current_user`'s `HTTPException(401)` fires as a real exception during dependency solving and propagates immediately, short-circuiting before FastAPI's automatic 422 for the invalid path parameter ever assembles. Fixed by adding an `authenticated_client` fixture that bypasses auth entirely, isolating path-validation testing from auth logic.

5. **`UserWarning: EvaluationRead.model_name has conflict with protected namespace "model_"`.** Pydantic v2 reserves the `model_` prefix for its own internals. Fixed with `protected_namespaces=()` on `ORMModel`'s `model_config`.

6. **The integration test file couldn't run at all initially, for two separate reasons:**
   - The `db_session` fixture lived only in `tests/db/conftest.py`, which pytest doesn't expose to sibling directories like `tests/api/`. Moved to the root `tests/conftest.py`, with `tests/db/conftest.py`'s `sample_user`/`sample_project` now depending on it from there.
   - Starlette's synchronous `TestClient` runs the ASGI app in a background thread via an `anyio` blocking portal, which crashed against the `db_session` fixture's same-loop asyncpg connection with `RuntimeError: ... Future ... attached to a different loop` the moment a route touched the database. Fixed by switching those tests to `httpx.AsyncClient` + `ASGITransport` — same app, same dependency overrides, but runs in-process on the test's own event loop.

7. **A three-round `coverage.py` investigation**, non-obvious enough to warrant its own subsection:

   Coverage sat at 87% after the first integration-test pass, concentrated in `deps.py`, the route modules, and `session.py` — code demonstrably being executed correctly (tests passed with the exact expected status codes) but not being recorded as covered.

   - **First hypothesis, tested and eliminated**: Starlette `TestClient`'s background thread (`concurrency = ["thread"]`). Per-line evidence ruled it out — the anomalous lines were reached through `httpx.AsyncClient` on the *same* event loop as the test, not through `TestClient`'s background thread at all. Coverage was byte-identical before and after applying this setting.
   - **Second hypothesis, confirmed correct**: SQLAlchemy's async ORM (`AsyncSession`/`AsyncEngine`) runs its internals bridged through a `greenlet` context — literally how SQLAlchemy 1.4+ async support is implemented — and `coverage.py`'s tracer does not follow greenlet context switches without an explicit `concurrency = ["greenlet"]` setting. Applying it resolved every one of the originally-anomalous lines in `deps.py`, `routes/evaluations.py`, `routes/projects.py`, `routes/users.py`, and `repository.py`.
   - **But switching to `"greenlet"` alone (replacing `"thread"` rather than adding to it) caused a real regression**: `webhook.py` and `server.py` dropped from 96%/98% to 39%/82%, because their tests (`tests/github/test_webhook.py`, `tests/test_server.py`) use the synchronous `TestClient` and lost thread-tracking the moment it was replaced instead of combined.
   - **Final fix**: `concurrency = ["thread", "greenlet"]` in `pyproject.toml`'s `[tool.coverage.run]`. Both mechanisms are needed *simultaneously* in any FastAPI + SQLAlchemy-async stack tested with a mix of `TestClient` and `httpx.AsyncClient`. Confirmed via a fully cleared cache (`.coverage`, `.pytest_cache`, all `__pycache__`) re-run: **131 tests, 98% coverage (842 statements, 18 missed)**, with `webhook.py`/`server.py` back to their prior 96%/98% and none of the greenlet-tracked fixes regressed.

   **Gotcha worth remembering**: anyone running `coverage.py` against a FastAPI + SQLAlchemy-async stack, tested with a mix of `TestClient` (thread-based) and `httpx.AsyncClient`/`ASGITransport` (same-loop), needs `concurrency = ["thread", "greenlet"]` — not one or the other. `coverage.py`'s own docs don't prominently connect the `greenlet` setting to SQLAlchemy specifically, so this is easy to miss and will silently under-report coverage on exactly the routes/dependencies that touch the database, while looking like a real test gap rather than a tooling gap.

---

## Known Gaps (All Deliberate)

- **`db/session.py`'s `get_db`/`dispose_engine` bodies** — `# pragma: no cover`'d. Every test overrides `get_db` by design (unit tests with a fake, integration tests with the real `db_session` fixture directly), so the real generator body is structurally unreachable in this suite, the same category as `cli.py`'s `main()` from Phase 1.
- **`clerk.py`'s two network-calling code paths, where genuinely untestable** — most of `clerk.py` *is* tested, via `httpx.MockTransport` and a throwaway RSA keypair (`tests/api/test_clerk.py`): `__init__`, cache-freshness/expiry, JWKS fetch-and-cache, full JWT verification round-trip, and unknown-`kid` rejection. Only the methods that would require a live Clerk account stay excluded.
- **The Clerk-success branch in `deps.py`** (`deps.py:45-48,64`) — genuinely untestable without a full successful Clerk JWT round-trip through `get_current_user`. Deferred to Phase 4, once a real dashboard can produce genuine session tokens.
- **One untested endpoint**: `routes/projects.py:35`, the authenticated `GET /api/v1/projects` (list-all) handler. No test currently calls it with valid auth. Low-risk — it follows the exact same pattern as every other list endpoint that *is* tested — but flagged explicitly as a real gap rather than silently left out.

---

## Task 15 and Task 16: Confirmed Successful by Direct User Verification

Both were flagged pending in the initial audit, consistent with how Task 13 was handled in the Phase 2 status doc. Both are now confirmed directly by the project owner, not just inferred from database state:

- **Task 15 (manual API walkthrough)**: register → API key issued → authenticate with the key → create organization → create project → list evaluations, worked end-to-end exactly as specified.
- **Task 16 (webhook-to-database)**: a real webhook fired, the orchestrator persisted an evaluation row to Postgres, and a PR comment posted — the same confirmed flow as Phase 2's Task 13, now with persistence alongside it. The evaluation showed the expected `EchoLLMClient`/70-point-threshold FAIL pattern seen throughout this project whenever a real `OPENAI_API_KEY` isn't set — consistent, not a new anomaly.

---

## Next Step: Phase 4 — Frontend Dashboard

See `Roadmap.md` for the full task breakdown. Two things to decide explicitly at Phase 4's kickoff, not default into silently:

1. **Frontend tooling approach is intentionally left open.** `Roadmap.md`'s Phase 4 examples assume a hand-built Next.js dashboard, but nothing in Phase 3 constrains this — the backend only exposes JSON over HTTP, so any frontend approach works, including a visual-first tool if that turns out to be a better fit for iterating on UI. Decide and document the choice explicitly at kickoff, the same as every other deviation in this project.
2. **`CLERK_JWKS_URL` in `.env` is still blank.** It needs to be filled in once a real Clerk account exists — that's what finally makes Clerk's live login flow testable for the first time, closing out the one deliberate gap left open by this phase.

Per `CLAUDE.md`'s golden rule: do not begin Phase 4 until this status doc is reviewed and Phase 3 is reconfirmed complete in that session.
