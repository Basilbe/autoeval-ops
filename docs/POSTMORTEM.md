# Postmortem

Built over 4 weeks, 2026-08-10 to 2026-09-08, across six phases.



Six phases, roughly 4 weeks, one working product. This is

the honest account: what was traded off deliberately, what broke in

ways unit tests never would have caught, and what I'd do differently

starting over. Where `docs/ARCHITECTURE.md` describes what the system

is, this describes what it took to get there.



---



## Architectural trade-offs



**`asyncio.Queue` over Celery + Redis.** Redis and Celery were

installed as a hedge in Phase 2's `requirements.txt` and never used —

`asyncio.Queue` turned out to be enough for a single backend instance,

and running a message broker for a queue that never needed to survive

a process restart was overhead without benefit. The trade-off is real:

this doesn't scale past one instance without rework. Worth revisiting

if this ever needs horizontal scaling.



**Postgres for traces, not ClickHouse.** The `traces` table was

created in Phase 0's original schema and sat completely unused through

Phases 1–4 — nothing wrote to it until Phase 5. Standing up a second,

purpose-built analytics database before the first one had ever been

exercised would have been speculative infrastructure. Postgres handles

the actual trace volume this project sees without strain.



**Lexical-overlap hallucination checking, not embeddings.** pgvector

was scoped in Phase 0 and deferred at the same time — the hallucination

evaluator instead checks word overlap between output and provided

context. Cheaper, no vector index to maintain, meaningfully less

accurate than a real semantic-similarity check. A known, accepted

limitation, not an oversight.



**Character-count token estimation, not `tiktoken`.** The cost

evaluator estimates tokens at roughly 4 characters each rather than

using a real tokenizer. Avoided a dependency for arithmetic that only

needs to be approximately right for cost *estimation*, not billing

accuracy.



**Per-page auth checks, not middleware route-matching.** Originally

built with Clerk's `createRouteMatcher` + `auth().protect()` in

`middleware.ts`. Both Next.js (renaming `middleware` to `proxy`) and

Clerk (deprecating path-matching-based protection) moved away from

that pattern mid-project. Rebuilt to check `auth()` directly inside

each page instead — Clerk's own current recommendation, and arguably

more correct: it can't diverge from how Next.js actually routes a

request the way a centralized matcher can.



**Google Gemini by default, OpenAI supported.** Both implement the

same `LLMClient` protocol; `build_llm_client` checks `GOOGLE_API_KEY`

first. Gemini's free tier (rate-limited, not billed per call) fits a

project evaluated occasionally far better than paying OpenAI per

request — a cost decision made in Phase 6, once real scoring actually

mattered for the demo.



**GitHub token encryption and LLM retry logic were planned, never

built.** The original Phase 0 design specified both. Neither exists in

the current code — confirmed by direct search, not assumed. The

encryption gap matters less in practice than it sounds: the deployed

system authenticates via GitHub App JWT + short-lived installation

tokens, not stored long-lived PATs, so there's no plaintext secret

actually sitting in the `github_token_encrypted` column today. The

retry gap is a real, live limitation — a failed LLM call currently

propagates immediately rather than retrying, and hasn't been hit in

practice only because Gemini's free tier has been reliable during

development.



---



## Bugs that only real end-to-end testing caught



None of these were caught by unit tests — every one required an actual

webhook, an actual browser session, or an actual deploy to surface.



- **`PromptRunner`'s `str.format()` crashed on literal curly braces.**

  Every mocked test used brace-free prompt templates, so this was

  invisible until a real prompt file (containing `{` outside the

  `{text}` placeholder) hit the live webhook path. Fixed by switching

  to `.replace("{text}", ...)`.



- **`.env` resolved relative to the process's working directory, not

  the repo root.** Invisible through Phase 0–2 because nothing had

  opened a real config-dependent connection yet. Surfaced the moment

  Phase 3 needed a real database URL. Fixed with an absolute path

  resolved from `__file__`.



- **Antivirus HTTPS interception broke every outbound TLS call from

  the backend.** Avast's local scanning proxy injects its own root

  certificate — trusted by Windows, not by Python's bundled `certifi`

  list. This broke Clerk's JWKS fetch with an opaque

  `CERTIFICATE_VERIFY_FAILED`, and took three separate hypotheses (a

  wrong env var, a stale token, a Clerk config issue) before actually

  testing raw outbound HTTPS to `pypi.org` and finding it failed

  identically — proving it was systemic, not application-specific.

  Fixed with `truststore`, which makes Python trust the OS certificate

  store directly.



- **Clerk's default session token has no `email` claim.** `deps.py`'s

  auth path looks for one and found nothing, producing a 401

  indistinguishable from several other possible failures. Required

  granular `print()`-level tracing through the actual verification

  code to isolate — the fix was a Clerk Dashboard config change, not

  code.



- **A verified Clerk login still 401'd after the email-claim fix.** A

  Clerk login never automatically creates a backend `users` row — only

  the API-key registration flow did that. Fixed with just-in-time user

  provisioning (`get_or_create_user_by_email`), the standard pattern

  for exactly this situation.



- **Two projects silently pointed at the same GitHub repo.**

  `get_project_by_repo()` had no uniqueness handling, so the second

  registered project's evaluations silently attributed to the first

  one — no error, just data landing in the wrong place. Only visible

  by directly comparing what the dashboard showed against what should

  have been there. Fixed with a real database-level unique constraint

  in Phase 6, once self-service registration made the bug not just

  possible but likely.



- **`Test-Path` misinterpreted Next.js's `[id]` dynamic-route folder

  syntax as a PowerShell wildcard.** A pure tooling gotcha, not an app

  bug — cost real debugging time chasing "missing" files that were

  actually present the whole time. `-LiteralPath` was the fix.



---



## Testing insights



**The `coverage.py` investigation.** Coverage sat at 87% after adding

integration tests, concentrated in code that was demonstrably being

executed correctly — tests passed with exactly the expected status

codes, but the lines weren't recorded as covered. Two wrong hypotheses

before the right one: first suspected Starlette's `TestClient`

background thread (`concurrency = ["thread"]`) — eliminated with

per-line evidence, since the affected lines were reached through

`httpx.AsyncClient` on the same event loop, not `TestClient` at all.

The actual cause: SQLAlchemy's async ORM bridges through a `greenlet`

context that `coverage.py` doesn't trace without an explicit

`concurrency = ["greenlet"]` setting. Applying it fixed every

anomalous line — but switching to `"greenlet"` alone then regressed

two files that *did* depend on thread-tracing. Final answer:

`concurrency = ["thread", "greenlet"]`, both together. Three real

rounds to isolate, and a genuinely non-obvious pitfall for anyone

running `coverage.py` against a FastAPI + SQLAlchemy-async stack.



**The same fixture-scope bug happened twice.** Phase 3 moved

`db_session` from `tests/db/conftest.py` up to the root

`tests/conftest.py` so sibling test directories could see it —

but left `sample_user`/`sample_project` behind. Phase 5 hit the exact

same class of failure the moment a new test directory

(`tests/observability/`) needed those fixtures. The lesson wasn't

learned the first time it mattered; only fixing the specific instance,

not the underlying pattern, meant it recurred.



**What mocked tests genuinely cannot catch.** Every phase in this

project ended in a live, manual walkthrough — not as a formality, but

because real bugs kept surfacing there and nowhere else: certificate

trust chains, OAuth claim shapes, race conditions between two

free-tier services waking up, PowerShell path-matching quirks. Mocking

the boundary is exactly what hides the bug that lives at the boundary.



---



## What I'd do differently



- **Build the "Add Project" UI in Phase 4, not Phase 6.** Every

  project registration for four phases went through hand-typed

  `Invoke-RestMethod` calls with a Clerk token copied out of DevTools.

  That was fine for proving the backend worked, but it meant the

  self-service gap wasn't actually felt until deployment — by which

  point it was one more thing standing between "deployed" and "usable

  by a stranger."

- **Check `git ls-files` for tracked secrets before every commit

  involving `.env.example`, not just once at the end.** A real Google

  API key ended up committed to `.env.example` in Phase 6 — caught by

  GitHub's push protection before it ever reached the remote, but it

  shouldn't have gotten that far.

- **Move shared test fixtures to the root `conftest.py` the first

  time, not reactively each time a new directory needs them.**

- **Decide the design direction before building, not after.** The

  Phase 4 brief asked for something visually distinct; what shipped

  was functional but never actually iterated on visually, because the

  Clerk auth crisis consumed the entire phase's attention. Worth

  treating visual design as a scheduled task with its own time budget,

  not something absorbed into whatever phase has room left over.

- **Set up frontend testing from Phase 4, not defer it indefinitely.**

  The original tech stack lock specified Jest + React Testing Library;

  neither was ever actually set up, surfaced only in Phase 6 while

  reconciling the tech stack doc against reality. Every dashboard

  behavior across six phases was verified by hand, in a browser — real

  and effective, but it doesn't scale, and it means a regression in

  auth logic or a page's data fetching has no safety net beyond

  remembering to click through it again. Logged here as a known,

  deliberately deferred gap rather than closed in Phase 6, given how

  much ground this phase already covers — a reasonable scope boundary,

  not an oversight, but a real one worth acting on before this sees

  any use beyond a portfolio demo.



---



## Load testing



Tool: `locust`, targeting `/api/v1/status` and `/health` against the

live deployed backend (`https://autoevalops-api.onrender.com`) —

deliberately not the evaluation pipeline itself, since that's bounded

by Gemini's/OpenAI's rate limits and would cost real money per request

to hammer.



**5 concurrent users, 1/sec ramp-up:**



| Metric | `/api/v1/status` | `/health` |

|---|---|---|

| Requests | 1,684 | 554 |

| Failures | 0 | 0 |

| Median | 180ms | 170ms |

| p95 | 210ms | 190ms |

| p99 | 320ms | 300ms |

| Max | 42,667ms | 41,324ms |



Zero failures at light load, and once warm, p95 stayed under a quarter

second. The one outlier — a 42.6-second max against a 180ms median —

is Render's free-tier cold start: the instance sleeps after

inactivity, and the very first request in the run paid the ~30-60s

wake-up cost the deployment guide already flagged as expected. Every

request after that was fast.



**200 concurrent users, 10/sec ramp-up:**



| Metric | `/api/v1/status` | `/health` |

|---|---|---|

| Requests | 5,940 | 1,928 |

| Failures | 0 | 0 |

| Median | 5,000ms | 240ms |

| p95 | 5,600ms | 330ms |

| p99 | 9,200ms | 670ms |

| Max | 13,618ms | 2,062ms |

| RPS achieved | 47.1 (aggregate) | |



**Still zero failures at 200 users** — the service degrades by getting

slower, not by rejecting requests. But median latency on the status

endpoint rose 27x (180ms → 5,000ms), and throughput plateaued around

**47 RPS** regardless of how many concurrent users were sending

requests. That gap between 200 users wanting service and only ~47

requests/sec actually being served is a queuing signature, not a

crash.



**Root cause, confirmed from the actual deploy log, not inferred:**



```

==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance

```



Render's free tier runs a single worker process on a single CPU.

Every request funnels through one process; there's no parallelism to

absorb concurrent load. This fully explains both the throughput

ceiling and the latency curve — requests are queuing behind each

other, not failing.



**Against `Roadmap.md`'s original 500+ RPS target:** this deployment

reaches roughly 9% of that under load, and the reason is legible and

fixable, not a defect in the application code. `/api/v1/status`'s own

query is cheap (a handful of aggregate Postgres reads); the ceiling is

entirely the hosting tier's worker count. The direct fix is a paid

Render tier with `WEB_CONCURRENCY` set above 1 and multiple instances

behind a load balancer — infrastructure spend, not a rewrite. Worth

stating plainly rather than quietly omitting the number: this is a

portfolio deployment on a free tier, not infrastructure sized for

production traffic, and the load test's value here is in showing

*where* and *why* it would need to change, not in hitting an arbitrary

target.

