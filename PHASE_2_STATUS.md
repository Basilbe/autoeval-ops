# Phase 2 Complete — 2026-08-13

Verified against every "Task N Done When" checklist in `PHASE_2_SETUP_POWERSHELL.md` (Tasks 0-14). All 15 tasks: **PASS**. 75/75 tests passing, 99% coverage, no warnings. Committed to `main` (`4324a89`), working tree clean, local `main` == `origin/main`.

---

## What Was Built

**GitHub App authentication** (`github/app_auth.py`): `GitHubAppAuth` signs a JWT with the App's private key (RS256), exchanges it for a short-lived installation access token via GitHub's REST API, and caches each installation's token until shortly before expiry.

**GitHub API client** (`github/client.py`): thin async wrapper on `httpx` — `get_pr_files`, `get_file_content` (base64-decoded), `post_pr_comment`.

**PromptRunner** (`github/runner.py`): renders a prompt template against a list of test cases through an injected `LLMClient`, producing per-case outputs shaped for `EvaluationPipeline`, with latency measured per call. Not in `Roadmap.md`'s original task list — added because evaluation has nothing real to score without it.

**EvaluationQueue** (`github/queue.py`): in-process `asyncio.Queue` + worker pool (`EvaluationQueue`, module-level `eval_queue` singleton). A bad job logs and moves on; it doesn't take down a worker.

**PR comment formatter** (`github/comment.py`): renders an `EvaluationReport` list into a Markdown results table, with an overall PASS/WARN/FAIL rollup.

**Orchestrator** (`github/orchestrator.py`): wires GitHub API access, `PromptRunner`, and Phase 1's `EvaluationPipeline` together for one PR job — finds changed `prompts/*.txt` files, loads the matching `eval/*.test_cases.json`, runs the prompt, evaluates the outputs, and posts the comment. Its path-derivation helper is named `resolve_test_cases_path` (not `test_cases_path_for`) specifically so pytest doesn't mistake it for a test function during collection.

**Webhook receiver** (`github/webhook.py`): verifies GitHub's HMAC-SHA256 signature on every request, filters to `pull_request` events with a relevant action (`opened`/`synchronize`/`reopened`), and enqueues an `EvalJob`.

**Minimal FastAPI server** (`server.py`): loads the GitHub App's private key via `resolve_repo_path`, starts the queue workers on lifespan startup and stops them on shutdown, exposes `/health`, and mounts the webhook router. Also not in `Roadmap.md`'s original task list — added now so there's something to actually receive the webhook; Phase 3 expands it rather than replacing it.

**Test suite**: 75 tests (43 from the Task 0 refactor checkpoint + 29 across Tasks 3-9 + 2 from `test_server.py` + 1 regression test added during Task 13), **99% coverage** (390 stmts, 5 missed), 0 warnings.
```
pytest -v --cov=autoeval_ops --cov-report=term-missing
75 passed in 2.41s
TOTAL   390 stmts   5 missed   99%
```

---

## Scope Decisions Confirmed for This Phase

- **Full GitHub App** (JWT auth + installation tokens), not a simplified PAT+webhook — matches the original Phase 2 scope decision in the setup guide.
- **httpx over PyGithub** for all GitHub API calls, matching `TECH_STACK.md`'s async commitment. `PyGithub` stays listed in `requirements.txt`, unused.
- **asyncio-based queue over Celery** — `EvaluationQueue` runs in-process via `asyncio.Queue`. Redis stays unused until a later phase adopts Celery for production-grade durability/distribution.
- **Two structural additions beyond `Roadmap.md`'s original task list**: `PromptRunner` (necessary for evaluation to mean anything — without it there's no real model output to score) and the minimal `server.py` (expanded, not replaced, in Phase 3).

---

## The config.py Bugfix

`Settings.env_file = ".env"` was previously resolved relative to the current working directory, not to `config.py`'s location. This silently worked in Phase 1 because no tested value actually depended on a real `.env` read. In Phase 2, the GitHub App's ID, private key path, and webhook secret must load correctly regardless of which folder the server is launched from. Fixed via an absolute `_REPO_ROOT` path (`Path(__file__).resolve().parents[3]`) and a `resolve_repo_path()` helper, plus `extra = "ignore"` so `.env` keys not yet declared as `Settings` fields (Phase 0/3+ keys like `POSTGRES_*`, `CLERK_*`) don't raise a validation error.

A follow-up fix landed after the initial Phase 2 commit: the original class-based `class Config: env_file = ...; extra = "ignore"` pattern is deprecated in Pydantic v2 and only started emitting `PydanticDeprecatedSince20` once Phase 2's `webhook.py`/`server.py` actually imported and instantiated `Settings` in tests (Phase 1 never did). Replaced with `model_config = SettingsConfigDict(env_file=..., extra="ignore")`. Warning is gone; 74 tests still passed at that checkpoint.

---

## Tooling Note: ngrok → Cloudflare Tunnel

Originally planned with ngrok for local webhook testing. Switched to Cloudflare Tunnel (`cloudflared`) after ngrok's Windows binary was persistently blocked by security software across three separate install/download methods (browser download, direct HTTP via `Invoke-WebRequest`, and `winget install`) — consistent with security software flagging tunneling tools specifically. `cloudflared` installed cleanly via `winget install --id Cloudflare.cloudflared` with no equivalent issues. Its free quick-tunnel mode issues a new random `*.trycloudflare.com` URL on every restart (no reserved/static domain, unlike ngrok's offering), which was fine for one-time local verification — a permanent host is Phase 6's job.

---

## Task 13: Real End-to-End Webhook Test — CONFIRMED SUCCESSFUL

A real PR (PR #1, `Basilbe/autoeval-ops`) triggered GitHub's webhook against the `cloudflared` tunnel. The full path ran live: signature verification → job enqueued → `GitHubAppAuth` exchanged the App's JWT for an installation token → `GitHubClient` fetched the changed prompt file and its test cases → `PromptRunner` generated outputs → `EvaluationPipeline` scored them → `format_comment` rendered the table → `GitHubClient.post_pr_comment` posted it. A comment from the GitHub App appeared on the PR with a results table showing correctness 50/50 (FAIL — expected, since `EchoLLMClient`'s fixed `"50"` response sits right at a 70-point pass threshold with no real `OPENAI_API_KEY` set), toxicity 0/0, hallucination 0/0, cost $0.0006, latency 0ms. No unhandled errors appeared in the uvicorn terminal. Visually confirmed directly by the project owner.

### Two bugs found and fixed via this real test (not caught by mocked unit tests)

1. **`PromptRunner` crashed on literal curly braces in a prompt template.** `runner.py` originally rendered templates with `prompt_template.format(text=case.get("input", ""))`. `str.format` interprets *every* `{...}` in the template, so any prompt asking the model to "return as `{"summary": "..."}`" (or any other literal brace) raised a `KeyError`. All of Phase 2's mocked unit tests used brace-free templates, so this never surfaced until a real prompt hit it. Fixed by switching to `prompt_template.replace("{text}", case.get("input", ""))`, which only substitutes the one known placeholder and leaves every other brace untouched. Regression test added: `test_runner_tolerates_literal_braces_in_template` (`backend/tests/github/test_runner.py`). Committed separately after the Task 0/Task 12 fixes, at `4324a89`.
2. **Content mistake, not a code bug**: while manually editing `prompts/summarize.txt` through GitHub's web UI to trigger the test PR, the `{text}` placeholder itself was accidentally overwritten with literal wording. This broke rendering on that test branch specifically — since fixed there. The repo root's `prompts/summarize.txt` on `main` was never affected and still reads `"Summarize the following text in one sentence: {text}"` exactly as Task 11 created it.

---

## DB Persistence: Deferred to Phase 3

The orchestrator currently runs **entirely in-memory** — `handle_eval_job` fetches PR files, runs the prompt, evaluates it, and posts the PR comment, but writes nothing to Postgres. No `evaluations` or `eval_results` rows are created for any run, including the confirmed Task 13 test. Phase 3's SQLAlchemy ORM models (per `Roadmap.md`) need to retrofit the orchestrator to persist each evaluation run — project, commit hash, prompt version, per-metric results — to the database *alongside* posting the comment, not replace the comment-posting behavior.

---

## Known Simplifications Worth Flagging for a Future Phase

- **No retry logic on failed GitHub API calls.** A transient failure in `get_pr_files`, `get_file_content`, or `post_pr_comment` propagates straight up; `EvaluationQueue`'s worker logs it and moves to the next job, but that job's evaluation is simply lost, not retried.
- **No rate-limit handling for GitHub's API.** No backoff or `X-RateLimit-*` header awareness — a burst of PRs could hit GitHub's rate limit with no graceful degradation.
- **Single prompt-file-naming convention** (`prompts/*.txt` paired with `eval/*.test_cases.json`). Multiple prompt formats, subdirectories, or naming schemes aren't supported yet.
- **The `cloudflared` quick-tunnel URL requires manual re-entry** into the GitHub App's webhook settings every session, since the free tier has no static/reserved domain. Phase 6's real deployment provides a permanent host and removes this friction entirely.

---

## Next Step: Phase 3 — Backend API

See `Roadmap.md` for the full task breakdown. Phase 3's API layer and SQLAlchemy ORM models are what finally close the persistence gap left open here — retrofitting the orchestrator to write each evaluation run to Postgres alongside posting the PR comment, plus the core FastAPI endpoints (`/api/v1/projects`, `/api/v1/projects/{id}/evals`, etc.), authentication, and rate limiting.

Per `CLAUDE.md`'s golden rule: do not begin Phase 3 until this status doc is reviewed and Phase 2 is reconfirmed complete in that session.
