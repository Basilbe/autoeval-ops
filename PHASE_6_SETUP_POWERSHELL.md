# Phase 6: Deployment & Polish (PowerShell Edition)

> Labels as before: **"Run in PowerShell"** or **"Paste into `filename`"**.

## Scope Decisions (confirmed before building)

`Roadmap.md`'s Phase 6 is written as a SaaS launch checklist — CI/CD, custom domain, 500+ RPS load testing, full security audit, marketing/pricing page. That's the right list for an actual product launch, but this project's real goal is narrower and sharper: **a stranger should be able to see this work in under two minutes, and use it on their own repo without anyone sitting next to them running PowerShell.**

That reprioritizes the work. This guide is sequenced by what actually removes friction, not by `Roadmap.md`'s original ordering — deliberately, and documented here rather than silently:

- **Tier 1 (removes real friction):** permanent deployment (kills the `cloudflared` dance entirely), "Add Project" UI (kills the manual `Invoke-RestMethod` dance), a real LLM API key — `GOOGLE_API_KEY` by default, free tier, `OPENAI_API_KEY` supported as an alternative (kills the placeholder `50` scores), and the repo-uniqueness fix (a genuine correctness bug once more than one person can register repos).
- **Tier 2 (strengthens the showcase):** `README.md` + `POSTMORTEM.md`, and the design polish pass deferred since Phase 4.
- **Tier 3 (legitimate, lower stakes here):** Sentry, security audit, load testing, custom domain. Real work, kept in scope, but none of it makes or breaks a two-minute first impression.

Other decisions:
- **Render for the backend, Vercel for the dashboard.** Vercel is built by the Next.js team and is the natural home for the frontend, but it's serverless — incompatible with the persistent `asyncio` worker pool `EvaluationQueue` runs. The backend needs a host that keeps a process alive; Render's free tier does, with a managed Postgres alongside. Railway or Fly.io work equally well if you prefer them.
- **Managed Postgres, not self-hosted.** Backups, connection pooling, and TLS handled for you. `docker-compose` stays as the local dev setup.
- **Jaeger is not deployed.** It's a local dev tool — production traces would need a hosted backend (Grafana Tempo, Honeycomb, Datadog). `OTEL_ENABLED=false` in production for now; the code path is already guarded and this is a documented, deliberate gap.
- **Repo-uniqueness fix is a real code change, not a doc note.** Phase 4 hit this bug directly (two projects on the same repo, silently colliding). With one user that's a rare annoyance; with self-service signup it's a correctness requirement.

---

## Task 1: Fix Repo Uniqueness (Correctness Before Deployment)

Phase 4 found this the hard way: two `projects` rows both pointing at `basilbe/autoeval-ops`, and `get_project_by_repo()` silently resolving to whichever existed first, so evaluations landed under the wrong project. Fixed then by renaming one row by hand — fine for one user, not acceptable once anyone can register a repo.

### Step 1.1: Add a uniqueness constraint

**Run in PowerShell (from `backend/`, venv active):**
```powershell
notepad src\autoeval_ops\db\models.py
```
Find the `Project` class's `__table_args__` and replace it with:
```python
    __table_args__ = (
        Index("idx_projects_org_id", "org_id"),
        UniqueConstraint("github_repo_url", name="uq_projects_github_repo_url"),
    )
```
Add `UniqueConstraint` to the `sqlalchemy` import at the top of the file. Save, close.

### Step 1.2: Generate the migration

**Run in PowerShell:**
```powershell
alembic revision --autogenerate -m "unique constraint on projects.github_repo_url"
```

**Inspect what it generated before applying it:**
```powershell
Get-ChildItem alembic\versions\*.py | Sort-Object LastWriteTime | Select-Object -Last 1 | Get-Content
```
Should contain a `create_unique_constraint` call. If it's empty, `models.py` wasn't saved correctly.

### Step 1.3: Clear existing duplicates first

The migration will fail if duplicates already exist — and yours do, from Phase 4's testing.

**Run in PowerShell:**
```powershell
docker exec -it autoeval_postgres psql -U autoeval_user -d autoeval_dev -c "SELECT github_repo_url, COUNT(*) FROM projects GROUP BY github_repo_url HAVING COUNT(*) > 1;"
```
If any rows come back, resolve them before continuing — either delete the unwanted project (cascades to its evaluations, so check first) or rename its `github_repo_url` as we did in Phase 4.

### Step 1.4: Apply it

**Run in PowerShell:**
```powershell
alembic upgrade head
alembic current
```

### Step 1.5: Handle the collision in the API

A unique constraint turns a silent wrong-project bug into a database error — which is better, but the API should return a clear message rather than a 500.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\routes\projects.py
```
In `create_project`, before creating, add a duplicate check:
```python
    existing = await repository.get_project_by_repo_url(db, payload.github_repo_url)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That repository is already registered to a project.",
        )
```
Save, close.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\db\repository.py
```
Add this helper alongside the other project functions, save, close:
```python
async def get_project_by_repo_url(db: AsyncSession, github_repo_url: str) -> Project | None:
    """Duplicate check for project registration. Uses the same
    normalization as get_project_by_repo so 'https://github.com/O/R' and
    'o/r' are correctly treated as the same repository."""
    normalized = normalize_repo(github_repo_url)
    result = await db.execute(select(Project).where(Project.github_repo_url == normalized))
    return result.scalars().first()
```

### Task 1 Done When:
- [ ] `UniqueConstraint` on `projects.github_repo_url` in `models.py`
- [ ] Migration generated and applied; `alembic current` shows the new head
- [ ] No duplicate `github_repo_url` rows remain
- [ ] `POST /api/v1/projects` returns 409 (not 500) for an already-registered repo

---

## Task 2: "Add Project" UI

Every project so far has been registered by hand — grab a Clerk token from DevTools, run `Invoke-RestMethod`. That's not self-service. This closes the gap.

### Step 2.1: Extend the API client

**Run in PowerShell (from `dashboard/`):**
```powershell
notepad src\lib\api.ts
```
Add these interfaces alongside the existing ones:
```typescript
export interface Organization {
  id: string;
  name: string;
  plan: string;
  created_at: string;
}

export interface CreateProjectInput {
  name: string;
  github_repo_url: string;
}
```

Add a `postRequest` helper below the existing `request` function:
```typescript
async function postRequest<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const parsed = await res.json();
      if (parsed?.detail) detail = parsed.detail;
    } catch {
      // response wasn't JSON - fall back to the status code
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}
```

Then add these to the exported `api` object:
```typescript
  listOrganizations: (token: string) =>
    request<Organization[]>("/api/v1/organizations", token),
  createOrganization: (token: string, name: string) =>
    postRequest<Organization>("/api/v1/organizations", token, { name }),
  createProject: (token: string, orgId: string, input: CreateProjectInput) =>
    postRequest<Project>(`/api/v1/projects?org_id=${orgId}`, token, input),
```
Save, close.

### Step 2.2: Server action

Keeps the Clerk token server-side — it never reaches the browser, unlike the manual DevTools approach we've been using.

**Run in PowerShell:**
```powershell
notepad src\app\actions.ts
```

**Paste (new file):**
```typescript
"use server";

import { auth } from "@clerk/nextjs/server";
import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";

export type CreateProjectState = { error: string | null };

export async function createProjectAction(
  _prev: CreateProjectState,
  formData: FormData
): Promise<CreateProjectState> {
  const { userId, getToken } = await auth();
  if (!userId) return { error: "Not signed in." };

  const name = String(formData.get("name") ?? "").trim();
  const repoUrl = String(formData.get("github_repo_url") ?? "").trim();

  if (!name || !repoUrl) {
    return { error: "Both a project name and a repository URL are required." };
  }

  const token = (await getToken()) ?? "";

  try {
    // Every project needs an owning organization. Reuse the first one if
    // the user has any; otherwise create a default so first-time users
    // don't have to think about organizations at all.
    const orgs = await api.listOrganizations(token);
    const org = orgs.length > 0 ? orgs[0] : await api.createOrganization(token, "My Org");

    await api.createProject(token, org.id, { name, github_repo_url: repoUrl });
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Could not create project." };
  }

  revalidatePath("/");
  return { error: null };
}
```
Save, close.

### Step 2.3: The form component

**Run in PowerShell:**
```powershell
notepad src\components\AddProjectForm.tsx
```

**Paste (new file):**
```tsx
"use client";

import { useActionState } from "react";
import { createProjectAction, type CreateProjectState } from "@/app/actions";

const initialState: CreateProjectState = { error: null };

export function AddProjectForm() {
  const [state, formAction, pending] = useActionState(createProjectAction, initialState);

  return (
    <form action={formAction} className="mb-6 rounded border border-ink-raised p-4">
      <h2 className="mb-3 text-sm uppercase tracking-wide text-bone-dim">Add a project</h2>

      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          name="name"
          placeholder="Project name"
          required
          className="flex-1 rounded border border-ink-raised bg-ink px-3 py-2 text-sm outline-none transition-colors duration-150 focus:border-acid"
        />
        <input
          name="github_repo_url"
          placeholder="owner/repo or https://github.com/owner/repo"
          required
          className="flex-[2] rounded border border-ink-raised bg-ink px-3 py-2 text-sm outline-none transition-colors duration-150 focus:border-acid"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded bg-acid px-4 py-2 text-sm font-medium text-ink transition-opacity duration-150 hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Adding..." : "Add"}
        </button>
      </div>

      {state.error ? <p className="mt-3 text-sm text-fail">{state.error}</p> : null}

      <p className="mt-3 text-xs text-bone-dim">
        Install the AutoEvalOps GitHub App on this repository, then add{" "}
        <code className="text-bone">prompts/*.txt</code> and matching{" "}
        <code className="text-bone">eval/*.test_cases.json</code> files. Evaluations run
        automatically on every pull request that touches a prompt.
      </p>
    </form>
  );
}
```
Save, close.

> `useActionState` is React 19 / Next 15+. On older versions the equivalent is `useFormState` from `react-dom`. This project is on Next 16, so `useActionState` is correct.

### Step 2.4: Add it to the projects page

**Run in PowerShell:**
```powershell
notepad src\app\page.tsx
```
Add the import alongside the others:
```tsx
import { AddProjectForm } from "@/components/AddProjectForm";
```
Then place `<AddProjectForm />` directly below the header block, above the projects list:
```tsx
      <AddProjectForm />
```
Save, close.

### Task 2 Done When:
- [ ] `api.ts` has `listOrganizations`, `createOrganization`, `createProject`
- [ ] `actions.ts` server action created (token stays server-side)
- [ ] `AddProjectForm` renders on the projects page
- [ ] Submitting the form creates a project without touching PowerShell

---

## Task 3: Real LLM Evaluation

Every result so far - every `50.00 FAIL` across five phases - came from `EchoLLMClient`, the placeholder used when no API key is set. That was correct for proving infrastructure. It is not a demo. A stranger's first real evaluation showing obviously-fake numbers undercuts the whole thing.

**Using Google AI Studio (Gemini) instead of OpenAI.** Google's free tier is rate-limited rather than metered - no card required, no per-call cost - which fits a portfolio project evaluated occasionally far better than paying OpenAI per request. `llm_client.py`'s `LLMClient` protocol was built in Phase 1 specifically so the provider is swappable; nothing downstream (the pipeline, the orchestrator, the CLI) knows or cares which one is actually running.

### Step 3.1: Add GeminiLLMClient

**Run in PowerShell (from `backend/`, venv active):**
```powershell
notepad requirements.txt
```
Add, save, close:
```text
google-generativeai
```
```powershell
pip install -r requirements.txt
```

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\core\llm_client.py
```
**Paste (full replacement):**
```python
"""Shared LLM client used by both the CLI (Phase 1) and the GitHub
orchestrator (Phase 2) - one implementation of 'talk to the real model, or
fall back to a placeholder' instead of two.

Phase 6 adds GeminiLLMClient alongside OpenAILLMClient. Google AI
Studio's free tier is rate-limited rather than metered, which is a
better fit for a portfolio demo evaluated occasionally than paying per
call to OpenAI - build_llm_client checks GOOGLE_API_KEY first for that
reason. Both clients implement the same LLMClient protocol, so nothing
downstream (the pipeline, the orchestrator, the CLI) needs to know or
care which provider is actually in use.
"""
from __future__ import annotations
import os
from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class EchoLLMClient:
    """Fallback used when no API key is set, so callers still run
    end-to-end for local demos without hitting a real API."""

    async def complete(self, prompt: str) -> str:
        return "50"


class GeminiLLMClient:  # pragma: no cover - requires a real GOOGLE_API_KEY
    """Google AI Studio's Gemini API. Free tier, no card required -
    rate-limited (requests per minute/day) rather than billed per call."""

    def __init__(self, model: str, api_key: str):
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    async def complete(self, prompt: str) -> str:
        response = await self._model.generate_content_async(prompt)
        return response.text or ""


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
    """GOOGLE_API_KEY is checked first - see the module docstring for why.
    OPENAI_API_KEY still works if that's what's configured instead."""
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:  # pragma: no cover - requires a real GOOGLE_API_KEY
        return GeminiLLMClient(model=model, api_key=google_key)

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:  # pragma: no cover - requires a real OPENAI_API_KEY
        return OpenAILLMClient(model=model, api_key=openai_key)

    return EchoLLMClient()
```
Save, close.

### Step 3.2: Get a Google AI Studio API key

1. Go to https://aistudio.google.com/apikey
2. Sign in with a Google account, **Create API key**
3. No billing setup required for the free tier

### Step 3.3: Set it locally

**Run in PowerShell (from the repo root):**
```powershell
notepad .env
```
Add, save, close:
```ini
GOOGLE_API_KEY=your-real-key
```

**Run in PowerShell (from the repo root):**
```powershell
notepad .env.example
```
Add, save, close:
```ini
GOOGLE_API_KEY=
```

### Step 3.4: Update the default model name

Wherever `"gpt-4"` appears as a default model string, it's now the wrong provider's naming.

**Run in PowerShell (from `backend/`):**
```powershell
Select-String -Path src\autoeval_ops\github\orchestrator.py -Pattern "gpt-4"
```
If found (likely `handle_eval_job`'s `model: str = "gpt-4"` default), change it to:
```python
model: str = "gemini-1.5-flash",
```

### Step 3.5: Verify real scoring works

Restart the backend, then re-run the CLI from Phase 1 - the fastest way to confirm real scoring without waiting on a webhook:

**Run in PowerShell (from `backend/`, venv active):**
```powershell
python -m autoeval_ops.core.cli evaluate --prompt "Summarize: {text}" --model gemini-1.5-flash --test-cases test_cases.json
```

The warning about a placeholder LLM client should be **gone**, and correctness scores should now vary per test case rather than all being exactly `50`. That variation is the proof it's real.

> If you get an auth error, confirm `GOOGLE_API_KEY` is set and the CLI's process actually loaded `.env` (same class of issue Phase 0 hit with `.env` path resolution).

> **Keeping OpenAI as a documented alternative, not removing it.** If you'd rather pay for OpenAI's models specifically, setting `OPENAI_API_KEY` instead of `GOOGLE_API_KEY` still works unchanged - `build_llm_client` falls through to it automatically.

### Task 3 Done When:
- [ ] `GeminiLLMClient` added to `llm_client.py`, `OpenAILLMClient` kept as an alternative
- [ ] `GOOGLE_API_KEY` set in `.env` and documented (blank) in `.env.example`
- [ ] Default model string updated from `gpt-4` to a real Gemini model
- [ ] CLI runs with no placeholder warning
- [ ] Correctness scores vary per test case instead of all being `50`

---

## Task 4: Deploy the Backend

Render's free tier keeps a process alive (unlike serverless), which `EvaluationQueue`'s worker pool requires. Railway or Fly.io are equivalent alternatives.

### Step 4.1: Production entrypoint config

**Run in PowerShell (from the repo root):**
```powershell
notepad render.yaml
```

**Paste (new file):**
```yaml
services:
  - type: web
    name: autoevalops-api
    runtime: python
    rootDir: backend
    buildCommand: "pip install -r requirements.txt && pip install -e ."
    startCommand: "alembic upgrade head && uvicorn autoeval_ops.server:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: PYTHON_VERSION
        value: "3.11.9"
      - key: OTEL_ENABLED
        value: "false"
      - key: DATABASE_URL
        fromDatabase:
          name: autoevalops-db
          property: connectionString

databases:
  - name: autoevalops-db
    databaseName: autoeval
    user: autoeval_user
```
Save, close.

> `alembic upgrade head` runs on every deploy — the schema stays in sync automatically. This is exactly what Phase 3's Alembic adoption was for; hand-running `schema.sql` would have been unworkable here.

> `OTEL_ENABLED=false` in production: Jaeger is a local dev tool and isn't deployed. The tracing code path is already guarded by this flag, so it cleanly no-ops. Documented as a deliberate gap.

**Commit and push this file before continuing** — Render's Blueprint feature (Step 4.2, Option A) reads `render.yaml` directly from GitHub, not from your local machine:
```powershell
git add render.yaml
git commit -m "[PHASE 6] Add Render Blueprint config"
git push origin main
```

### Step 4.2: Deploy

**Two ways to do this — pick one.** Render's Blueprint feature (Option A) reads `render.yaml` and provisions everything in one step, but it prompted for a credit card during testing even on the free tier — apparently specific to provisioning a web service *and* a database together via Blueprint, since individually-created free resources are more consistently reported as not requiring one. Option B creates the same two resources by hand through Render's dashboard forms instead, and was confirmed not to prompt for a card.

**Option A — Blueprint (may ask for a card):**
1. Go to https://render.com, sign up, connect your GitHub account
2. **New → Blueprint**, select the `autoeval-ops` repo — Render reads `render.yaml` and provisions both the service and the database
3. If it prompts for a card and you'd rather not enter one, back out and use Option B instead

**Option B — Manual creation (confirmed no card required):**

**Database first:**
1. Render dashboard → **New +** → **PostgreSQL**
2. Name: `autoevalops-db`, Database: `autoeval`, User: `autoeval_user`
3. Plan: **Free** → **Create Database**
4. Once created, open it and copy the **Internal Database URL** — needed in the next step

**Then the web service**, mirroring `render.yaml`'s content into the dashboard's fields instead of letting it be read automatically:
1. Render dashboard → **New +** → **Web Service**
2. Select the `autoeval-ops` repo
3. **Name:** `autoevalops-api`
4. **Root Directory:** `backend`
5. **Runtime:** `Python 3`
6. **Build Command:** `pip install -r requirements.txt && pip install -e .`
7. **Start Command:** `alembic upgrade head && uvicorn autoeval_ops.server:app --host 0.0.0.0 --port $PORT`
8. **Plan:** **Free**
9. Scroll to **Environment Variables**, add `PYTHON_VERSION=3.11.9`, `OTEL_ENABLED=false`, and `DATABASE_URL` = the Internal Database URL copied above
10. **Create Web Service**

`render.yaml` stays in the repo either way — harmless if unused, and documents the intended config for anyone who later wants to switch to Blueprint.

**Whichever option you used**, once the web service exists, open its **Environment** tab and add the remaining secrets (they must never be committed):
   - `GITHUB_APP_ID`
   - `GITHUB_WEBHOOK_SECRET`
   - `GOOGLE_API_KEY`
   - `OPENAI_API_KEY` (only if you're using OpenAI instead of/alongside Gemini)
   - `CLERK_SECRET_KEY`
   - `CLERK_JWKS_URL`

The GitHub App private key is a file, not a simple value — look for a **Secret Files** section in the same environment settings area, add one named `github-app-private-key.pem` with the key's contents, note the mount path Render reports, and set `GITHUB_APP_PRIVATE_KEY_PATH` to that path (typically `/etc/secrets/github-app-private-key.pem`).

### Step 4.3: Fix the DATABASE_URL scheme

Render provides a `postgresql://` connection string. This project needs `postgresql+asyncpg://` — the exact issue that broke Phase 3's Alembic setup.

**Run in PowerShell (from `backend/`):**
```powershell
notepad src\autoeval_ops\config.py
```
Add this normalization inside `Settings`, after the field declarations, save, close:
```python
    @property
    def async_database_url(self) -> str:
        """Managed Postgres providers hand out postgresql:// URLs, which
        route SQLAlchemy to the sync psycopg2 driver. This project uses
        asyncpg. Normalizing here means the deployment platform's value
        can be used verbatim without hand-editing."""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url
```

Then update both places that read the URL:
```powershell
notepad src\autoeval_ops\db\session.py
```
Change `settings.database_url` to `settings.async_database_url` in `get_engine()`. Save, close.
```powershell
notepad alembic\env.py
```
Change `settings.database_url` to `settings.async_database_url`. Save, close.

### Step 4.4: Verify the deployment

**Run in PowerShell:**
```powershell
Invoke-RestMethod https://your-service-name.onrender.com/health
Invoke-RestMethod https://your-service-name.onrender.com/api/v1/status
```
Both should return real JSON. The second one working with no auth header confirms the public endpoint survived deployment.

> Render's free tier sleeps after inactivity — the first request after idle can take 30-60 seconds. Worth knowing before assuming something's broken, and worth mentioning to anyone you send the link to.

### Task 4 Done When:
- [ ] Backend deployed, `/health` and `/api/v1/status` reachable over HTTPS
- [ ] Migrations ran automatically on deploy
- [ ] All secrets set as environment variables / secret files, none committed

---

## Task 5: Point the GitHub App at Production

This is the moment the `cloudflared` dance ends permanently.

1. Go to https://github.com/settings/apps → your app → **General**
2. Set **Webhook URL** to:
   ```
   https://your-service-name.onrender.com/github/webhook
   ```
3. **Save changes**

That URL never changes again. No tunnel, no per-session updates.

### Task 5 Done When:
- [ ] Webhook URL points at the deployed backend
- [ ] `cloudflared` is no longer needed for webhook testing

---

## Task 6: Deploy the Dashboard

**Run in PowerShell (from the repo root):**
```powershell
git add -A
git commit -m "[PHASE 6] Uniqueness constraint, Add Project UI, deployment config"
git push origin main
```

1. Go to https://vercel.com, sign up, **Add New → Project**, import the `autoeval-ops` repo
2. Set **Root Directory** to `dashboard`
3. Add environment variables:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
   - `CLERK_SECRET_KEY`
   - `NEXT_PUBLIC_API_URL` → your Render backend URL (e.g. `https://your-service-name.onrender.com`)
4. **Deploy**

### Step 6.1: Update backend CORS

The dashboard is no longer on `localhost:3000`.

**Run in PowerShell (from `backend/`):**
```powershell
notepad src\autoeval_ops\server.py
```
Change the CORS origins to include the deployed dashboard, save, close:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-dashboard.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Commit and push — Render redeploys automatically.

### Step 6.2: Clerk domain — usually nothing to do here

**Correction, found the hard way:** Clerk's **Domains** dashboard page (Configure → Developers → Domains) only applies to **Production** Clerk instances, which require a real DNS-verified custom domain — not a page for allowlisting arbitrary URLs like a Vercel deploy address. This project is still on a **Development** Clerk instance (same `*.clerk.accounts.dev` domain used throughout every prior phase), and development instances aren't domain-restricted at all — the keys work on any origin. There's nothing to add here for a Vercel `*.vercel.app` URL.

**If sign-in fails on the deployed dashboard anyway**, it's not a domain allowlist problem — check these instead:
1. `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` are actually set in Vercel's **Environment Variables**, specifically for the **Production** environment (not just Preview/Development — Vercel scopes env vars per-environment)
2. After adding/editing env vars in Vercel, a **redeploy** is required — they aren't picked up by an already-running deployment

**Only if you later switch to a real Clerk Production instance** (via the "Go to prod" button, which requires owning and DNS-verifying a real domain) does this Domains page become relevant — genuinely out of scope for a portfolio deployment on free-tier Vercel/Render domains.

### Task 6 Done When:
- [ ] Dashboard deployed and loading over HTTPS
- [ ] Clerk sign-in works on the deployed domain
- [ ] Projects list loads real data from the deployed backend

---

## Task 7: End-to-End Verification on Production

The real test: does this work for someone who isn't you, on a machine that isn't yours?

1. Open the deployed dashboard in an **Incognito window**
2. Sign up with a fresh email — confirms Phase 4's JIT provisioning works in production
3. Use the **Add Project** form to register a repo (Task 2's whole point — no PowerShell)
4. Install the GitHub App on that repo if it isn't already
5. Add `prompts/example.txt` and `eval/example.test_cases.json` to that repo
6. Open a PR touching the prompt file
7. Confirm: a comment appears on the PR, **with real varying scores** rather than `50` across the board
8. Confirm the evaluation appears in the dashboard, and clicking through shows real per-metric detail
9. Open `https://your-dashboard.vercel.app/status` in Incognito — public status page, no login

### Task 7 Done When:
- [ ] A fresh account can sign up, add a project, and see real evaluations — start to finish, no terminal
- [ ] PR comments show genuine varying scores from a real model
- [ ] Public status page works on the deployed domain

---

## Task 8: README and Postmortem

Arguably the highest-leverage task in this phase. Most people evaluating this project will read before they click — and six phases of real debugging is unusually good material.

### Step 8.1: README

**Run in PowerShell (from the repo root):**
```powershell
notepad README.md
```

Structure it as:
```markdown
# AutoEvalOps

Automated LLM prompt evaluation on every pull request. Change a prompt,
open a PR, get correctness/toxicity/hallucination/cost/latency scores
posted as a comment before you merge.

**Live:** https://your-dashboard.vercel.app
**Status:** https://your-dashboard.vercel.app/status (public, no login)

## How it works
[the GitHub PR -> webhook -> queue -> evaluators -> PR comment + dashboard flow]

## Try it on your own repo
1. Install the GitHub App
2. Add the project in the dashboard
3. Add prompts/*.txt and matching eval/*.test_cases.json
4. Open a PR

## Architecture
[brief - link to docs/ARCHITECTURE.md for detail]

## Tech stack
[from docs/TECH_STACK.md]

## Running locally
[docker-compose up, venv setup, the two dev servers]
```
Save, close.

### Step 8.2: Postmortem

This is the differentiator. Everyone's portfolio project has a README; almost none have an honest account of what actually broke and why.

**Run in PowerShell:**
```powershell
notepad docs\POSTMORTEM.md
```

Draw directly from `PHASE_0_STATUS.md` through `PHASE_5_STATUS.md` — the real material is already written. Worth covering:

**Architectural trade-offs made and why:**
- `asyncio.Queue` over Celery (single instance, no broker to operate)
- Postgres over ClickHouse for traces (the table sat unused until Phase 5; a second database was weight without benefit)
- Lexical-overlap hallucination checking over embeddings (pgvector deferred in Phase 0)
- Character-count token estimation over `tiktoken` (avoided a dependency for arithmetic)
- Per-page auth checks over middleware route-matching (followed Clerk's own deprecation guidance)

**Bugs found only through real end-to-end testing, not unit tests:**
- `PromptRunner`'s `str.format()` crashing on literal braces in prompts — every mocked test used brace-free templates
- `config.py` resolving `.env` relative to cwd — invisible until Phase 3 actually needed a real value
- Antivirus TLS interception breaking all outbound HTTPS from the venv
- Clerk's session token having no `email` claim by default
- Clerk logins never creating backend users (JIT provisioning gap)
- Two projects on one repo silently colliding in `get_project_by_repo()`

**Testing insights worth writing up:**
- The `coverage.py` investigation: `concurrency = ["thread", "greenlet"]` needed together for FastAPI's `TestClient` and SQLAlchemy's async ORM to both be traced — three rounds to isolate
- Fixture scope: the same `conftest.py` visibility bug surfaced twice, phases apart
- What mocked tests genuinely cannot catch, and why every phase ended in a live walkthrough

**What you'd do differently**, honestly.

### Task 8 Done When:
- [ ] `README.md` has live links and a clear "try it yourself" path
- [ ] `docs/POSTMORTEM.md` covers trade-offs, real bugs, and testing insights

---

## Task 9: Update Deferred Documentation

Two follow-ups have been carried since Phase 4 — worth closing now rather than leaving permanently open.

**Run in PowerShell:**
```powershell
notepad docs\TECH_STACK.md
```
Add, save, close:
```markdown
## Additions After the Original Lock (documented deviations)
- **PyJWT[crypto]** (Phase 2) — GitHub App JWT signing
- **truststore** (Phase 4) — trusts Windows' native certificate store, fixing TLS interception by local HTTPS-scanning antivirus
- **OpenTelemetry OTLP exporter** (Phase 5) — replaces the deprecated Jaeger exporter originally specified
- **Jaeger** (Phase 5, local dev only) — trace visualization; not deployed to production
- **google-generativeai** (Phase 6) — Google AI Studio's Gemini API, checked first by `build_llm_client`; free tier (rate-limited, not metered) is a better fit for a demo than paying OpenAI per call. `OPENAI_API_KEY` still works as a documented alternative via the same `LLMClient` protocol.
- **Render** (Phase 6) — backend hosting; needs a persistent process for the asyncio worker pool, which serverless can't provide
- **Vercel** (Phase 6) — dashboard hosting
```

**Run in PowerShell (from the repo root):**
```powershell
notepad .env.example
```
Confirm every variable the app actually reads is present (blank values, no secrets): `DATABASE_URL`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`, `GITHUB_WEBHOOK_SECRET`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `OTEL_ENABLED`, `OTEL_EXPORTER_ENDPOINT`.

### Task 9 Done When:
- [ ] `TECH_STACK.md` documents all post-lock additions
- [ ] `.env.example` matches what the app actually reads

---

## Task 10: Security Pass

Not a full audit — a focused check on the things that actually matter now that this is publicly reachable.

**Run in PowerShell (from the repo root):**
```powershell
git ls-files | Select-String -Pattern "\.env$|\.pem$|secrets/"
```
Must return nothing.

```powershell
git log --all --oneline -S "sk-" -- . | Select-Object -First 5
```
Checks whether an API key was ever committed historically. If anything turns up, rotate that key immediately — history rewriting is a separate, larger job.

**Confirm by inspection:**
- [ ] Rate limiting active (`slowapi`, added Phase 3)
- [ ] CORS lists only your real origins, not `*`
- [ ] `/api/v1/status` still exposes only aggregates — the Phase 5 regression test covers this, confirm it still passes
- [ ] Webhook HMAC verification still enforced (Phase 2's `verify_signature`)
- [ ] API keys stored bcrypt-hashed, never in plaintext

**Rotate the webhook secret** — it was pasted into a chat during Phase 3. Generate a new one, update it in both the GitHub App settings and Render's environment variables.

### Task 10 Done When:
- [ ] No secrets tracked in git, historically or currently
- [ ] Webhook secret rotated
- [ ] Security checklist reviewed

---

## Task 11: Load Testing

`Roadmap.md` asks for 500+ RPS. Worth being honest about what that means here: the bottleneck is OpenAI's API and rate limits, not this code. What's actually worth measuring is that the queue and connection pool behave under concurrent load without deadlocking or leaking.

**Run in PowerShell (from `backend/`, venv active):**
```powershell
pip install locust
notepad locustfile.py
```

**Paste (new file):**
```python
"""Load test for the public status endpoint - the only route that can be
hit without auth, and the one most likely to see real traffic.

Deliberately not load-testing the evaluation pipeline: that's bounded by
OpenAI's rate limits and costs real money per request, so hammering it
would measure their infrastructure and bill you for the privilege.
"""
from locust import HttpUser, task, between


class StatusPageUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def status(self):
        self.client.get("/api/v1/status")

    @task(1)
    def health(self):
        self.client.get("/health")
```
Save, close.

**Run in PowerShell:**
```powershell
locust -f locustfile.py --host https://your-service-name.onrender.com
```
Open http://localhost:8089, start with 50 users, watch p95 latency and error rate. Record the results — they belong in `POSTMORTEM.md`.

> Free-tier hosting will fall over well before 500 RPS. That's a hosting-tier limitation, not a code defect, and saying so plainly in the postmortem is more credible than quietly omitting the number.

### Task 11 Done When:
- [ ] Load test run against the deployed backend
- [ ] Results recorded in `POSTMORTEM.md` with honest context about tier limits

---

## Task 12: Sentry (Deferred From Phase 5)

Now there's a real production deployment to attach it to.

**Run in PowerShell (from `backend/`, venv active):**
```powershell
notepad requirements.txt
```
Add, save, close:
```text
sentry-sdk[fastapi]
```
```powershell
pip install -r requirements.txt
notepad src\autoeval_ops\server.py
```
Add near the top, after the `truststore` block and before `configure_tracing()`:
```python
import sentry_sdk

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        environment=settings.environment,
    )
```
Save, close.

Add the setting:
```powershell
notepad src\autoeval_ops\config.py
```
```python
    sentry_dsn: str = ""
```
Sign up at https://sentry.io, create a Python/FastAPI project, copy the DSN, and set `SENTRY_DSN` in Render's environment variables.

### Task 12 Done When:
- [ ] Sentry initialized, guarded so a missing DSN is a clean no-op
- [ ] `SENTRY_DSN` set in production
- [ ] A deliberately triggered error appears in Sentry

---

## Task 13: Design Polish Pass (Deferred From Phase 4)

The original Phase 4 brief asked for something "intriguing" that "shouldn't look like a typical AI-generated website." What shipped is clean and consistent but was never actually iterated on visually — the Clerk auth crisis consumed that phase.

This is the natural moment: the pages are stable, the data is real, and there's now a public surface strangers will see.

**Highest-value targets, in order:**
1. **`/status`** — fully public, no login required, most likely to be the first thing a stranger sees
2. **The projects list** — the first authenticated view
3. **Eval detail** — the page that actually shows the product working

Worth considering Claude Design here specifically, per the discussion at the end of Phase 4: visual iteration is faster to judge by eye than to specify in words, and the backend contract is stable now, so nothing about this risks breaking functionality.

**Guardrails, so polish doesn't undo the deliberate choices:**
- Keep motion functional and fast (150-250ms) — no scroll-triggered reveals on a tool people check daily
- Keep monospace for data, sans for prose — that split is what most distinguishes this from generic AI-generated design
- The terminal aesthetic was chosen for a reason; refine it rather than replacing it

### Task 13 Done When:
- [ ] At least the public `/status` page has had a real visual pass
- [ ] Motion still functional, not decorative
- [ ] Deployed and verified on the live domain

---

## Task 14: CI/CD

Both Render and Vercel already auto-deploy on push to `main`. What's missing is tests running *before* that happens.

**Run in PowerShell (from the repo root):**
```powershell
New-Item -ItemType Directory -Force -Path .github\workflows
notepad .github\workflows\test.yml
```

**Paste (new file):**
```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: autoeval_user
          POSTGRES_PASSWORD: dev_password
          POSTGRES_DB: autoeval_dev
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        working-directory: backend
        run: |
          pip install -r requirements.txt
          pip install -e .

      - name: Run migrations
        working-directory: backend
        env:
          DATABASE_URL: postgresql+asyncpg://autoeval_user:dev_password@localhost:5432/autoeval_dev
        run: alembic upgrade head

      - name: Run tests
        working-directory: backend
        env:
          DATABASE_URL: postgresql+asyncpg://autoeval_user:dev_password@localhost:5432/autoeval_dev
          OTEL_ENABLED: "false"
        run: pytest -v --cov=autoeval_ops --cov-report=term-missing
```
Save, close.

Push it, then check the **Actions** tab on GitHub to confirm it runs green.

> There's a satisfying symmetry here: this project evaluates prompts on every PR, and now has its own tests running on every PR.

### Task 14 Done When:
- [ ] Workflow runs on push and PR
- [ ] All 149+ tests pass in CI
- [ ] Badge added to `README.md` (optional)

---

## Task 15: Final Commit and Verification

**Run in PowerShell (from `backend/`, venv active):**
```powershell
pytest -v --cov=autoeval_ops --cov-report=term-missing
```

**Run in PowerShell (from the repo root):**
```powershell
git status
git add -A
git commit -m "[PHASE 6] Deployment, self-service project creation, docs

- Unique constraint on projects.github_repo_url (fixes the silent
  wrong-project bug found in Phase 4; a correctness requirement once
  anyone can register a repo)
- Add Project UI - registration no longer requires manual API calls
- Real LLM evaluation via Google AI Studio's free-tier Gemini API
  (GOOGLE_API_KEY, checked first) - evaluations produce genuine, varying
  scores, not EchoLLMClient's placeholder 50. OpenAI kept as a documented
  alternative via the same LLMClient protocol.
- Backend deployed to Render (persistent process required for the
  asyncio worker pool), dashboard to Vercel, permanent webhook URL -
  cloudflared no longer needed
- DATABASE_URL scheme normalized so managed Postgres URLs work verbatim
- README + POSTMORTEM documenting architecture, trade-offs, and the
  bugs only live testing caught
- Sentry (deferred from Phase 5), CI running tests on every PR,
  security pass, load testing
- Breaking changes: NO"
git push origin main
```

### Final Checklist:
- [ ] Backend and dashboard both deployed and reachable
- [ ] Permanent webhook URL; no tunnel needed
- [ ] A stranger can sign up, add a project, and get real evaluations without a terminal
- [ ] Real LLM scoring, not placeholders
- [ ] README and POSTMORTEM complete
- [ ] CI green
- [ ] All tests passing

---

## Next Step

Write `PHASE_6_STATUS.md` (same audit pattern as prior phases).

Then the project is complete — and worth stepping back to look at what that actually means: a working CI/CD platform for LLM prompts, deployed, self-service, with six phases of honestly-documented engineering behind it.

---

## Troubleshooting Log (Phase 6)

| Symptom | Cause | Fix |
|---|---|---|
| `render.yaml` not found when creating a Render Blueprint | Blueprint reads the file from GitHub, not your local machine — it was created locally but never committed and pushed | `git add render.yaml`, commit, push, then retry (Task 4, Step 4.1) |
| Render's Blueprint flow asks for a credit card even on the free tier | Appears specific to provisioning a web service and database together via Blueprint — individually-created free resources are more consistently reported as not requiring one | Use Task 4, Step 4.2's Option B: create the Postgres database and web service separately through Render's dashboard forms, entering `render.yaml`'s values manually instead of letting Blueprint read the file |
| `alembic upgrade head` fails on the uniqueness migration | Duplicate `github_repo_url` rows already exist (very likely, from Phase 4's testing) | Resolve duplicates first (Task 1, Step 1.3) before applying |
| Render build fails on `pip install -e .` | `rootDir` isn't set to `backend`, so `pyproject.toml` isn't found | Confirm `rootDir: backend` in `render.yaml` |
| Deployed backend can't reach the database | Render hands out a `postgresql://` URL; this project needs `postgresql+asyncpg://` | Task 4, Step 4.3's `async_database_url` property normalizes it — confirm both `session.py` and `alembic/env.py` use it |
| First request to the deployed backend takes 30-60s | Render's free tier sleeps after inactivity | Expected, not a bug. Worth mentioning to anyone you send the link to |
| Clerk sign-in works locally but fails on the deployed dashboard | Almost certainly not a Clerk domain-allowlist issue — Development Clerk instances aren't domain-restricted. More likely `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`/`CLERK_SECRET_KEY` aren't set for Vercel's Production environment, or a redeploy is needed after setting them | Check Vercel env vars are scoped to Production and redeploy (Task 6, Step 6.2) |
| CORS errors from the deployed dashboard | Backend still only allows `localhost:3000` | Add the Vercel URL to `allow_origins` (Task 6, Step 6.1), push, let Render redeploy |
| GitHub App private key not found in production | It's a file, not an env var | Add as a Render **Secret File**, set `GITHUB_APP_PRIVATE_KEY_PATH` to the path Render reports |
| Evaluations still score exactly `50` after deploying | Neither `GOOGLE_API_KEY` nor `OPENAI_API_KEY` is set in production, so `build_llm_client` falls back to `EchoLLMClient` | Set `GOOGLE_API_KEY` (or `OPENAI_API_KEY`) in Render's environment variables — the local `.env` isn't deployed |
