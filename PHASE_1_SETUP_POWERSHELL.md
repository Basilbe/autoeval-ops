# Phase 1: Core Evaluation Engine (PowerShell Edition)

> Every code block is labeled where it goes: **"Run in PowerShell"** (terminal) or **"Paste into `filename`"** (via Notepad). Follows the same conventions as `PHASE_0_SETUP_POWERSHELL.md`.

---

## Structural Decision (Read Before Starting)

`Roadmap.md`'s Phase 1 examples assume a flat layout (`backend/core/evaluator.py`, run via `python -m backend.core.cli`). But Phase 0 already established a **src-layout package** for `config.py` (`backend/src/autoeval_ops/config.py`). Continuing with a flat `backend/core/` would split the codebase into two incompatible import styles.

**Decision:** all Phase 1 code goes under the existing `autoeval_ops` package: `backend/src/autoeval_ops/core/`. The empty `backend/core/`, `backend/github/`, `backend/api/`, `backend/observability/` folders from Phase 0 are left as-is (harmless, unused) — future phases will place their code under `autoeval_ops/github/`, `autoeval_ops/api/`, `autoeval_ops/observability/` instead, for consistency. The CLI is invoked as `python -m autoeval_ops.core.cli` rather than `python -m backend.core.cli`.

This is exactly the kind of structural deviation `CLAUDE.md` says must be explicit and documented — Task 0 below records it in `PHASE_0_STATUS.md` before any code is written.

### Task 0: Document the Decision

**Run in PowerShell:**
```powershell
notepad PHASE_0_STATUS.md
```
Add this under the "Deliberate Deviations" section, then save/close:
```markdown
- **Phase 1 package layout.** Roadmap.md's flat `backend/core/` example was
  not followed. All Phase 1+ code lives under the src-layout package
  established in Phase 0 (`backend/src/autoeval_ops/`), i.e.
  `backend/src/autoeval_ops/core/`. CLI runs as
  `python -m autoeval_ops.core.cli`, not `python -m backend.core.cli`.
  The empty `backend/core/`, `backend/github/`, `backend/api/`,
  `backend/observability/` folders from Phase 0 are unused going forward.
```

---

## Prerequisites: Python Environment

**Run in PowerShell (from the repo root, `autoeval-ops/`):**
```powershell
cd backend
python --version
```
Confirm this shows Python 3.11 or higher. If not, install it from https://www.python.org/downloads/ before continuing.

### Create and activate a virtual environment

**Run in PowerShell:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
Your prompt should now start with `(.venv)`. If you get a script-execution error, run this once and retry:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Install dependencies

**Run in PowerShell:**
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```
> `detoxify` pulls in PyTorch — this is a multi-GB download and can take several minutes. That's expected, not an error. If it fails outright, try installing the CPU-only wheel first, then retry:
> ```powershell
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```

**All commands from here through Task 13 assume you're still inside `backend/` with `.venv` active.** Task 14 (final commit) explicitly returns you to the repo root for git commands.

---

## Task 1: Package Skeleton + Editable Install

### Step 1.1: Create the core package directories

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path src/autoeval_ops/core/evaluators
New-Item -ItemType File -Force -Path src/autoeval_ops/core/__init__.py, src/autoeval_ops/core/evaluators/__init__.py
New-Item -ItemType Directory -Force -Path tests/core/evaluators
New-Item -ItemType File -Force -Path tests/__init__.py
```

### Step 1.2: Create `pyproject.toml` for the editable install

**Run in PowerShell:**
```powershell
notepad pyproject.toml
```

**Paste into `backend/pyproject.toml`:**
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "autoeval-ops"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]
```
Save, close.

### Step 1.3: Install the package in editable mode

**Run in PowerShell:**
```powershell
pip install -e .
```

### Step 1.4: Verify the import works

**Run in PowerShell:**
```powershell
python -c "from autoeval_ops.config import settings; print(settings.environment)"
```
Should print `development` with no errors.

### Task 1 Done When:
- [ ] `src/autoeval_ops/core/` and `src/autoeval_ops/core/evaluators/` exist with `__init__.py` files
- [ ] `pyproject.toml` created
- [ ] `pip install -e .` succeeds
- [ ] `autoeval_ops` imports without error

---

## Task 2: Evaluator Base Class

**Run in PowerShell:**
```powershell
notepad src/autoeval_ops/core/evaluator.py
```

**Paste into `backend/src/autoeval_ops/core/evaluator.py`:**
```python
"""Base class and result model shared by every evaluator."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationResult:
    metric_name: str
    metric_value: float
    status: str  # "pass" | "fail" | "warning"
    details: dict[str, Any] = field(default_factory=dict)


class Evaluator(ABC):
    """Every evaluator (correctness, toxicity, etc.) implements this."""

    name: str = "base"

    @abstractmethod
    async def evaluate(self, output: str, **kwargs: Any) -> EvaluationResult:
        """Evaluate a single model output and return a result."""
        raise NotImplementedError
```
Save, close.

### Task 2 Done When:
- [ ] `evaluator.py` created with `Evaluator` ABC and `EvaluationResult` dataclass

---

## Task 3: Correctness Evaluator

Uses an injectable LLM-as-judge client so tests never need a real API key.

**Run in PowerShell:**
```powershell
notepad src/autoeval_ops/core/evaluators/correctness.py
```

**Paste into `backend/src/autoeval_ops/core/evaluators/correctness.py`:**
```python
"""LLM-as-judge correctness evaluator."""
from __future__ import annotations
from typing import Protocol

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class CorrectnessEvaluator(Evaluator):
    name = "correctness"

    def __init__(self, llm_client: LLMClient, pass_threshold: float = 70.0):
        self.llm_client = llm_client
        self.pass_threshold = pass_threshold

    async def evaluate(self, output: str, expected: str = "", **kwargs) -> EvaluationResult:
        if not output.strip():
            return EvaluationResult(self.name, 0.0, "fail", {"reason": "empty output"})

        judge_prompt = (
            "You are grading an AI answer against a reference answer.\n"
            f"Reference: {expected}\n"
            f"Candidate: {output}\n"
            "Score the candidate's correctness from 0 to 100. "
            "Respond with only the number."
        )
        raw = await self.llm_client.complete(judge_prompt)
        try:
            score = float(raw.strip())
        except ValueError:
            score = 0.0
        score = max(0.0, min(100.0, score))
        status = "pass" if score >= self.pass_threshold else "fail"
        return EvaluationResult(self.name, score, status, {"raw_judge_response": raw})
```
Save, close.

### Task 3 Done When:
- [ ] `correctness.py` created and imports cleanly

---

## Task 4: Toxicity Evaluator

Scorer is also injectable, so tests don't need Detoxify/PyTorch loaded.

**Run in PowerShell:**
```powershell
notepad src/autoeval_ops/core/evaluators/toxicity.py
```

**Paste into `backend/src/autoeval_ops/core/evaluators/toxicity.py`:**
```python
"""Toxicity evaluator, backed by a pluggable scorer (Detoxify by default)."""
from __future__ import annotations
import asyncio
from typing import Protocol

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


class ToxicityScorer(Protocol):
    def score(self, text: str) -> float: ...  # 0.0 (clean) - 1.0 (toxic)


class DetoxifyScorer:
    """Lazy-loads Detoxify so importing this module never forces a torch
    load unless this scorer is actually instantiated."""

    def __init__(self) -> None:
        from detoxify import Detoxify  # heavy import, deferred on purpose

        self._model = Detoxify("original")

    def score(self, text: str) -> float:
        result = self._model.predict(text)
        return float(result.get("toxicity", 0.0))


class ToxicityEvaluator(Evaluator):
    name = "toxicity"

    def __init__(self, scorer: ToxicityScorer, fail_threshold: float = 0.5):
        self.scorer = scorer
        self.fail_threshold = fail_threshold

    async def evaluate(self, output: str, **kwargs) -> EvaluationResult:
        if not output.strip():
            return EvaluationResult(self.name, 0.0, "pass", {"reason": "empty output"})
        # scorer.score is CPU-bound and synchronous; run off the event loop
        raw_score = await asyncio.to_thread(self.scorer.score, output)
        pct = raw_score * 100
        status = "fail" if raw_score >= self.fail_threshold else "pass"
        return EvaluationResult(self.name, pct, status, {"raw_score": raw_score})
```
Save, close.

### Task 4 Done When:
- [ ] `toxicity.py` created and imports cleanly

---

## Task 5: Hallucination Evaluator

No pgvector/embeddings available yet (deferred in Phase 0), so this is a lexical-overlap heuristic for MVP — upgradeable later without changing the `Evaluator` interface.

**Run in PowerShell:**
```powershell
notepad src/autoeval_ops/core/evaluators/hallucination.py
```

**Paste into `backend/src/autoeval_ops/core/evaluators/hallucination.py`:**
```python
"""MVP hallucination check via lexical overlap with provided context.

Upgrade path: once a vector store is available, swap this scoring logic
for embedding similarity without changing the Evaluator interface.
"""
from __future__ import annotations
import re

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class HallucinationEvaluator(Evaluator):
    name = "hallucination"

    def __init__(self, min_overlap: float = 0.3):
        self.min_overlap = min_overlap

    async def evaluate(self, output: str, context: str = "", **kwargs) -> EvaluationResult:
        if not output.strip():
            return EvaluationResult(self.name, 0.0, "pass", {"reason": "empty output"})
        if not context.strip():
            return EvaluationResult(
                self.name, 0.0, "warning", {"reason": "no context provided to check against"}
            )

        output_tokens = _tokenize(output)
        context_tokens = _tokenize(context)
        if not output_tokens:
            return EvaluationResult(self.name, 0.0, "pass", {})

        grounded = output_tokens & context_tokens
        overlap_ratio = len(grounded) / len(output_tokens)
        score = overlap_ratio * 100
        status = "pass" if overlap_ratio >= self.min_overlap else "fail"
        return EvaluationResult(self.name, score, status, {"overlap_ratio": overlap_ratio})
```
Save, close.

### Task 5 Done When:
- [ ] `hallucination.py` created and imports cleanly

---

## Task 6: Cost Evaluator

Uses a character-count approximation (~4 chars/token) instead of adding a new `tiktoken` dependency — keeps the Phase 0 tech-stack lock intact.

**Run in PowerShell:**
```powershell
notepad src/autoeval_ops/core/evaluators/cost.py
```

**Paste into `backend/src/autoeval_ops/core/evaluators/cost.py`:**
```python
"""Cost evaluator: estimates spend from prompt+output length and model pricing."""
from __future__ import annotations

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult

# USD per 1K tokens, blended input+output estimate. Update as pricing changes.
MODEL_PRICING = {
    "gpt-4": 0.03,
    "gpt-4o": 0.005,
    "gpt-3.5-turbo": 0.0015,
}
DEFAULT_PRICE_PER_1K = 0.01


def _estimate_tokens(text: str) -> int:
    # ~4 characters per token (OpenAI's rule of thumb). Avoids a tiktoken
    # dependency for Phase 1; revisit if precise counts become necessary.
    return max(1, len(text) // 4)


class CostEvaluator(Evaluator):
    name = "cost"

    def __init__(self, model: str, max_cost_usd: float = 0.05):
        self.model = model
        self.max_cost_usd = max_cost_usd

    async def evaluate(self, output: str, prompt: str = "", **kwargs) -> EvaluationResult:
        tokens = _estimate_tokens(prompt) + _estimate_tokens(output)
        price_per_1k = MODEL_PRICING.get(self.model, DEFAULT_PRICE_PER_1K)
        cost_usd = (tokens / 1000) * price_per_1k
        status = "pass" if cost_usd <= self.max_cost_usd else "fail"
        return EvaluationResult(
            self.name, cost_usd, status, {"estimated_tokens": tokens, "model": self.model}
        )
```
Save, close.

### Task 6 Done When:
- [ ] `cost.py` created and imports cleanly

---

## Task 7: Latency Evaluator

Validates a latency figure already measured elsewhere (e.g. during generation) against an SLA — it does not time itself.

**Run in PowerShell:**
```powershell
notepad src/autoeval_ops/core/evaluators/latency.py
```

**Paste into `backend/src/autoeval_ops/core/evaluators/latency.py`:**
```python
"""Latency evaluator: validates a pre-measured generation time against an SLA."""
from __future__ import annotations

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


class LatencyEvaluator(Evaluator):
    name = "latency"

    def __init__(self, max_latency_ms: float = 5000.0):
        self.max_latency_ms = max_latency_ms

    async def evaluate(self, output: str, latency_ms: float = 0.0, **kwargs) -> EvaluationResult:
        status = "pass" if latency_ms <= self.max_latency_ms else "fail"
        return EvaluationResult(
            self.name, latency_ms, status, {"max_latency_ms": self.max_latency_ms}
        )
```
Save, close.

### Task 7 Done When:
- [ ] `latency.py` created and imports cleanly

---

## Task 8: Async Evaluation Pipeline

**Run in PowerShell:**
```powershell
notepad src/autoeval_ops/core/pipeline.py
```

**Paste into `backend/src/autoeval_ops/core/pipeline.py`:**
```python
"""Runs all evaluators concurrently against one or many test cases."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


@dataclass
class EvaluationReport:
    results: list[EvaluationResult] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        if any(r.status == "fail" for r in self.results):
            return "fail"
        if any(r.status == "warning" for r in self.results):
            return "warning"
        return "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "results": [
                {
                    "metric_name": r.metric_name,
                    "metric_value": r.metric_value,
                    "status": r.status,
                    "details": r.details,
                }
                for r in self.results
            ],
        }


class EvaluationPipeline:
    def __init__(self, evaluators: list[Evaluator]):
        self.evaluators = evaluators

    async def evaluate_case(self, output: str, **kwargs: Any) -> EvaluationReport:
        tasks = [ev.evaluate(output, **kwargs) for ev in self.evaluators]
        results = await asyncio.gather(*tasks)
        return EvaluationReport(results=list(results))

    async def evaluate_batch(
        self, cases: list[dict[str, Any]], max_concurrency: int = 10
    ) -> list[EvaluationReport]:
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run(case: dict[str, Any]) -> EvaluationReport:
            async with semaphore:
                output = case.pop("output")
                return await self.evaluate_case(output, **case)

        return await asyncio.gather(*[_run(dict(c)) for c in cases])
```
Save, close.

### Task 8 Done When:
- [ ] `pipeline.py` created with `EvaluationPipeline` and `EvaluationReport`
- [ ] `evaluate_case` uses `asyncio.gather` across evaluators
- [ ] `evaluate_batch` caps concurrency via `asyncio.Semaphore`

---

## Task 9: Pytest Configuration

**Run in PowerShell:**
```powershell
notepad pytest.ini
```

**Paste into `backend/pytest.ini`:**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```
Save, close.

**Run in PowerShell:**
```powershell
notepad tests\conftest.py
```

**Paste into `backend/tests/conftest.py`:**
```python
"""Ensures the src package is importable even without an editable install."""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```
Save, close.

### Task 9 Done When:
- [ ] `pytest.ini` sets `asyncio_mode = auto`
- [ ] `conftest.py` created as a safety net for imports

---

## Task 10: Unit Tests

### Step 10.1: Base evaluator + result model

**Run in PowerShell:**
```powershell
notepad tests\core\test_evaluator_base.py
```

**Paste into `backend/tests/core/test_evaluator_base.py`:**
```python
import pytest

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


def test_evaluator_is_abstract():
    with pytest.raises(TypeError):
        Evaluator()


def test_evaluation_result_defaults():
    result = EvaluationResult(metric_name="x", metric_value=1.0, status="pass")
    assert result.details == {}


async def test_concrete_evaluator_can_be_instantiated_and_run():
    class DummyEvaluator(Evaluator):
        name = "dummy"

        async def evaluate(self, output, **kwargs):
            return EvaluationResult(self.name, 1.0, "pass")

    ev = DummyEvaluator()
    result = await ev.evaluate("hello")
    assert result.status == "pass"
```
Save, close.

### Step 10.2: Correctness evaluator tests

**Run in PowerShell:**
```powershell
notepad tests\core\evaluators\test_correctness.py
```

**Paste into `backend/tests/core/evaluators/test_correctness.py`:**
```python
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response

    async def complete(self, prompt: str) -> str:
        return self.response


async def test_correctness_high_score_passes():
    ev = CorrectnessEvaluator(FakeLLMClient("95"))
    result = await ev.evaluate("Paris is the capital of France.", expected="Paris")
    assert result.status == "pass"
    assert result.metric_value == 95.0


async def test_correctness_low_score_fails():
    ev = CorrectnessEvaluator(FakeLLMClient("20"))
    result = await ev.evaluate("The moon is made of cheese.", expected="rock")
    assert result.status == "fail"
    assert result.metric_value == 20.0


async def test_correctness_empty_output_fails_without_calling_llm():
    ev = CorrectnessEvaluator(FakeLLMClient("100"))
    result = await ev.evaluate("", expected="anything")
    assert result.status == "fail"
    assert result.metric_value == 0.0


async def test_correctness_handles_non_numeric_judge_response():
    ev = CorrectnessEvaluator(FakeLLMClient("not a number"))
    result = await ev.evaluate("some output", expected="ref")
    assert result.metric_value == 0.0
    assert result.status == "fail"


async def test_correctness_clamps_out_of_range_score():
    ev = CorrectnessEvaluator(FakeLLMClient("150"))
    result = await ev.evaluate("output", expected="ref")
    assert result.metric_value == 100.0
```
Save, close.

### Step 10.3: Toxicity evaluator tests

**Run in PowerShell:**
```powershell
notepad tests\core\evaluators\test_toxicity.py
```

**Paste into `backend/tests/core/evaluators/test_toxicity.py`:**
```python
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator


class FakeScorer:
    def __init__(self, value: float):
        self.value = value

    def score(self, text: str) -> float:
        return self.value


async def test_toxicity_clean_text_passes():
    ev = ToxicityEvaluator(FakeScorer(0.05))
    result = await ev.evaluate("Have a wonderful day!")
    assert result.status == "pass"


async def test_toxicity_toxic_text_fails():
    ev = ToxicityEvaluator(FakeScorer(0.9))
    result = await ev.evaluate("some toxic text")
    assert result.status == "fail"


async def test_toxicity_empty_output_passes_without_scoring():
    ev = ToxicityEvaluator(FakeScorer(0.9))
    result = await ev.evaluate("")
    assert result.status == "pass"
    assert result.metric_value == 0.0


async def test_toxicity_boundary_at_threshold_fails():
    ev = ToxicityEvaluator(FakeScorer(0.5), fail_threshold=0.5)
    result = await ev.evaluate("borderline text")
    assert result.status == "fail"


async def test_toxicity_score_converted_to_percentage():
    ev = ToxicityEvaluator(FakeScorer(0.3))
    result = await ev.evaluate("mild text")
    assert result.metric_value == 30.0
```
Save, close.

### Step 10.4: Hallucination evaluator tests

**Run in PowerShell:**
```powershell
notepad tests\core\evaluators\test_hallucination.py
```

**Paste into `backend/tests/core/evaluators/test_hallucination.py`:**
```python
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator


async def test_hallucination_grounded_output_passes():
    ev = HallucinationEvaluator(min_overlap=0.3)
    context = "The Eiffel Tower is located in Paris France and was completed in 1889"
    output = "The Eiffel Tower is in Paris"
    result = await ev.evaluate(output, context=context)
    assert result.status == "pass"


async def test_hallucination_ungrounded_output_fails():
    ev = HallucinationEvaluator(min_overlap=0.5)
    context = "The Eiffel Tower is in Paris"
    output = "Dinosaurs invented the telephone in 1200 BC"
    result = await ev.evaluate(output, context=context)
    assert result.status == "fail"


async def test_hallucination_no_context_returns_warning():
    ev = HallucinationEvaluator()
    result = await ev.evaluate("some output", context="")
    assert result.status == "warning"


async def test_hallucination_empty_output_passes():
    ev = HallucinationEvaluator()
    result = await ev.evaluate("", context="some context")
    assert result.status == "pass"


async def test_hallucination_case_insensitive_matching():
    ev = HallucinationEvaluator(min_overlap=0.5)
    context = "PARIS is a CITY"
    output = "paris is a city"
    result = await ev.evaluate(output, context=context)
    assert result.status == "pass"
```
Save, close.

### Step 10.5: Cost evaluator tests

**Run in PowerShell:**
```powershell
notepad tests\core\evaluators\test_cost.py
```

**Paste into `backend/tests/core/evaluators/test_cost.py`:**
```python
from autoeval_ops.core.evaluators.cost import CostEvaluator, _estimate_tokens


async def test_cost_within_budget_passes():
    ev = CostEvaluator(model="gpt-3.5-turbo", max_cost_usd=1.0)
    result = await ev.evaluate("short output", prompt="short prompt")
    assert result.status == "pass"


async def test_cost_over_budget_fails():
    ev = CostEvaluator(model="gpt-4", max_cost_usd=0.00001)
    result = await ev.evaluate("a" * 2000, prompt="a" * 2000)
    assert result.status == "fail"


async def test_cost_unknown_model_uses_default_pricing():
    ev = CostEvaluator(model="some-unlisted-model", max_cost_usd=1.0)
    result = await ev.evaluate("output text", prompt="prompt text")
    assert result.details["model"] == "some-unlisted-model"


def test_estimate_tokens_roughly_matches_character_count():
    assert _estimate_tokens("a" * 400) == 100


def test_estimate_tokens_minimum_is_one():
    assert _estimate_tokens("") == 1
```
Save, close.

### Step 10.6: Latency evaluator tests

**Run in PowerShell:**
```powershell
notepad tests\core\evaluators\test_latency.py
```

**Paste into `backend/tests/core/evaluators/test_latency.py`:**
```python
from autoeval_ops.core.evaluators.latency import LatencyEvaluator


async def test_latency_within_sla_passes():
    ev = LatencyEvaluator(max_latency_ms=1000)
    result = await ev.evaluate("output", latency_ms=250)
    assert result.status == "pass"


async def test_latency_over_sla_fails():
    ev = LatencyEvaluator(max_latency_ms=1000)
    result = await ev.evaluate("output", latency_ms=5000)
    assert result.status == "fail"


async def test_latency_exactly_at_sla_passes():
    ev = LatencyEvaluator(max_latency_ms=1000)
    result = await ev.evaluate("output", latency_ms=1000)
    assert result.status == "pass"


async def test_latency_default_zero_passes():
    ev = LatencyEvaluator()
    result = await ev.evaluate("output")
    assert result.status == "pass"


async def test_latency_reports_max_in_details():
    ev = LatencyEvaluator(max_latency_ms=1500)
    result = await ev.evaluate("output", latency_ms=100)
    assert result.details["max_latency_ms"] == 1500
```
Save, close.

### Step 10.7: Pipeline tests (concurrency + aggregation)

**Run in PowerShell:**
```powershell
notepad tests\core\test_pipeline.py
```

**Paste into `backend/tests/core/test_pipeline.py`:**
```python
import asyncio

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult
from autoeval_ops.core.pipeline import EvaluationPipeline


class FixedEvaluator(Evaluator):
    def __init__(self, name, status, value=1.0):
        self.name = name
        self._status = status
        self._value = value

    async def evaluate(self, output, **kwargs):
        return EvaluationResult(self.name, self._value, self._status)


class ConcurrencyTrackingEvaluator(Evaluator):
    name = "tracker"
    active = 0
    max_active = 0

    async def evaluate(self, output, **kwargs):
        type(self).active += 1
        type(self).max_active = max(type(self).max_active, type(self).active)
        await asyncio.sleep(0.01)
        type(self).active -= 1
        return EvaluationResult(self.name, 1.0, "pass")


async def test_pipeline_runs_all_evaluators_in_parallel():
    evaluators = [FixedEvaluator("a", "pass"), FixedEvaluator("b", "pass")]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("some output")
    assert len(report.results) == 2


async def test_pipeline_overall_status_fail_if_any_fails():
    evaluators = [FixedEvaluator("a", "pass"), FixedEvaluator("b", "fail")]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("some output")
    assert report.overall_status == "fail"


async def test_pipeline_overall_status_warning_when_no_failures():
    evaluators = [FixedEvaluator("a", "pass"), FixedEvaluator("b", "warning")]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("some output")
    assert report.overall_status == "warning"


async def test_pipeline_batch_respects_max_concurrency():
    ConcurrencyTrackingEvaluator.active = 0
    ConcurrencyTrackingEvaluator.max_active = 0
    pipeline = EvaluationPipeline([ConcurrencyTrackingEvaluator()])
    cases = [{"output": f"case {i}"} for i in range(20)]
    await pipeline.evaluate_batch(cases, max_concurrency=5)
    assert ConcurrencyTrackingEvaluator.max_active <= 5


async def test_pipeline_as_dict_serializes_cleanly():
    evaluators = [FixedEvaluator("a", "pass", value=42.0)]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("output")
    data = report.as_dict()
    assert data["results"][0]["metric_value"] == 42.0
```
Save, close.

### Task 10 Done When:
- [ ] All 7 test files created (base, 5 evaluators, pipeline)
- [ ] 33 total test functions across all files

---

## Task 11: Run Tests and Verify Coverage

**Run in PowerShell:**
```powershell
pytest -v --cov=autoeval_ops --cov-report=term-missing
```
Expect all tests to pass with no warnings. Check the coverage summary at the bottom — target is ≥95% per `CLAUDE.md`.

> Note: `evaluators/toxicity.py`'s `DetoxifyScorer` class and `cli.py`'s `OpenAILLMClient` won't be exercised by these tests (they need real Detoxify/OpenAI credentials) — some uncovered lines there are expected and fine. Everything else should be fully covered.

### Task 11 Done When:
- [ ] `pytest -v` shows all tests passing
- [ ] Coverage ≥95% (excluding the noted real-API code paths)
- [ ] No warnings in output

---

## Task 12: CLI Tool

### Step 12.1: Create the CLI

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\core\cli.py
```

**Paste into `backend/src/autoeval_ops/core/cli.py`:**
```python
"""
Usage:
  python -m autoeval_ops.core.cli evaluate --prompt "Summarize: {text}" --model gpt-4 --test-cases test_cases.json
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from autoeval_ops.core.pipeline import EvaluationPipeline
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator


class EchoLLMClient:
    """Fallback used when no OPENAI_API_KEY is set, so the CLI still runs
    end-to-end for local demos without hitting a real API."""

    async def complete(self, prompt: str) -> str:
        return "50"


class NullToxicityScorer:
    def score(self, text: str) -> float:
        return 0.0


def build_pipeline(model: str) -> EvaluationPipeline:
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)

        class OpenAILLMClient:
            async def complete(self, prompt: str) -> str:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                )
                return resp.choices[0].message.content or "0"

        llm_client = OpenAILLMClient()
    else:
        print("WARNING: OPENAI_API_KEY not set - using placeholder LLM client.", file=sys.stderr)
        llm_client = EchoLLMClient()

    try:
        from autoeval_ops.core.evaluators.toxicity import DetoxifyScorer

        scorer = DetoxifyScorer()
    except Exception:
        print("WARNING: Detoxify unavailable - using placeholder toxicity scorer.", file=sys.stderr)
        scorer = NullToxicityScorer()

    return EvaluationPipeline(
        [
            CorrectnessEvaluator(llm_client),
            ToxicityEvaluator(scorer),
            HallucinationEvaluator(),
            CostEvaluator(model=model),
            LatencyEvaluator(),
        ]
    )


async def run_evaluate(args: argparse.Namespace) -> None:
    test_cases_path = Path(args.test_cases)
    cases = json.loads(test_cases_path.read_text())

    pipeline = build_pipeline(args.model)

    prepared = []
    for case in cases:
        prepared.append(
            {
                "output": case["output"],
                "expected": case.get("expected", ""),
                "context": case.get("context", ""),
                "prompt": args.prompt,
                "latency_ms": case.get("latency_ms", 0.0),
            }
        )

    reports = await pipeline.evaluate_batch(prepared)

    for i, report in enumerate(reports):
        print(f"\n=== Test case {i + 1}: {report.overall_status.upper()} ===")
        for result in report.results:
            print(f"  {result.metric_name:14s} {result.metric_value:8.2f}  [{result.status}]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="autoeval-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate", help="Run the evaluation pipeline against test cases")
    evaluate_parser.add_argument("--prompt", required=True)
    evaluate_parser.add_argument("--model", required=True)
    evaluate_parser.add_argument("--test-cases", required=True)

    args = parser.parse_args()

    if args.command == "evaluate":
        asyncio.run(run_evaluate(args))


if __name__ == "__main__":
    main()
```
Save, close.

### Step 12.2: Create example test cases

**Run in PowerShell:**
```powershell
notepad test_cases.json
```

**Paste into `backend/test_cases.json`:**
```json
[
  {
    "output": "The capital of France is Paris.",
    "expected": "Paris",
    "context": "Paris is the capital and most populous city of France.",
    "latency_ms": 180
  },
  {
    "output": "I think the moon is made of cheese, probably imported from the stars.",
    "expected": "The moon is composed of rock",
    "context": "The Moon is Earth's only natural satellite, composed primarily of rock.",
    "latency_ms": 900
  }
]
```
Save, close.

### Step 12.3: Run the CLI

**Run in PowerShell:**
```powershell
python -m autoeval_ops.core.cli evaluate --prompt "Summarize: {text}" --model gpt-4 --test-cases test_cases.json
```
Without `OPENAI_API_KEY` set, you'll see warnings about placeholder clients — that's expected and the CLI should still run to completion, printing pass/fail results per test case.

### Task 12 Done When:
- [ ] `cli.py` created
- [ ] `test_cases.json` created
- [ ] CLI runs end-to-end and prints results for both test cases

---

## Task 13: Benchmark

Uses fake LLM/toxicity clients with a simulated 10ms delay, so the numbers measure pipeline/asyncio overhead rather than real network latency.

### Step 13.1: Create the benchmark script

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path scripts
notepad scripts\benchmark.py
```

**Paste into `backend/scripts/benchmark.py`:**
```python
"""
Benchmarks the evaluation pipeline at 10, 100, and 1000 parallel cases.
Run with: python scripts/benchmark.py
"""
from __future__ import annotations
import asyncio
import time

from autoeval_ops.core.pipeline import EvaluationPipeline
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator


class FakeLLMClient:
    async def complete(self, prompt: str) -> str:
        await asyncio.sleep(0.01)  # simulate small network latency
        return "80"


class FakeToxicityScorer:
    def score(self, text: str) -> float:
        return 0.05


def build_pipeline() -> EvaluationPipeline:
    return EvaluationPipeline(
        [
            CorrectnessEvaluator(FakeLLMClient()),
            ToxicityEvaluator(FakeToxicityScorer()),
            HallucinationEvaluator(),
            CostEvaluator(model="gpt-4"),
            LatencyEvaluator(),
        ]
    )


async def run_n(n: int, max_concurrency: int) -> float:
    pipeline = build_pipeline()
    cases = [
        {
            "output": f"This is test output number {i}",
            "expected": "reference answer",
            "context": "This is test output number context",
            "prompt": "Summarize: {text}",
            "latency_ms": 120.0,
        }
        for i in range(n)
    ]
    start = time.perf_counter()
    await pipeline.evaluate_batch(cases, max_concurrency=max_concurrency)
    return (time.perf_counter() - start) * 1000


async def main() -> None:
    print("Benchmarking EvaluationPipeline (fake clients, no real network calls)\n")
    results = {}
    for n in (10, 100, 1000):
        elapsed_ms = await run_n(n, max_concurrency=10)
        results[n] = elapsed_ms
        print(f"{n:5d} parallel evals: {elapsed_ms:8.1f} ms  ({elapsed_ms / n:6.2f} ms/eval)")

    with open("BENCHMARK.md", "w") as f:
        f.write("# Phase 1 Benchmark Results\n\n")
        f.write("Measured with fake LLM/toxicity clients (simulated 10ms latency), max_concurrency=10.\n\n")
        f.write("| Parallel Evals | Total Time (ms) | ms/eval |\n")
        f.write("|---|---|---|\n")
        for n, ms in results.items():
            f.write(f"| {n} | {ms:.1f} | {ms / n:.2f} |\n")
    print("\nWrote BENCHMARK.md")


if __name__ == "__main__":
    asyncio.run(main())
```
Save, close.

### Step 13.2: Run it

**Run in PowerShell:**
```powershell
python scripts\benchmark.py
```

### Step 13.3: Verify

**Run in PowerShell:**
```powershell
Get-Content BENCHMARK.md
```

### Task 13 Done When:
- [ ] `scripts/benchmark.py` created
- [ ] Script runs and prints 10/100/1000 timing results
- [ ] `backend/BENCHMARK.md` generated with the results table

---

## Task 14: Final Commit and Verification

### Step 14.1: Deactivate the virtual environment and return to repo root

**Run in PowerShell:**
```powershell
deactivate
cd ..
```

### Step 14.2: Update `.gitignore` to exclude the venv

**Run in PowerShell:**
```powershell
notepad .gitignore
```
Add this line if not already present, save, close:
```text
backend/.venv/
```

### Step 14.3: Full verification pass

**Run in PowerShell:**
```powershell
Write-Host "=== Tests ===" -ForegroundColor Cyan
cd backend
.venv\Scripts\Activate.ps1
pytest -v --cov=autoeval_ops --cov-report=term-missing
deactivate
cd ..

Write-Host "=== Git Status ===" -ForegroundColor Cyan
git status
```

### Step 14.4: Commit and push

**Run in PowerShell:**
```powershell
git add -A
git commit -m "[PHASE 1] Core evaluation engine: 5 evaluators, async pipeline, CLI, benchmarks"
git push origin main
```

### Final Checklist:
- [ ] All 5 evaluators implemented (Correctness, Toxicity, Hallucination, Cost, Latency)
- [ ] Async pipeline runs evaluators in parallel via `asyncio.gather`
- [ ] `evaluate_batch` caps concurrency via `asyncio.Semaphore`
- [ ] 33 unit tests passing, ≥95% coverage (excluding real-API-only code paths)
- [ ] CLI tool runs end-to-end
- [ ] `BENCHMARK.md` documents 10/100/1000-eval timings
- [ ] Structural deviation documented in `PHASE_0_STATUS.md`
- [ ] Committed and pushed to GitHub

---

## Next Step

Once every box above is checked, move to **Phase 2: GitHub Integration** per `Roadmap.md`. Before starting:
1. Update `PHASE_0_STATUS.md` (or create `PHASE_1_STATUS.md`) summarizing what's done — same pattern as the Phase 0 audit, so a fresh Claude Code session can pick up context without relying on conversation history.
2. Note that `HallucinationEvaluator`'s lexical-overlap approach and `CostEvaluator`'s character-based token estimate are known MVP simplifications — fine for now, worth revisiting once pgvector/tiktoken become relevant.

---

## PowerShell Notes
- All commands in Tasks 1-13 assume you're inside `backend/` with `.venv` activated.
- `notepad <file>` + paste remains the most reliable way to get code into files without here-string paste issues.
- If `pytest` isn't found after activating `.venv`, confirm `pip install -r requirements.txt` completed successfully — `pytest` ships as part of that install.
