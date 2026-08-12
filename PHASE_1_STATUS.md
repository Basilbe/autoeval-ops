# Phase 1 Complete — 2026-08-12

Verified against every "Task N Done When" checklist in `PHASE_1_SETUP_POWERSHELL.md` (Tasks 0-14). All 15 tasks: **PASS**. 41/41 tests passing, 99% coverage, no warnings. Committed to `main`, working tree clean.

---

## What Was Built

**5 evaluators** in `backend/src/autoeval_ops/core/evaluators/`:
- `CorrectnessEvaluator` — LLM-as-judge via injectable `LLMClient` protocol (0-100 score, 70-point pass threshold)
- `ToxicityEvaluator` — pluggable `ToxicityScorer` protocol; `DetoxifyScorer` (real model) or `NullToxicityScorer` (fallback)
- `HallucinationEvaluator` — lexical token-overlap against provided context
- `CostEvaluator` — token-count estimate × per-model USD pricing
- `LatencyEvaluator` — validates a pre-measured latency figure against an SLA

**Async pipeline** in `core/pipeline.py`: `EvaluationPipeline.evaluate_case` runs all evaluators concurrently via `asyncio.gather`; `evaluate_batch` caps concurrency across many cases via `asyncio.Semaphore`. `EvaluationReport` aggregates per-evaluator results into an `overall_status` (fail > warning > pass).

**CLI** in `core/cli.py`: `python -m autoeval_ops.core.cli evaluate --prompt ... --model ... --test-cases test_cases.json`. Falls back to `EchoLLMClient`/`NullToxicityScorer` placeholders when `OPENAI_API_KEY`/Detoxify aren't available, so it always runs end-to-end for local demos.

**Test suite**: 41 tests across 8 files (`tests/core/` + `tests/core/evaluators/`), **99% coverage** (175 stmts, 2 missed), 0 warnings.
```
pytest -v --cov=autoeval_ops --cov-report=term-missing
41 passed in 0.36s
TOTAL   175 stmts   2 missed   99%
```

**Benchmark** (`backend/BENCHMARK.md`, fake clients, `max_concurrency=10`):

| Parallel Evals | Total Time (ms) | ms/eval |
|---|---|---|
| 10 | 3.9 | 0.39 |
| 100 | 10.7 | 0.11 |
| 1000 | 128.7 | 0.13 |

---

## Deliberate Deviations from Original Plan (Phase 1)

- **src-layout package instead of flat `backend/core/`.** `Roadmap.md`'s Phase 1 examples assumed a flat `backend/core/evaluator.py` layout, but Phase 0 already established a src-layout package for `config.py` (`backend/src/autoeval_ops/`). All Phase 1 code lives under `backend/src/autoeval_ops/core/` instead, and the CLI runs as `python -m autoeval_ops.core.cli`. `claude.md`'s Module Isolation table now reflects this src-layout path for **every** phase (`/backend/src/autoeval_ops/github/`, `/api/`, `/observability/`), not just Phase 1. The empty `backend/core/`, `backend/github/`, `backend/api/`, `backend/observability/` folders from the original Phase 0 structure are unused going forward.

- **Python 3.11 required specifically** (not just "3.11+"). Newer Python versions (3.13 tested) hit wheel-availability gaps on Windows for this dependency set (`asyncpg`, `pydantic-core`, and — before it was dropped — `tokenizers`), forcing source builds that fail without a full Rust/C toolchain. 3.11 has prebuilt wheels for all of them.

- **`detoxify` dropped from `requirements.txt`.** Its dependency chain (`transformers` → `tokenizers==0.12.1` → `pyo3==0.12.4`) is unmaintained and fails to build from source on Windows (Rust compile error on 3.13; linker "Access is denied" flake on 3.11). `ToxicityEvaluator` was already designed around a pluggable `ToxicityScorer` protocol, so no code changes were needed: `cli.py` falls back to `NullToxicityScorer`, and all tests use a `FakeScorer`/`NullToxicityScorer` — never the real model. Real toxicity scoring is deferred to a future phase (e.g. a modern `transformers`+`tokenizers` pipeline with current Windows wheels, pointed at a public toxicity model).

- **Coverage exceptions are scoped to specific lines, not whole files.** Initial measurement was 63% because `--cov=autoeval_ops` covered `config.py` (untested Phase 0 file) and all of `cli.py` (untested entirely) with no scoping. This was resolved in two passes: (1) `config.py` is omitted via `[tool.coverage.run] omit = ["*/config.py"]` in `pyproject.toml`, since it's Phase 0 code outside this phase's test scope; (2) `cli.py`'s `run_evaluate()` — the actual orchestration logic — is now fully unit-tested (`tests/core/test_cli.py`, 8 tests total covering `build_pipeline`, `EchoLLMClient`, `NullToxicityScorer`, and `run_evaluate` end-to-end via `tmp_path` fixtures). Only genuinely untestable-without-live-credentials code is `# pragma: no cover`-marked: the real-`OpenAILLMClient` branch inside `build_pipeline` (needs a live `OPENAI_API_KEY`), `DetoxifyScorer.__init__`/`.score` (needs the real Detoxify model, which isn't installed), and `cli.py`'s `main()`/`__main__` entrypoint boilerplate (verified manually via the CLI run in Task 12, not unit-test territory).

---

## Known MVP Simplifications Worth Revisiting Later

- **`HallucinationEvaluator`'s lexical-overlap heuristic.** Checks token overlap between output and context rather than semantic grounding — no pgvector/embeddings available yet (deferred in Phase 0). Upgrade path: swap in embedding similarity once a vector store exists, without changing the `Evaluator` interface.
- **`CostEvaluator`'s character-based token estimate** (~4 chars/token). Avoids adding a `tiktoken` dependency mid-phase, keeping the Phase 0 tech-stack lock intact. Revisit if precise token counts become necessary.

---

## Known Issues / Gotchas for Future Sessions

- `evaluator.py` line 23 (the `Evaluator.evaluate` abstract method body, `raise NotImplementedError`) shows as the one remaining uncovered line (93% on that file) — structurally unreachable since it's an `@abstractmethod` stub, not a functional gap. Left unmarked since overall coverage (99%) already clears the 95% gate without it.
- `backend/.coverage` and `backend/src/autoeval_ops.egg-info/*` build/coverage artifacts are currently tracked in git (committed alongside the Phase 1 work). Harmless but worth `.gitignore`-ing and removing from tracking in a later cleanup pass — not blocking.

---

## Next Step: Phase 2 — GitHub Integration

See `Roadmap.md` for the full task breakdown. Summary:

- Create the GitHub App (permissions: read code/PRs, write PRs; events: push, pull_request)
- Build the webhook receiver (`backend/src/autoeval_ops/github/webhooks.py`, FastAPI endpoint)
- Build the async task queue that invokes the Phase 1 `EvaluationPipeline` per PR
- Build the PR comment generator
- Integration tests with mocked GitHub API responses, including webhook signature verification
- Deploy to a staging environment and validate with a real test-repo PR

Per `CLAUDE.md`'s golden rule: do not begin Phase 2 until this status doc is reviewed and Phase 1 is reconfirmed complete in that session.
