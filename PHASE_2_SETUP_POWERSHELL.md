# Phase 2: GitHub Integration (PowerShell Edition)

> Every code block is labeled where it goes: **"Run in PowerShell"** or **"Paste into `filename`"**. Same conventions as Phase 0/1.

## Scope Decisions (confirmed before building)
- **Full GitHub App** (JWT auth, installation tokens) — not a simplified PAT+webhook.
- **httpx**, not PyGithub, for GitHub API calls — matches `TECH_STACK.md`'s async commitment. `PyGithub` stays in `requirements.txt` unused.
- **Cloudflare Tunnel (`cloudflared`)** for local webhook testing — real cloud deployment stays in Phase 6. (Originally planned with ngrok; switched after ngrok's Windows binary was persistently blocked by security software across three separate download methods — see Troubleshooting Log.)
- **In-memory, no DB persistence yet** — Phase 2 runs evaluators live and posts straight to the PR comment. Phase 3's ORM models retrofit persistence.
- **asyncio-based queue**, not Celery — Redis stays unused until a later phase.
- **New:** a `PromptRunner` component (not in `Roadmap.md`'s task list) that actually calls the LLM to generate outputs for the changed prompt — required for evaluation to mean anything.
- **New:** a minimal FastAPI app (`server.py`) created now, expanded in Phase 3 rather than replaced.

---

## Prerequisites

### Reactivate the Phase 1 environment

**Run in PowerShell (from the repo root):**
```powershell
cd backend
.venv\Scripts\Activate.ps1
python --version
```
Confirm `Python 3.11.x`.

### Add PyJWT for GitHub App authentication

**Run in PowerShell:**
```powershell
notepad requirements.txt
```
Add this line (anywhere, e.g. near `cryptography`), save, close:
```text
PyJWT[crypto]==2.8.0
```

**Run in PowerShell:**
```powershell
pip install -r requirements.txt
```

### Install Cloudflare Tunnel (`cloudflared`)

No account or signup needed for the quick-tunnel mode used here.

**Run in PowerShell:**
```powershell
winget install --id Cloudflare.cloudflared
```
Close this PowerShell window completely, open a **brand new** one, then verify:
```powershell
cloudflared --version
```

> Note: `cloudflared`'s free quick-tunnel mode gets a new random `*.trycloudflare.com` URL every time you start it — there's no free reserved/static domain equivalent to what ngrok offers. That's fine for Task 13's one-time verification test; you'll just re-paste the URL into the GitHub App's webhook settings each session. A permanent, unchanging URL is what Phase 6's real deployment provides.

### Task Done When:
- [ ] `.venv` reactivated, `python --version` shows 3.11.x
- [ ] `PyJWT[crypto]` installed
- [ ] `cloudflared` installed, `cloudflared --version` runs clean

---

## Task 0: Refactor Shared LLM Client + Fix a Latent Config Bug

This touches Phase 0/1 files. Per the Bug Containment rule, we fix and re-verify Phase 1 before building anything new on top of it.

### Step 0.1: Fix `config.py`'s `.env` path bug

**Why:** `Config.env_file = ".env"` is resolved relative to the current working directory, not relative to `config.py`'s location. It silently worked in Phase 1 only because no tested value actually depended on a real `.env` read. In Phase 2, the GitHub App's ID/key path/webhook secret must load correctly regardless of which folder you launch the server from.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\config.py
```

**Paste into `backend/src/autoeval_ops/config.py`** (full replacement):
```python
from pathlib import Path

from pydantic_settings import BaseSettings

# config.py lives at backend/src/autoeval_ops/config.py — four levels below
# the repo root. Resolve .env from an absolute path so it loads correctly
# regardless of the working directory the process is launched from.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_repo_path(path: str) -> Path:
    """Resolve a path from .env relative to the repo root, regardless of
    the working directory the process was launched from."""
    p = Path(path)
    return p if p.is_absolute() else _REPO_ROOT / p


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://autoeval_user:dev_password@localhost:5432/autoeval_dev"

    # Server
    environment: str = "development"
    log_level: str = "DEBUG"

    # Evaluation
    max_concurrent_evals: int = 10
    eval_timeout_seconds: int = 300

    # GitHub App (Phase 2)
    github_app_id: str = ""
    github_app_private_key_path: str = ""
    github_webhook_secret: str = ""

    class Config:
        env_file = str(_REPO_ROOT / ".env")
        extra = "ignore"  # .env has Phase 0/3+ keys (POSTGRES_*, CLERK_*,
                           # etc.) not yet declared as fields here - ignore
                           # rather than error on them.


settings = Settings()
```
Save, close.

### Step 0.2: Create the shared LLM client module

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\core\llm_client.py
```

**Paste into `backend/src/autoeval_ops/core/llm_client.py`:**
```python
"""Shared LLM client used by both the CLI (Phase 1) and the GitHub
orchestrator (Phase 2) — one implementation of 'talk to the real model, or
fall back to a placeholder' instead of two."""
from __future__ import annotations
import os
from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class EchoLLMClient:
    """Fallback used when no OPENAI_API_KEY is set, so callers still run
    end-to-end for local demos without hitting a real API."""

    async def complete(self, prompt: str) -> str:
        return "50"


class OpenAILLMClient:  # pragma: no cover - requires a real OPENAI_API_KEY
    def __init__(self, model: str, api_key: str):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(self, prompt: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        return resp.choices[0].message.content or ""


def build_llm_client(model: str) -> LLMClient:
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:  # pragma: no cover - requires a real OPENAI_API_KEY
        return OpenAILLMClient(model=model, api_key=api_key)
    return EchoLLMClient()
```
Save, close.

### Step 0.3: Move `NullToxicityScorer` into `toxicity.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\core\evaluators\toxicity.py
```

Add this class at the end of the file (keep everything else unchanged), save, close:
```python
class NullToxicityScorer:
    """No-op scorer used when Detoxify is unavailable (it was dropped from
    requirements.txt in Phase 1 — see PHASE_0_STATUS.md)."""

    def score(self, text: str) -> float:
        return 0.0
```

### Step 0.4: Simplify `cli.py` to use the shared modules

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\core\cli.py
```

**Paste into `backend/src/autoeval_ops/core/cli.py`** (full replacement):
```python
"""
Usage:
  python -m autoeval_ops.core.cli evaluate --prompt "Summarize: {text}" --model gpt-4 --test-cases test_cases.json
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

from autoeval_ops.core.pipeline import EvaluationPipeline
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator, NullToxicityScorer
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator
from autoeval_ops.core.llm_client import build_llm_client, EchoLLMClient  # noqa: F401 (re-exported for tests)


def build_pipeline(model: str) -> EvaluationPipeline:
    llm_client = build_llm_client(model)

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


def main() -> None:  # pragma: no cover - entrypoint, verified manually
    parser = argparse.ArgumentParser(prog="autoeval-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate", help="Run the evaluation pipeline against test cases")
    evaluate_parser.add_argument("--prompt", required=True)
    evaluate_parser.add_argument("--model", required=True)
    evaluate_parser.add_argument("--test-cases", required=True)

    args = parser.parse_args()

    if args.command == "evaluate":
        asyncio.run(run_evaluate(args))


if __name__ == "__main__":  # pragma: no cover
    main()
```
Save, close.

### Step 0.5: Add tests for the new shared module

**Run in PowerShell:**
```powershell
notepad tests\core\test_llm_client.py
```

**Paste into `backend/tests/core/test_llm_client.py`:**
```python
from autoeval_ops.core.llm_client import build_llm_client, EchoLLMClient


async def test_build_llm_client_returns_echo_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = build_llm_client("gpt-4")
    assert isinstance(client, EchoLLMClient)


async def test_echo_llm_client_returns_fixed_score():
    client = EchoLLMClient()
    result = await client.complete("anything")
    assert result == "50"
```
Save, close.

### Step 0.6: Re-run the full Phase 1 suite

**Run in PowerShell:**
```powershell
pytest -v --cov=autoeval_ops --cov-report=term-missing
```
Confirm: all tests pass (43 total: the original 41 plus 2 new), coverage still ≥95%, no warnings. `EchoLLMClient` and `NullToxicityScorer` are still importable from `autoeval_ops.core.cli` (via re-export) — existing `test_cli.py` should need zero changes.

### Task 0 Done When:
- [ ] `config.py` uses an absolute path for `.env`
- [ ] `llm_client.py` created, `cli.py` simplified to use it
- [ ] `NullToxicityScorer` lives in `toxicity.py`
- [ ] Full test suite passes, coverage still ≥95%

---

## Task 1: Register the GitHub App

### Step 1.1: Create the App (in browser)
1. Go to https://github.com/settings/apps/new
2. **GitHub App name:** something globally unique, e.g. `autoevalops-yourusername`
3. **Homepage URL:** your repo's URL (e.g. `https://github.com/YOUR_USERNAME/autoeval-ops`)
4. **Webhook → Active:** checked
5. **Webhook URL:** `https://example.com/github/webhook` (placeholder — `cloudflared`'s quick-tunnel URL isn't known until Task 13 starts it; you'll come back and update this field then)
6. **Webhook secret:** generate a random string (e.g. `openssl rand -hex 20` if you have git-bash/WSL, or just mash the keyboard for 30+ characters) — save it, you'll need it in Step 1.3
7. **Repository permissions:**
   - Contents: **Read-only**
   - Pull requests: **Read and write**
   - (Metadata: Read-only is enabled automatically)
8. **Subscribe to events:** check **Pull request**
9. **Where can this GitHub App be installed:** "Only on this account" is fine
10. Click **Create GitHub App**

### Step 1.2: Generate and save the private key
1. On the App's settings page, scroll to **Private keys** → **Generate a private key**
2. This downloads a `.pem` file — move it somewhere safe in your project

**Run in PowerShell (from the repo root):**
```powershell
New-Item -ItemType Directory -Force -Path backend\secrets
```
Move the downloaded `.pem` file into `backend\secrets\` and rename it to `github-app-private-key.pem`.

**Add it to `.gitignore` — this must never be committed:**
```powershell
notepad .gitignore
```
Add this line, save, close:
```text
backend/secrets/
```

### Step 1.3: Note your App ID and install the App
1. On the App's settings page, note the **App ID** (shown near the top)
2. Click **Install App** in the left sidebar → choose your account → select **Only select repositories** → choose your `autoeval-ops` repo → **Install**

### Step 1.4: Update `.env` and `.env.example`

**Run in PowerShell (from the repo root):**
```powershell
notepad .env.example
```
Replace the old `GITHUB_PRIVATE_KEY=` line with these three (renamed for clarity — a file path is more reliable than pasting a multi-line key directly into `.env`), save, close:
```ini
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=
GITHUB_WEBHOOK_SECRET=
```

**Run in PowerShell:**
```powershell
notepad .env
```
Fill in real values, save, close:
```ini
GITHUB_APP_ID=your-app-id-here
GITHUB_APP_PRIVATE_KEY_PATH=backend/secrets/github-app-private-key.pem
GITHUB_WEBHOOK_SECRET=the-same-secret-you-entered-in-step-1.1
```

### Task 1 Done When:
- [ ] GitHub App created with correct permissions and webhook URL
- [ ] Private key downloaded to `backend/secrets/` (gitignored)
- [ ] App installed on your `autoeval-ops` repo
- [ ] `.env` and `.env.example` updated with `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`, `GITHUB_WEBHOOK_SECRET`

---

## Task 2: Package Skeleton

**Run in PowerShell (from `backend/`, venv active):**
```powershell
New-Item -ItemType Directory -Force -Path src\autoeval_ops\github
New-Item -ItemType File -Force -Path src\autoeval_ops\github\__init__.py
New-Item -ItemType Directory -Force -Path tests\github
New-Item -ItemType File -Force -Path tests\github\__init__.py
```

### Task 2 Done When:
- [ ] `src/autoeval_ops/github/` and `tests/github/` exist with `__init__.py` files

---

## Task 3: GitHub App Authentication

Signs a JWT with the App's private key, exchanges it for a short-lived installation access token, and caches it until shortly before expiry.

### Step 3.1: Create `app_auth.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\app_auth.py
```

**Paste into `backend/src/autoeval_ops/github/app_auth.py`:**
```python
"""GitHub App authentication: signs a JWT with the App's private key, then
exchanges it for a short-lived installation access token, caching until
shortly before expiry."""
from __future__ import annotations
import time
from datetime import datetime

import httpx
import jwt


class GitHubAppAuth:
    def __init__(self, app_id: str, private_key: str, http_client: httpx.AsyncClient | None = None):
        self.app_id = app_id
        self.private_key = private_key
        self._http = http_client or httpx.AsyncClient()
        self._tokens: dict[int, tuple[str, float]] = {}

    def generate_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + (9 * 60), "iss": self.app_id}
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached and cached[1] > time.time() + 30:
            return cached[0]

        token_jwt = self.generate_jwt()
        resp = await self._http.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {token_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        self._tokens[installation_id] = (data["token"], expires_at)
        return data["token"]
```
Save, close.

### Step 3.2: Tests

**Run in PowerShell:**
```powershell
notepad tests\github\test_app_auth.py
```

**Paste into `backend/tests/github/test_app_auth.py`:**
```python
"""Tests for GitHubAppAuth. Uses a freshly generated throwaway RSA key
(not a real GitHub App key) purely to exercise JWT signing - no network
calls, no real credentials."""
from __future__ import annotations

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from autoeval_ops.github.app_auth import GitHubAppAuth


@pytest.fixture(scope="module")
def test_private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def make_mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_generate_jwt_has_expected_claims(test_private_key):
    auth = GitHubAppAuth(app_id="12345", private_key=test_private_key)
    token = auth.generate_jwt()
    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["iss"] == "12345"
    assert decoded["exp"] > decoded["iat"]


def test_generate_jwt_uses_rs256_algorithm(test_private_key):
    auth = GitHubAppAuth(app_id="999", private_key=test_private_key)
    token = auth.generate_jwt()
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"


async def test_get_installation_token_fetches_and_caches(test_private_key):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(
            200, json={"token": "installation-token-abc", "expires_at": "2099-01-01T00:00:00Z"}
        )

    auth = GitHubAppAuth(
        app_id="12345", private_key=test_private_key, http_client=make_mock_client(handler)
    )
    token1 = await auth.get_installation_token(999)
    token2 = await auth.get_installation_token(999)

    assert token1 == "installation-token-abc"
    assert token2 == "installation-token-abc"
    assert call_count["n"] == 1  # second call used the cache


async def test_get_installation_token_refetches_when_cache_expired(test_private_key):
    def handler(request):
        return httpx.Response(200, json={"token": "fresh-token", "expires_at": "2000-01-01T00:00:00Z"})

    auth = GitHubAppAuth(
        app_id="12345", private_key=test_private_key, http_client=make_mock_client(handler)
    )
    token = await auth.get_installation_token(1)
    assert token == "fresh-token"
```
Save, close.

### Task 3 Done When:
- [ ] `app_auth.py` created
- [ ] 4 tests pass, no network calls made

---

## Task 4: GitHub API Client

Thin async wrapper on `httpx` — matches `TECH_STACK.md`'s async commitment instead of the synchronous `PyGithub`.

### Step 4.1: Create `client.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\client.py
```

**Paste into `backend/src/autoeval_ops/github/client.py`:**
```python
"""Thin async GitHub REST API client built on httpx, per TECH_STACK.md's
commitment to httpx for async HTTP. (PyGithub is listed in requirements.txt
but unused, kept in case a future phase wants its higher-level helpers.)"""
from __future__ import annotations
import base64

import httpx


class GitHubClient:
    def __init__(self, token: str, http_client: httpx.AsyncClient | None = None):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._http = http_client or httpx.AsyncClient()

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=self._headers,
            params={"ref": ref},
        )
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    async def post_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        resp = await self._http.post(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=self._headers,
            json={"body": body},
        )
        resp.raise_for_status()
```
Save, close.

### Step 4.2: Tests

**Run in PowerShell:**
```powershell
notepad tests\github\test_client.py
```

**Paste into `backend/tests/github/test_client.py`:**
```python
"""Tests for GitHubClient. Uses httpx.MockTransport - no real network calls."""
from __future__ import annotations
import base64

import httpx
import pytest

from autoeval_ops.github.client import GitHubClient


def make_client(handler) -> GitHubClient:
    transport = httpx.MockTransport(handler)
    return GitHubClient(token="fake-token", http_client=httpx.AsyncClient(transport=transport))


async def test_get_pr_files_returns_filenames():
    def handler(request):
        assert request.headers["authorization"] == "Bearer fake-token"
        return httpx.Response(200, json=[{"filename": "prompts/summarize.txt"}])

    client = make_client(handler)
    files = await client.get_pr_files("owner", "repo", 1)
    assert files[0]["filename"] == "prompts/summarize.txt"


async def test_get_file_content_decodes_base64():
    encoded = base64.b64encode(b"Summarize: {text}").decode()

    def handler(request):
        return httpx.Response(200, json={"content": encoded})

    client = make_client(handler)
    content = await client.get_file_content("owner", "repo", "prompts/summarize.txt", "main")
    assert content == "Summarize: {text}"


async def test_post_pr_comment_sends_body():
    captured = {}

    def handler(request):
        captured["body"] = request.content
        return httpx.Response(201, json={"id": 1})

    client = make_client(handler)
    await client.post_pr_comment("owner", "repo", 1, "hello world")
    assert b"hello world" in captured["body"]


async def test_get_pr_files_raises_on_http_error():
    def handler(request):
        return httpx.Response(404, json={"message": "Not Found"})

    client = make_client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_pr_files("owner", "repo", 999)
```
Save, close.

### Task 4 Done When:
- [ ] `client.py` created
- [ ] 4 tests pass, no network calls made

---

## Task 5: Prompt Runner

The piece not in `Roadmap.md`'s original task list — actually generates outputs for the changed prompt so there's something real to evaluate.

### Step 5.1: Create `runner.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\runner.py
```

**Paste into `backend/src/autoeval_ops/github/runner.py`:**
```python
"""Runs a prompt template against a set of test cases through a real (or
injected) LLM client, producing outputs shaped for EvaluationPipeline."""
from __future__ import annotations
import time
from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class PromptRunner:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def run(self, prompt_template: str, test_cases: list[dict]) -> list[dict]:
        prepared = []
        for case in test_cases:
            rendered = prompt_template.format(text=case.get("input", ""))
            start = time.perf_counter()
            output = await self.llm_client.complete(rendered)
            latency_ms = (time.perf_counter() - start) * 1000
            prepared.append(
                {
                    "output": output,
                    "expected": case.get("expected", ""),
                    "context": case.get("context", ""),
                    "prompt": rendered,
                    "latency_ms": latency_ms,
                }
            )
        return prepared
```
Save, close.

### Step 5.2: Tests

**Run in PowerShell:**
```powershell
notepad tests\github\test_runner.py
```

**Paste into `backend/tests/github/test_runner.py`:**
```python
from autoeval_ops.github.runner import PromptRunner


class FakeLLMClient:
    def __init__(self, response: str = "a generated answer"):
        self.response = response
        self.received_prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.received_prompts.append(prompt)
        return self.response


async def test_runner_renders_prompt_template_per_case():
    client = FakeLLMClient()
    runner = PromptRunner(client)
    cases = [{"input": "hello"}, {"input": "world"}]
    await runner.run("Echo: {text}", cases)
    assert client.received_prompts == ["Echo: hello", "Echo: world"]


async def test_runner_produces_pipeline_shaped_output():
    client = FakeLLMClient(response="generated")
    runner = PromptRunner(client)
    cases = [{"input": "x", "expected": "y", "context": "z"}]
    results = await runner.run("{text}", cases)
    assert results[0]["output"] == "generated"
    assert results[0]["expected"] == "y"
    assert results[0]["context"] == "z"
    assert results[0]["latency_ms"] >= 0


async def test_runner_defaults_missing_optional_fields():
    client = FakeLLMClient()
    runner = PromptRunner(client)
    results = await runner.run("{text}", [{"input": "only input"}])
    assert results[0]["expected"] == ""
    assert results[0]["context"] == ""


async def test_runner_handles_empty_test_case_list():
    client = FakeLLMClient()
    runner = PromptRunner(client)
    results = await runner.run("{text}", [])
    assert results == []
```
Save, close.

### Task 5 Done When:
- [ ] `runner.py` created
- [ ] 4 tests pass

---

## Task 6: Evaluation Queue

In-process `asyncio.Queue`-based worker pool. Per `TECH_STACK.md`, Celery+Redis is deferred to a later phase — Redis stays unused for now.

### Step 6.1: Create `queue.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\queue.py
```

**Paste into `backend/src/autoeval_ops/github/queue.py`:**
```python
"""In-process asyncio-based queue for evaluation jobs. Deferred to a proper
broker (Celery+Redis) in a later phase per TECH_STACK.md - sufficient for a
single backend instance."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class EvalJob:
    installation_id: int
    owner: str
    repo: str
    pr_number: int
    head_sha: str


class EvaluationQueue:
    def __init__(self, worker_count: int = 3):
        self.queue: asyncio.Queue[EvalJob] = asyncio.Queue()
        self.worker_count = worker_count
        self._workers: list[asyncio.Task] = []

    async def enqueue(self, job: EvalJob) -> None:
        await self.queue.put(job)

    def start(self, handler: Callable[[EvalJob], Awaitable[None]]) -> None:
        self._workers = [
            asyncio.create_task(self._worker(handler)) for _ in range(self.worker_count)
        ]

    async def _worker(self, handler: Callable[[EvalJob], Awaitable[None]]) -> None:
        while True:
            job = await self.queue.get()
            try:
                await handler(job)
            except Exception as exc:  # keep the worker alive on a single bad job
                print(f"AutoEvalOps job failed: {job} - {exc}")
            finally:
                self.queue.task_done()

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        self._workers = []


eval_queue = EvaluationQueue(worker_count=3)
```
Save, close.

### Step 6.2: Tests

**Run in PowerShell:**
```powershell
notepad tests\github\test_queue.py
```

**Paste into `backend/tests/github/test_queue.py`:**
```python
import asyncio

from autoeval_ops.github.queue import EvaluationQueue, EvalJob


def _job(n: int) -> EvalJob:
    return EvalJob(installation_id=1, owner="o", repo="r", pr_number=n, head_sha="abc")


async def test_queue_processes_enqueued_jobs():
    processed = []

    async def handler(job: EvalJob) -> None:
        processed.append(job.pr_number)

    queue = EvaluationQueue(worker_count=2)
    queue.start(handler)
    await queue.enqueue(_job(1))
    await queue.enqueue(_job(2))
    await queue.queue.join()
    await queue.stop()

    assert sorted(processed) == [1, 2]


async def test_queue_worker_survives_handler_exception():
    processed = []

    async def handler(job: EvalJob) -> None:
        if job.pr_number == 1:
            raise ValueError("boom")
        processed.append(job.pr_number)

    queue = EvaluationQueue(worker_count=1)
    queue.start(handler)
    await queue.enqueue(_job(1))  # this one raises
    await queue.enqueue(_job(2))  # worker must still process this one
    await queue.queue.join()
    await queue.stop()

    assert processed == [2]


async def test_stop_cancels_workers():
    async def handler(job: EvalJob) -> None:
        await asyncio.sleep(10)

    queue = EvaluationQueue(worker_count=2)
    queue.start(handler)
    await queue.stop()
    assert queue._workers == []
```
Save, close.

### Task 6 Done When:
- [ ] `queue.py` created with module-level `eval_queue` singleton
- [ ] 3 tests pass

---

## Task 7: PR Comment Formatter

### Step 7.1: Create `comment.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\comment.py
```

**Paste into `backend/src/autoeval_ops/github/comment.py`:**
```python
"""Formats an evaluation run into a Markdown PR comment."""
from __future__ import annotations

from autoeval_ops.core.pipeline import EvaluationReport

_ICON = {"pass": "PASS", "fail": "FAIL", "warning": "WARN"}


def _overall(reports: list[EvaluationReport]) -> str:
    if any(r.overall_status == "fail" for r in reports):
        return "fail"
    if any(r.overall_status == "warning" for r in reports):
        return "warning"
    return "pass"


def format_comment(prompt_name: str, reports: list[EvaluationReport]) -> str:
    overall = _overall(reports)
    lines = [
        f"## AutoEvalOps Report -- `{prompt_name}`",
        "",
        f"**Overall: {_ICON[overall]}** ({len(reports)} test case(s))",
        "",
        "| Case | Status | Correctness | Toxicity | Hallucination | Cost ($) | Latency (ms) |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, report in enumerate(reports, start=1):
        by_metric = {r.metric_name: r for r in report.results}
        lines.append(
            f"| {i} | {_ICON[report.overall_status]} | "
            f"{by_metric['correctness'].metric_value:.0f} | "
            f"{by_metric['toxicity'].metric_value:.0f} | "
            f"{by_metric['hallucination'].metric_value:.0f} | "
            f"{by_metric['cost'].metric_value:.4f} | "
            f"{by_metric['latency'].metric_value:.0f} |"
        )
    lines.append("")
    lines.append("_Posted automatically by AutoEvalOps._")
    return "\n".join(lines)
```
Save, close.

### Step 7.2: Tests

**Run in PowerShell:**
```powershell
notepad tests\github\test_comment.py
```

**Paste into `backend/tests/github/test_comment.py`:**
```python
from autoeval_ops.core.evaluator import EvaluationResult
from autoeval_ops.core.pipeline import EvaluationReport
from autoeval_ops.github.comment import format_comment


def _report(status: str) -> EvaluationReport:
    return EvaluationReport(
        results=[
            EvaluationResult("correctness", 90.0, status),
            EvaluationResult("toxicity", 5.0, "pass"),
            EvaluationResult("hallucination", 80.0, "pass"),
            EvaluationResult("cost", 0.001, "pass"),
            EvaluationResult("latency", 200.0, "pass"),
        ]
    )


def test_format_comment_includes_prompt_name():
    body = format_comment("prompts/summarize.txt", [_report("pass")])
    assert "prompts/summarize.txt" in body


def test_format_comment_overall_pass_when_all_pass():
    body = format_comment("p", [_report("pass"), _report("pass")])
    assert "PASS" in body


def test_format_comment_overall_fail_if_any_case_fails():
    body = format_comment("p", [_report("pass"), _report("fail")])
    assert "FAIL" in body


def test_format_comment_includes_one_row_per_case():
    body = format_comment("p", [_report("pass"), _report("pass"), _report("pass")])
    table_rows = [line for line in body.splitlines() if line.startswith("|")]
    assert len(table_rows) == 5  # header + separator + 3 data rows
```
Save, close.

### Task 7 Done When:
- [ ] `comment.py` created
- [ ] 4 tests pass

---

## Task 8: Orchestrator

Wires GitHub API access, prompt execution, and evaluation together for one PR job.

### Step 8.1: Create `orchestrator.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\orchestrator.py
```

**Paste into `backend/src/autoeval_ops/github/orchestrator.py`:**
```python
"""Wires together GitHub API access, prompt execution, and evaluation for a
single PR job, then posts the results as a PR comment.

Convention: a prompt file at prompts/<name>.txt is evaluated against test
cases at eval/<name>.test_cases.json in the same repo/ref.
"""
from __future__ import annotations
import json

from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.client import GitHubClient
from autoeval_ops.github.queue import EvalJob
from autoeval_ops.github.runner import PromptRunner
from autoeval_ops.github.comment import format_comment
from autoeval_ops.core.llm_client import build_llm_client
from autoeval_ops.core.pipeline import EvaluationPipeline
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator, NullToxicityScorer
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator

PROMPT_DIR_PREFIX = "prompts/"
PROMPT_SUFFIX = ".txt"


def is_prompt_file(path: str) -> bool:
    return path.startswith(PROMPT_DIR_PREFIX) and path.endswith(PROMPT_SUFFIX)


def resolve_test_cases_path(prompt_path: str) -> str:
    return prompt_path.replace("prompts/", "eval/", 1).replace(".txt", ".test_cases.json")


def build_default_pipeline(model: str, llm_client) -> EvaluationPipeline:
    return EvaluationPipeline(
        [
            CorrectnessEvaluator(llm_client),
            ToxicityEvaluator(NullToxicityScorer()),
            HallucinationEvaluator(),
            CostEvaluator(model=model),
            LatencyEvaluator(),
        ]
    )


async def handle_eval_job(
    job: EvalJob,
    app_auth: GitHubAppAuth,
    model: str = "gpt-4",
    client_factory=GitHubClient,
) -> None:
    token = await app_auth.get_installation_token(job.installation_id)
    gh = client_factory(token)

    files = await gh.get_pr_files(job.owner, job.repo, job.pr_number)
    prompt_files = [f["filename"] for f in files if is_prompt_file(f["filename"])]
    if not prompt_files:
        return

    llm_client = build_llm_client(model)
    runner = PromptRunner(llm_client)

    for prompt_path in prompt_files:
        prompt_text = await gh.get_file_content(job.owner, job.repo, prompt_path, job.head_sha)

        tc_path = resolve_test_cases_path(prompt_path)
        try:
            test_cases_raw = await gh.get_file_content(job.owner, job.repo, tc_path, job.head_sha)
        except Exception:
            continue  # no matching test suite for this prompt, skip

        test_cases = json.loads(test_cases_raw)
        prepared_cases = await runner.run(prompt_text, test_cases)

        pipeline = build_default_pipeline(model, llm_client)
        reports = await pipeline.evaluate_batch([dict(c) for c in prepared_cases])

        comment_body = format_comment(prompt_path, reports)
        await gh.post_pr_comment(job.owner, job.repo, job.pr_number, comment_body)
```
Save, close.

### Step 8.2: Tests

**Run in PowerShell:**
```powershell
notepad tests\github\test_orchestrator.py
```

**Paste into `backend/tests/github/test_orchestrator.py`:**
```python
"""Tests for the orchestrator. Uses fakes throughout - no real network
calls, no real OpenAI key needed (falls back to EchoLLMClient)."""
from __future__ import annotations
import json

from autoeval_ops.github.orchestrator import handle_eval_job, is_prompt_file, resolve_test_cases_path
from autoeval_ops.github.queue import EvalJob
# Note: orchestrator.py's helper is named resolve_test_cases_path (not
# test_cases_path_for) - pytest collects ANY function named test_* it finds
# in a test module's namespace, including imported ones, so a plain
# "test_"-prefixed utility function would be mistakenly picked up as a test.


class FakeAppAuth:
    async def get_installation_token(self, installation_id: int) -> str:
        return "fake-token"


class FakeGitHubClient:
    def __init__(self, token: str, files=None, contents=None):
        self.token = token
        self.files = files or []
        self.contents = contents or {}
        self.posted_comments: list[str] = []

    async def get_pr_files(self, owner, repo, pr_number):
        return self.files

    async def get_file_content(self, owner, repo, path, ref):
        if path not in self.contents:
            raise FileNotFoundError(path)
        return self.contents[path]

    async def post_pr_comment(self, owner, repo, pr_number, body):
        self.posted_comments.append(body)


def _job() -> EvalJob:
    return EvalJob(installation_id=1, owner="bazil", repo="autoeval-ops", pr_number=7, head_sha="abc")


def test_is_prompt_file_matches_convention():
    assert is_prompt_file("prompts/summarize.txt") is True
    assert is_prompt_file("src/main.py") is False
    assert is_prompt_file("prompts/readme.md") is False


def test_resolve_test_cases_path_derives_matching_path():
    assert resolve_test_cases_path("prompts/summarize.txt") == "eval/summarize.test_cases.json"


async def test_handle_eval_job_skips_prs_with_no_prompt_files():
    client_holder = {}

    def factory(token):
        c = FakeGitHubClient(token, files=[{"filename": "README.md"}])
        client_holder["client"] = c
        return c

    await handle_eval_job(_job(), FakeAppAuth(), client_factory=factory)
    assert client_holder["client"].posted_comments == []


async def test_handle_eval_job_skips_when_no_matching_test_cases_file():
    client_holder = {}

    def factory(token):
        c = FakeGitHubClient(
            token,
            files=[{"filename": "prompts/summarize.txt"}],
            contents={"prompts/summarize.txt": "Summarize: {text}"},
            # no eval/summarize.test_cases.json in contents -> get_file_content raises
        )
        client_holder["client"] = c
        return c

    await handle_eval_job(_job(), FakeAppAuth(), client_factory=factory)
    assert client_holder["client"].posted_comments == []


async def test_handle_eval_job_posts_comment_when_prompt_and_tests_present(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    test_cases = json.dumps([{"input": "hello", "expected": "world", "context": "hello world"}])
    client_holder = {}

    def factory(token):
        c = FakeGitHubClient(
            token,
            files=[{"filename": "prompts/summarize.txt"}],
            contents={
                "prompts/summarize.txt": "Echo: {text}",
                "eval/summarize.test_cases.json": test_cases,
            },
        )
        client_holder["client"] = c
        return c

    await handle_eval_job(_job(), FakeAppAuth(), client_factory=factory)
    assert len(client_holder["client"].posted_comments) == 1
    assert "prompts/summarize.txt" in client_holder["client"].posted_comments[0]
```
Save, close.

### Task 8 Done When:
- [ ] `orchestrator.py` created
- [ ] 5 tests pass

---

## Task 9: Webhook Receiver

Verifies GitHub's HMAC signature and enqueues a job for relevant PR events.

### Step 9.1: Create `webhook.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\webhook.py
```

**Paste into `backend/src/autoeval_ops/github/webhook.py`:**
```python
"""GitHub webhook receiver: verifies signatures and enqueues evaluation jobs."""
from __future__ import annotations
import hashlib
import hmac

from fastapi import APIRouter, Request, HTTPException, Header

from autoeval_ops.github.queue import EvalJob, eval_queue
from autoeval_ops.config import settings

router = APIRouter()

RELEVANT_ACTIONS = {"opened", "synchronize", "reopened"}


def verify_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


@router.post("/github/webhook")
async def handle_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
) -> dict:
    body = await request.body()

    if not verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    payload = await request.json()
    action = payload.get("action")
    if action not in RELEVANT_ACTIONS:
        return {"status": "ignored", "reason": f"action={action}"}

    job = EvalJob(
        installation_id=payload["installation"]["id"],
        owner=payload["repository"]["owner"]["login"],
        repo=payload["repository"]["name"],
        pr_number=payload["pull_request"]["number"],
        head_sha=payload["pull_request"]["head"]["sha"],
    )
    await eval_queue.enqueue(job)

    return {"status": "queued", "pr": job.pr_number}
```
Save, close.

### Step 9.2: Tests

**Run in PowerShell:**
```powershell
notepad tests\github\test_webhook.py
```

**Paste into `backend/tests/github/test_webhook.py`:**
```python
"""Tests for the webhook receiver: signature verification and event/action
filtering. Uses a minimal test app (just the router, no lifespan) so these
tests don't need a real private key file on disk."""
from __future__ import annotations
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autoeval_ops.github.webhook import router
from autoeval_ops.github.queue import eval_queue
from autoeval_ops.config import settings

WEBHOOK_SECRET = "test-secret"


@pytest.fixture(autouse=True)
def set_webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", WEBHOOK_SECRET)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _pr_payload(action: str = "opened") -> dict:
    return {
        "action": action,
        "installation": {"id": 42},
        "repository": {"owner": {"login": "bazil"}, "name": "autoeval-ops"},
        "pull_request": {"number": 7, "head": {"sha": "deadbeef"}},
    }


def test_rejects_invalid_signature(client):
    body = json.dumps(_pr_payload()).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 401


def test_ignores_non_pull_request_events(client):
    body = json.dumps(_pr_payload()).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_ignores_irrelevant_pr_actions(client):
    body = json.dumps(_pr_payload(action="closed")).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_enqueues_job_for_opened_pr(client):
    body = json.dumps(_pr_payload(action="opened")).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert eval_queue.queue.qsize() >= 1
    eval_queue.queue.get_nowait()  # drain so this doesn't leak into other tests


def test_enqueues_job_for_synchronize_action(client):
    body = json.dumps(_pr_payload(action="synchronize")).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    eval_queue.queue.get_nowait()
```
Save, close.

### Task 9 Done When:
- [ ] `webhook.py` created
- [ ] 5 tests pass

---

## Task 10: Minimal FastAPI App

Hosts the webhook route and starts the queue workers. Phase 3 expands this into the full backend API rather than replacing it.

### Step 10.1: Create `server.py`

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\server.py
```

**Paste into `backend/src/autoeval_ops/server.py`:**
```python
"""Minimal FastAPI app hosting the GitHub webhook receiver.
Phase 3 expands this into the full backend API rather than replacing it.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI

from autoeval_ops.github.queue import eval_queue
from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.orchestrator import handle_eval_job
from autoeval_ops.github.webhook import router as github_router
from autoeval_ops.config import settings, resolve_repo_path


def _load_app_auth() -> GitHubAppAuth:
    # .env's GITHUB_APP_PRIVATE_KEY_PATH is relative to the repo root, not
    # to whichever directory uvicorn was launched from - resolve_repo_path
    # (see config.py) makes this work regardless of cwd.
    key_path = resolve_repo_path(settings.github_app_private_key_path)
    with open(key_path, "r") as f:
        private_key = f.read()
    return GitHubAppAuth(app_id=settings.github_app_id, private_key=private_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_auth = _load_app_auth()

    async def handler(job):
        await handle_eval_job(job, app_auth)

    eval_queue.start(handler)
    yield
    await eval_queue.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(github_router)
```
Save, close.

### Step 10.2: Run it locally

**Run in PowerShell:**
```powershell
uvicorn autoeval_ops.server:app --reload --port 8000
```
In a separate PowerShell tab (keep this one running), verify the health check:
```powershell
Invoke-RestMethod http://localhost:8000/health
```
Should return `{"status": "ok"}`. Stop the server with `Ctrl+C` once confirmed.

### Step 10.3: Tests

**Run in PowerShell:**
```powershell
notepad tests\test_server.py
```

**Paste into `backend/tests/test_server.py`:**
```python
"""Tests for server.py's testable pieces: _load_app_auth() in isolation,
and the full app (health + lifespan startup/shutdown) via a temp key file."""
from __future__ import annotations

from fastapi.testclient import TestClient

from autoeval_ops.config import settings
from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.server import _load_app_auth, app


def test_load_app_auth_reads_key_file(tmp_path, monkeypatch):
    key_file = tmp_path / "key.pem"
    key_file.write_text("fake-key-content")
    monkeypatch.setattr(settings, "github_app_private_key_path", str(key_file))
    monkeypatch.setattr(settings, "github_app_id", "12345")

    app_auth = _load_app_auth()
    assert isinstance(app_auth, GitHubAppAuth)
    assert app_auth.app_id == "12345"
    assert app_auth.private_key == "fake-key-content"


def test_health_endpoint_with_full_app_lifespan(tmp_path, monkeypatch):
    key_file = tmp_path / "key.pem"
    key_file.write_text("fake-key-content")
    monkeypatch.setattr(settings, "github_app_private_key_path", str(key_file))
    monkeypatch.setattr(settings, "github_app_id", "12345")

    with TestClient(app) as client:  # triggers real lifespan startup/shutdown
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
```
Save, close.

### Task 10 Done When:
- [ ] `server.py` created
- [ ] Server starts without errors (requires `.env`'s `GITHUB_APP_ID`/`GITHUB_APP_PRIVATE_KEY_PATH` to be set correctly from Task 1)
- [ ] `/health` returns `{"status": "ok"}`

---

## Task 11: Sample Project for End-to-End Testing

A small prompt + test suite, committed to the repo root, used to trigger a real PR in Task 13.

### Step 11.1: Create the prompt file

**Run in PowerShell (from the repo root):**
```powershell
New-Item -ItemType Directory -Force -Path prompts, eval
notepad prompts\summarize.txt
```

**Paste into `prompts/summarize.txt`:**
```text
Summarize the following text in one sentence: {text}
```
Save, close.

### Step 11.2: Create the matching test cases

**Run in PowerShell:**
```powershell
notepad eval\summarize.test_cases.json
```

**Paste into `eval/summarize.test_cases.json`:**
```json
[
  {
    "input": "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the English alphabet at least once, making it a useful tool for testing typewriters, fonts, and keyboards.",
    "expected": "A pangram sentence used for testing typography, containing every letter of the alphabet.",
    "context": "The quick brown fox jumps over the lazy dog is a well-known pangram used to test fonts and keyboards."
  },
  {
    "input": "Paris is the capital and most populous city of France, known for landmarks like the Eiffel Tower and the Louvre Museum.",
    "expected": "Paris is France's capital, famous for the Eiffel Tower and the Louvre.",
    "context": "Paris is the capital and most populous city of France, known for landmarks like the Eiffel Tower and the Louvre Museum."
  }
]
```
Save, close.

### Task 11 Done When:
- [ ] `prompts/summarize.txt` and `eval/summarize.test_cases.json` exist at the repo root

---

## Task 12: Run the Full Test Suite

**Run in PowerShell (from `backend/`, venv active):**
```powershell
pytest -v --cov=autoeval_ops --cov-report=term-missing
```
Expect 74 tests total (43 from Task 0's checkpoint + 29 across Tasks 3-9 + 2 from Task 10.3's `test_server.py`), all passing, coverage comfortably above 95% (verified: 99%). Real gaps you should expect and not chase further: `OpenAILLMClient`/the real-API branch (needs a live key), `DetoxifyScorer` (detoxify was dropped), and `main()`/`__main__` (entrypoint, verified manually).

> If you see `ERROR at setup of <name>` pointing at a file that isn't a test file (e.g. `orchestrator.py`), it means a plain function got named `test_*` and pytest tried to collect it as a test via import. `resolve_test_cases_path` in Task 8 was deliberately named to avoid this — if you hit it elsewhere, rename the function.

### Task 12 Done When:
- [ ] All tests pass, no warnings
- [ ] Coverage ≥95%

---

## Task 13: Real End-to-End Test via Cloudflare Tunnel

### Step 13.1: Start the server

**Run in PowerShell (from `backend/`, venv active):**
```powershell
uvicorn autoeval_ops.server:app --reload --port 8000
```
Leave this running.

### Step 13.2: Start the tunnel

**Run in PowerShell (new tab, from anywhere):**
```powershell
cloudflared tunnel --url http://localhost:8000
```
Leave this running. Watch its output — within a few seconds it prints a line like:
```
https://random-words-here.trycloudflare.com
```
Copy that URL exactly. Unlike ngrok's inspector, `cloudflared`'s quick tunnels don't ship a local web UI for watching requests live — you'll rely on the uvicorn terminal's logs instead (Step 13.5).

### Step 13.3: Update the GitHub App's webhook URL
Go to your App's settings (https://github.com/settings/apps → your app → General) and replace the placeholder Webhook URL with the real one from Step 13.2, appending the webhook path:
```
https://random-words-here.trycloudflare.com/github/webhook
```
Click **Save changes** at the bottom of the page.

### Step 13.4: Trigger a real PR

**Simplest option — edit directly on GitHub's website:**
1. Go to your repo on GitHub, navigate to `prompts/summarize.txt`, click the pencil (edit) icon
2. Change the wording slightly (e.g. add "in a single clear sentence")
3. Commit the change with **"Create a new branch and start a pull request"** selected — GitHub creates the branch and opens the PR for you in one step

**Alternative — from your local terminal, if you prefer:**

No `.venv` needed for this — `git` doesn't touch Python packages, so it works whether or not it's active. Open a new tab (separate from the uvicorn and `cloudflared` tabs already running) and go to the repo root.

**Run in PowerShell (from the repo root):**
```powershell
git checkout -b test-phase-2-webhook
```
Edit `prompts\summarize.txt` — change the wording slightly (e.g. add "in a single clear sentence").
```powershell
git add prompts\summarize.txt
git commit -m "test: tweak summarize prompt to trigger webhook"
git push origin test-phase-2-webhook
git checkout main
```
Open a PR on GitHub from `test-phase-2-webhook` into `main`. Note the `git checkout main` at the end — switching back keeps you on `main` for Task 14's final commit, matching whichever route you took above.

### Step 13.5: Watch it work
- **uvicorn terminal**: should show an incoming `POST /github/webhook` request within a few seconds of opening the PR, handled with no tracebacks.
- **`cloudflared` terminal**: shows connection-level logs (fewer details than uvicorn's, but confirms the tunnel is passing traffic).
- **The PR itself**: within ~10-30 seconds, a comment from your GitHub App should appear with the results table.

Without a real `OPENAI_API_KEY` set, correctness will show as failing — the fallback `EchoLLMClient` always returns `"50"` against a 70-point threshold, same as Phase 1's CLI. That's expected, not a bug.

### Step 13.6: If nothing happens
Go to your App's settings → **Advanced** tab → **Recent Deliveries**. GitHub logs every webhook attempt here with the exact payload sent and the response your server returned — the single most useful debugging tool for this step. Check for a non-200 response or a delivery that never fired at all (usually a webhook URL mismatch).

### Task 13 Done When:
- [ ] A real PR against your repo triggers a webhook
- [ ] A comment posts automatically with the evaluation results table
- [ ] No unhandled errors in the uvicorn terminal

---

## Task 14: Final Commit and Verification

### Step 14.1: Return to the repo root

**Run in PowerShell:**
```powershell
deactivate
cd ..
```

### Step 14.2: Verify secrets aren't tracked

**Run in PowerShell:**
```powershell
git ls-files | Select-String -Pattern "secrets|\.pem"
```
Should return nothing. If anything shows up, untrack it:
```powershell
git rm --cached -r <path-that-showed-up>
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
git status
```
Confirm you're on `main` (Task 13.4's test PR is typically triggered by editing the file directly in GitHub's web UI, which creates its own branch there without touching your local repo — so it's normal to still be on local `main` with `prompts/`/`eval/` showing as untracked at this point).

```powershell
git add -A
git commit -m "[PHASE 2] GitHub App integration: webhook, JWT auth, prompt runner, PR comments

- Full GitHub App auth (JWT + installation tokens) via app_auth.py
- httpx-based GitHubClient (files, content, comments)
- PromptRunner: generates real outputs for the changed prompt (new addition
  beyond Roadmap.md, required for evaluation to mean anything)
- asyncio-based EvaluationQueue, in-process worker pool
- Markdown PR comment formatter
- Orchestrator wiring it all together, in-memory (no DB persistence yet -
  deferred to Phase 3 per plan)
- Minimal FastAPI app (server.py), expanded in Phase 3
- Fixed a latent config.py bug: .env now resolved via absolute path
- Verified end-to-end via Cloudflare Tunnel against a real PR
- Test coverage: see PHASE_2_STATUS.md
- Breaking changes: NO (Phase 1 suite re-verified passing after refactor)"
git push origin main
```

> If you'd rather use a feature-branch-and-PR workflow (useful if you're working with others or want a review step), create and push a branch instead: `git checkout -b phase-2-complete`, commit as above, `git push origin phase-2-complete`, then open and merge a PR on GitHub. Not required for a solo project — pushing straight to `main` is fine here.

### Final Checklist:
- [ ] GitHub App registered, installed, private key gitignored
- [ ] All Phase 2 modules built and tested (auth, client, runner, queue, comment, orchestrator, webhook, server)
- [ ] Phase 1 suite re-verified passing after the Task 0 refactor
- [ ] Real end-to-end test succeeded via Cloudflare Tunnel
- [ ] Committed and merged to `main`

---

## Next Step

Once every box above is checked, move to **Phase 3: Backend API** per `Roadmap.md`. Before starting:
1. Write `PHASE_2_STATUS.md` (same audit pattern as Phase 0/1) documenting what's built, the scope decisions confirmed here, the `config.py` bugfix, and that DB persistence is now Phase 3's job (retrofitting the orchestrator to write to Postgres alongside posting the comment).
2. `claude.md`'s Module Isolation table already points Phase 2 at `/backend/src/autoeval_ops/github/` — confirm Phase 3's `/backend/src/autoeval_ops/api/` entry is still accurate before building there.

---

## Troubleshooting Log (Phase 2)

| Symptom | Cause | Fix |
|---|---|---|
| Server crashes on startup with `FileNotFoundError` on the private key | `.env`'s `GITHUB_APP_PRIVATE_KEY_PATH` is wrong, or `config.py`'s `.env` resolution bug (fixed in Task 0) wasn't applied | Confirm Task 0 was completed, and that the path in `.env` is relative to the repo root (e.g. `backend/secrets/github-app-private-key.pem`), not relative to `backend/` |
| `pydantic_core.ValidationError: N validation errors ... Extra inputs are not permitted` on startup, listing `POSTGRES_USER`, `REDIS_URL`, `OPENAI_API_KEY`, etc. | `.env` (from Phase 0) has keys pydantic-settings doesn't recognize as declared `Settings` fields yet, and by default it errors on unknown keys | Add `extra = "ignore"` to `config.py`'s `Config` class (already included above) |
| `FileNotFoundError: backend/secrets/github-app-private-key.pem` even though the file exists at that path from the repo root | Same class of bug as the `.env` path issue: `open()` resolves relative paths against the current working directory (`backend/`, since that's where uvicorn was launched), so it was actually looking for `backend/backend/secrets/...` | Use `resolve_repo_path()` (already included above) instead of passing the raw `.env` value straight to `open()` |
| `ERROR at setup of <name>` during `pytest`, pointing at a non-test file like `orchestrator.py` | A plain utility function was named `test_*`, and pytest collects any `test_*`-named function it finds in a test module's namespace - including ones brought in by `from ... import` | Rename the utility function so it doesn't start with `test_` (see Task 8's `resolve_test_cases_path`) |
| Webhook fires successfully but no PR comment ever appears, and `orchestrator.py` seems to skip every PR | `prompts/` and `eval/` folders were created inside `backend/` instead of the repo root | Move them to the repo root — GitHub reports changed file paths relative to the repo root, so `is_prompt_file()`'s `prompts/` prefix check only matches files that actually live there |
| ngrok downloads/updates fail repeatedly: browser download stalls with "check internet connection", `Invoke-WebRequest` fails with TLS/connection-reset errors, `winget install` fails with "Access is denied" on its own link files, `ngrok update` corrupts the binary mid-update | Across three independent download methods (browser, direct HTTP, winget) all specifically targeting ngrok — strongly indicative of security software (Defender or similar) actively interfering with ngrok specifically, a category of tool (tunneling) that gets flagged more than most | Switched to Cloudflare Tunnel (`cloudflared`), installed cleanly via `winget install --id Cloudflare.cloudflared` with no equivalent issues. If you hit similar problems with `cloudflared`, check Windows Security → Protection history for blocked items first before assuming a network issue |
| `cloudflared` shows `ERR failed to dial a quic connection: timeout: no recent network activity` shortly after connecting | QUIC (UDP-based) can be unreliable on some networks/routers, or when virtual adapters (WSL/Hyper-V) complicate UDP routing | Usually self-heals within seconds (watch for `Registered tunnel connection` reappearing). If it keeps dropping during an actual test, restart with `cloudflared tunnel --url http://localhost:8000 --protocol http2` to force TCP-based HTTP/2 instead of QUIC — update the GitHub App's webhook URL to match the new tunnel URL it prints |

## PowerShell Notes
- All backend commands assume you're inside `backend/` with `.venv` activated, unless a step explicitly says otherwise (Task 1, 11, 13.4, 14 work from the repo root).
- Keep the uvicorn terminal and the `cloudflared` terminal both running simultaneously during Task 13 — use separate PowerShell tabs/windows.
- `cloudflared`'s quick-tunnel URL changes every time you restart it — re-update the GitHub App's webhook URL each session unless/until Phase 6 provides a permanent host.
- `notepad <file>` + paste remains the standard for getting code into files reliably.
