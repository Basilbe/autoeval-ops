# Phase 4: Frontend Dashboard (PowerShell Edition)

> Labels as before: **"Run in PowerShell"** or **"Paste into `filename`"**.

## Scope Decisions
- **Logged-in tool, not a marketing page.** Data density and fast functional motion, not landing-page spectacle.
- **Terminal/CI aesthetic.** Near-black base, warm off-white text, one acid accent for pass/active, muted red for fail. Monospace for all data (scores, hashes, timestamps), sans for prose only.
- **Motion is functional, fast (150-250ms).** Counting numbers, staggered row entry, morphing status pills, designed skeleton states — not scroll reveals or entrance flourishes.
- **Scope: login → projects list → eval history → eval detail.** Nothing else this phase.
- **Design established in Claude Design first**, then implemented here in Next.js against the real Phase 3 API.
- **Clerk goes live this phase.** `CLERK_JWKS_URL` gets filled in for the first time — this is the first real external signup since the GitHub App.

---

## Prerequisites

### Clerk account

1. Sign up at https://clerk.com (free tier is fine)
2. Create an application, choose **Email** as the sign-in method (keep it simple)
3. In the Clerk dashboard, go to **API Keys** and copy:
   - **Publishable key** (`pk_test_...`)
   - **Secret key** (`sk_test_...`)
4. Go to **Configure → Sessions → JWT Templates**, or just note your Clerk **Frontend API URL** (shown on the API Keys page, looks like `https://xxx.clerk.accounts.dev`) — your JWKS URL is that plus `/.well-known/jwks.json`.

**Run in PowerShell (from the repo root):**
```powershell
notepad .env
```
Fill in the three Clerk lines that have been blank since Phase 3, save, close:
```ini
CLERK_SECRET_KEY=sk_test_your_real_key
CLERK_JWKS_URL=https://xxx.clerk.accounts.dev/.well-known/jwks.json
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_your_real_key
```

### Node.js

**Run in PowerShell:**
```powershell
node --version
```
Need 18+. If missing, install from https://nodejs.org (LTS).

### Task Done When:
- [ ] Clerk app created, keys copied
- [ ] `.env` has real `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`, `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- [ ] `node --version` shows 18+

---

## Task 1: Create the Next.js App

### Step 1.1: Remove stale Phase 0 placeholder folders first

`DEVELOPMENT_ROADMAP.md`'s original Phase 0 sketch created empty `dashboard/pages/` and `dashboard/components/` folders. If `pages/` still exists when `create-next-app` runs, Next.js treats it as a signal to scaffold the older **Pages Router** instead of the **App Router** this guide uses — even with `--app` passed explicitly.

**Run in PowerShell (from the repo root):**
```powershell
Get-ChildItem dashboard\pages, dashboard\components -ErrorAction SilentlyContinue
```
If these exist and are empty, remove them:
```powershell
Remove-Item -Recurse -Force dashboard\pages, dashboard\components -ErrorAction SilentlyContinue
```

### Step 1.2: Scaffold the app

**Run in PowerShell (from the repo root):**
```powershell
npx create-next-app@latest dashboard --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```
Accept the defaults it prompts for.

**Confirm which Next.js version actually got installed** — `create-next-app@latest` doesn't always mean the newest Next.js major:
```powershell
cd dashboard
npm list next
```

**This guide's Clerk integration (Tasks 2, 6-8) uses Next.js 15's async APIs** (`await auth()`, `params` typed as a `Promise`) and `@clerk/nextjs` v5+ (which requires Next 15+ as a peer dependency). If the check above shows `14.x.x`, upgrade before continuing:
```powershell
npm install next@latest react@latest react-dom@latest
npm install -D eslint-config-next@latest
npm list next
```
Confirm `15.x.x` or higher.

**Verify the App Router actually got created:**
```powershell
Test-Path src\app
```
Must be `True`. If `False`, Step 1.1 was likely skipped or something else claimed the `pages/` convention — delete `dashboard/` entirely and retry both steps before continuing.

### Step 1.3: Install Clerk

`clerkMiddleware`/`createRouteMatcher` (used in Task 2) only exist in `@clerk/nextjs` v5+, and current Clerk versions require Next.js 15+ as a peer dependency — this is why Step 1.2 checks/upgrades Next.js first, to avoid an `ERESOLVE` conflict here.

**Run in PowerShell:**
```powershell
npm install @clerk/nextjs@latest
npm list @clerk/nextjs
```
Confirm the version printed is `5.x.x` or higher.

### Task 1 Done When:
- [ ] `dashboard/pages` and `dashboard/components` (Phase 0 leftovers) removed
- [ ] `dashboard/src/app` exists (App Router, not Pages Router)
- [ ] `@clerk/nextjs` installed at v5+

---

## Task 2: Wire Up Clerk

> **`proxy.ts`, not `middleware.ts` — and it's still needed, just minimal.** Next.js 16 renamed the `middleware` file convention to `proxy` (same mechanism, new filename). Separately, Clerk deprecated `createRouteMatcher`/path-matching-based `auth().protect()` in favor of checking auth directly inside each page — their own guidance: *"Move auth checks into each page, layout, API route, or Server Function that accesses protected data."* But `clerkMiddleware()` itself is still required, even with no route matching inside it — it's what establishes the auth context that `await auth()` reads inside your pages. Without it, every page-level `auth()` call fails with *"Clerk: auth() was called but Clerk can't detect usage of clerkMiddleware()."* So: a bare `clerkMiddleware()` wrapper in `proxy.ts`, with all the actual protect-and-redirect logic living in each page instead (Tasks 6-8) — not a full middleware-based auth layer.

**Run in PowerShell (from `dashboard/`):**
```powershell
notepad .env.local
```
**Paste (new file):**
```ini
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_your_real_key
CLERK_SECRET_KEY=sk_test_your_real_key
NEXT_PUBLIC_API_URL=http://localhost:8000
```
Save, close. (Copy the same key values from the repo-root `.env` you filled in during Prerequisites.)

**Run in PowerShell:**
```powershell
notepad src\app\layout.tsx
```
**Paste (full replacement):**
```tsx
import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoEvalOps",
  description: "Automated LLM prompt evaluation on every pull request.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="bg-ink text-bone font-mono antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}
```
Save, close.

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path src\app\sign-in\'[[...sign-in]]', src\app\sign-up\'[[...sign-up]]'
notepad "src\app\sign-in\[[...sign-in]]\page.tsx"
```
**Paste:**
```tsx
import { SignIn } from "@clerk/nextjs";

export default function Page() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn />
    </div>
  );
}
```
Save, close.
```powershell
notepad "src\app\sign-up\[[...sign-up]]\page.tsx"
```
**Paste:**
```tsx
import { SignUp } from "@clerk/nextjs";

export default function Page() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignUp />
    </div>
  );
}
```
Save, close.

**Run in PowerShell:**
```powershell
notepad src\proxy.ts
```
**Paste (new file):**
```typescript
import { clerkMiddleware } from "@clerk/nextjs/server";

export default clerkMiddleware();

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)", "/(api|trpc)(.*)"],
};
```
Save, close. No `createRouteMatcher`, no `.protect()` — this file only establishes auth context; the actual redirect-if-unauthenticated logic lives in each page (Tasks 6-8).

### Task 2 Done When:
- [ ] `proxy.ts` created (bare `clerkMiddleware()`, no route matching)
- [ ] `layout.tsx`, sign-in/sign-up pages created
- [ ] `.env.local` has real Clerk keys

---

## Task 3: Design Tokens (Terminal Aesthetic)

`create-next-app --tailwind` on current Next.js versions installs **Tailwind CSS v4**, which removed `tailwind.config.js/ts` and `npx tailwindcss init` entirely — tokens now live directly in CSS via an `@theme` block. This is a real architecture change from v3, not optional to skip.

**Confirm your version first:**
```powershell
npm list tailwindcss
```
If it shows `4.x.x`, follow this task as written. (If somehow on v3, use a `tailwind.config.ts` with a `theme.extend` object instead — ask if you land there and need the v3 version.)

### Step 3.1: Correct PostCSS config for v4

**Run in PowerShell:**
```powershell
npm uninstall autoprefixer
npm install -D @tailwindcss/postcss
notepad postcss.config.mjs
```
**Paste (full replacement):**
```javascript
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
```
Save, close.

### Step 3.2: Design tokens via `@theme` in `globals.css`

**Run in PowerShell:**
```powershell
notepad src\app\globals.css
```
**Paste (full replacement — note the font `@import` comes FIRST, before `@import "tailwindcss"`):**
```css
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500&display=swap');
@import "tailwindcss";

@theme {
  --color-ink: #0D0F0E;
  --color-ink-raised: #151816;
  --color-bone: #EDEAE3;
  --color-bone-dim: #9C9A93;
  --color-acid: #B4F461;
  --color-fail: #E8604C;
  --color-warn: #F4B860;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
  --font-sans: Inter, ui-sans-serif, system-ui;
}
```
Save, close.

> **Why the font import goes first:** `@import "tailwindcss"` doesn't stay a single line — Tailwind v4 expands it into 170+ lines of real preflight/reset CSS at build time. Anything textually *after* it in your source ends up positioned after real CSS rules in the compiled output, even though it looks fine in the source file — and CSS requires every `@import` to precede all other rules. Putting the font import first sidesteps this entirely, regardless of how large Tailwind's expansion grows.

This makes `bg-ink`, `text-bone`, `font-mono`, etc. work exactly as utility classes everywhere else in this guide — only how they're defined changes, not how they're used in components.

### Task 3 Done When:
- [ ] `postcss.config.mjs` uses `@tailwindcss/postcss`
- [ ] `globals.css` defines the terminal palette via `@theme`
- [ ] No `tailwind.config.ts` needed (v4 doesn't use one)

---

## Task 4: API Client

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path src\lib
notepad src\lib\api.ts
```
**Paste:**
```typescript
export interface Project {
  id: string;
  org_id: string;
  name: string;
  github_repo_url: string | null;
  created_at: string;
}

export interface EvaluationSummary {
  id: string;
  project_id: string;
  commit_hash: string | null;
  prompt_version: string | null;
  model_name: string | null;
  test_cases_count: number;
  status: string;
  created_at: string;
  completed_at: string | null;
}

export interface EvalResultRow {
  id: string;
  metric_name: string | null;
  metric_value: number | null;
  status: string;
}

export interface EvaluationDetail extends EvaluationSummary {
  results_json: Record<string, unknown> | null;
  results: EvalResultRow[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(res.status, `${res.status} on ${path}`);
  }
  return res.json();
}

export const api = {
  listProjects: (token: string) => request<Project[]>("/api/v1/projects", token),
  listEvaluations: (token: string, projectId: string) =>
    request<EvaluationSummary[]>(`/api/v1/projects/${projectId}/evals`, token),
  getEvaluation: (token: string, evalId: string) =>
    request<EvaluationDetail>(`/api/v1/evals/${evalId}`, token),
};

export { ApiError };
```
Save, close.

> Note: the backend's `get_current_user` already accepts a Clerk Bearer token via `Authorization: Bearer ...` (built in Phase 3) — this is the first time that path actually gets exercised for real.

### Task 4 Done When:
- [ ] `api.ts` created with typed functions matching Phase 3's response shapes

---

## Task 5: Shared Components

### Step 5.1: Status pill (morphing, not swapping)

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path src\components
notepad src\components\StatusPill.tsx
```
**Paste:**
```tsx
"use client";

const STYLES: Record<string, string> = {
  pending: "bg-bone-dim/20 text-bone-dim",
  running: "bg-acid/20 text-acid animate-pulse",
  pass: "bg-acid/20 text-acid",
  fail: "bg-fail/20 text-fail",
  warning: "bg-warn/20 text-warn",
};

export function StatusPill({ status }: { status: string }) {
  const style = STYLES[status] ?? STYLES.pending;
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium uppercase tracking-wide transition-colors duration-200 ${style}`}
    >
      {status}
    </span>
  );
}
```
Save, close.

### Step 5.2: Animated number (counts up on mount)

**Run in PowerShell:**
```powershell
notepad src\components\AnimatedNumber.tsx
```
**Paste:**
```tsx
"use client";
import { useEffect, useState } from "react";

export function AnimatedNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const duration = 250;
    const start = performance.now();
    const from = display;

    function tick(now: number) {
      const progress = Math.min((now - start) / duration, 1);
      setDisplay(from + (value - from) * progress);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return <span>{display.toFixed(decimals)}</span>;
}
```
Save, close.

### Step 5.3: Skeleton row (designed, not a gray box)

**Run in PowerShell:**
```powershell
notepad src\components\SkeletonRow.tsx
```
**Paste:**
```tsx
export function SkeletonRow() {
  return (
    <div className="flex animate-pulse items-center gap-4 border-b border-ink-raised px-4 py-3">
      <div className="h-4 w-16 rounded bg-ink-raised" />
      <div className="h-4 w-32 rounded bg-ink-raised" />
      <div className="h-4 w-20 rounded bg-ink-raised" />
      <div className="h-4 flex-1 rounded bg-ink-raised" />
    </div>
  );
}
```
Save, close.

### Task 5 Done When:
- [ ] `StatusPill`, `AnimatedNumber`, `SkeletonRow` created

---

## Task 6: Projects List (`/`)

**Run in PowerShell:**
```powershell
notepad src\app\page.tsx
```
**Paste (full replacement):**
```tsx
import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { UserButton } from "@clerk/nextjs";
import { api } from "@/lib/api";

export default async function ProjectsPage() {
  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  const token = (await getToken()) ?? "";
  const projects = await api.listProjects(token);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-lg font-medium tracking-tight">AutoEvalOps</h1>
        <UserButton />
      </div>

      {projects.length === 0 ? (
        <div className="rounded border border-ink-raised px-6 py-16 text-center text-bone-dim">
          No projects registered yet. Register one via the API to see it here.
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-ink-raised">
          {projects.map((project, i) => (
            <Link
              key={project.id}
              href={`/projects/${project.id}`}
              className="flex items-center justify-between border-b border-ink-raised px-4 py-3 transition-colors duration-150 last:border-b-0 hover:bg-ink-raised"
              style={{ animationDelay: `${i * 20}ms` }}
            >
              <span className="font-medium">{project.name}</span>
              <span className="text-sm text-bone-dim">{project.github_repo_url}</span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
```
Save, close.

### Task 6 Done When:
- [ ] Projects list renders, links to eval history

---

## Task 7: Evaluation History (`/projects/[id]`)

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path "src\app\projects\[id]"
notepad "src\app\projects\[id]\page.tsx"
```
**Paste:**
```tsx
import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { StatusPill } from "@/components/StatusPill";

export default async function EvalHistoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  const token = (await getToken()) ?? "";
  const evaluations = await api.listEvaluations(token, id);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <Link href="/" className="text-sm text-bone-dim transition-colors duration-150 hover:text-bone">
        &larr; Projects
      </Link>
      <h1 className="mb-6 mt-2 text-lg font-medium tracking-tight">Evaluation History</h1>

      {evaluations.length === 0 ? (
        <div className="rounded border border-ink-raised px-6 py-16 text-center text-bone-dim">
          No evaluations yet. They appear here once a PR triggers the webhook.
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-ink-raised">
          {evaluations.map((eval_, i) => (
            <Link
              key={eval_.id}
              href={`/evals/${eval_.id}`}
              className="flex items-center gap-4 border-b border-ink-raised px-4 py-3 text-sm transition-colors duration-150 last:border-b-0 hover:bg-ink-raised"
              style={{ animationDelay: `${i * 20}ms` }}
            >
              <span className="w-20 truncate text-bone-dim">
                {eval_.commit_hash?.slice(0, 7) ?? "-"}
              </span>
              <span className="flex-1 truncate">{eval_.prompt_version ?? "-"}</span>
              <span className="text-bone-dim">{eval_.test_cases_count} cases</span>
              <StatusPill status={eval_.status} />
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
```
Save, close.

### Task 7 Done When:
- [ ] Eval history renders per project, links to detail

---

## Task 8: Evaluation Detail (`/evals/[id]`)

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path "src\app\evals\[id]"
notepad "src\app\evals\[id]\page.tsx"
```
**Paste:**
```tsx
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { StatusPill } from "@/components/StatusPill";
import { AnimatedNumber } from "@/components/AnimatedNumber";

export default async function EvalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  const token = (await getToken()) ?? "";
  const evaluation = await api.getEvaluation(token, id);

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium tracking-tight">{evaluation.prompt_version}</h1>
          <p className="text-sm text-bone-dim">
            {evaluation.commit_hash?.slice(0, 7)} &middot; {evaluation.model_name}
          </p>
        </div>
        <StatusPill status={evaluation.status} />
      </div>

      <div className="overflow-hidden rounded border border-ink-raised">
        {evaluation.results.map((result, i) => (
          <div
            key={result.id}
            className="flex items-center justify-between border-b border-ink-raised px-4 py-3 text-sm last:border-b-0"
            style={{ animationDelay: `${i * 30}ms` }}
          >
            <span className="capitalize">{result.metric_name}</span>
            <div className="flex items-center gap-3">
              <span className="tabular-nums text-bone-dim">
                <AnimatedNumber value={result.metric_value ?? 0} decimals={2} />
              </span>
              <StatusPill status={result.status} />
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
```
Save, close.

### Task 8 Done When:
- [ ] Eval detail renders per-metric results with animated values

---

## Task 9: Backend Configuration for Clerk

Three real, sequential issues surfaced only once a genuine Clerk login hit the backend for the first time — none of these were visible from unit tests, since Phase 3's Clerk tests only ever used mocked JWKS. Fixing them in this order avoids the multi-hour debugging chain that produced this task.

### Step 9.1: Fix TLS certificate verification (Windows + antivirus HTTPS interception)

If your machine runs Avast, AVG, or similar antivirus with HTTPS scanning enabled, it intercepts TLS traffic using its own locally-generated root certificate — one that Python's bundled `certifi` CA list doesn't trust, even though Windows itself does. This breaks **every** outbound HTTPS call from the venv, not just Clerk's — including `pip install` and JWKS fetches. Symptom: `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` on any HTTPS request.

**Run in PowerShell (from `backend/`):**
```powershell
notepad requirements.txt
```
Add, save, close:
```text
truststore
```
```powershell
pip install -r requirements.txt
```

**Add the injection as early as possible in `server.py`** — before any other imports:
```powershell
notepad src\autoeval_ops\server.py
```
Add these two lines as the very first lines of the file, above every other import:
```python
import truststore
truststore.inject_into_ssl()
```
Save, close. This makes Python's `ssl` module read from Windows' own certificate store (CryptoAPI) instead of `certifi`'s bundled list — Windows already trusts the antivirus's interception certificate, so this fixes it with no security tradeoff and no antivirus configuration changes needed. It also means this fix travels with the repo for anyone else who clones it, rather than being a one-off local exclusion.

**Verify:**
```powershell
python -c "import truststore; truststore.inject_into_ssl(); import urllib.request; print(urllib.request.urlopen('https://pypi.org').status)"
```
Should print `200`.

### Step 9.2: Add an email claim to Clerk's session token

By default, Clerk's session token does **not** include an email address — its claims are limited to session/security metadata (`azp`, `exp`, `sub`, etc.). `deps.py`'s `_user_from_clerk_token` looks for `claims.get("email")`, so without this step every real login fails auth with no email to look up.

1. Go to https://dashboard.clerk.com, select your app
2. **Configure → Sessions → Customize session token**
3. In the Claims editor, add:
   ```json
   {
     "email": "{{user.primary_email_address}}"
   }
   ```
4. Save
5. **This does not apply retroactively** — any browser tab already signed in is holding an old token without the claim. Sign out and back in (or use a fresh Incognito window) to force a new token after this change.

### Step 9.3: Just-in-time user provisioning

A Clerk login and a backend `users` row are two separate things — signing into Clerk does **not** automatically create a row in your `users` table. Phase 3's Task 15 walkthrough created a user via `POST /api/v1/users` with the API-key flow, but a real Clerk login uses a *different* email in the general case, and there's no row for it. Without provisioning, every genuinely new Clerk user 401s permanently, which defeats the purpose of self-service signup.

**Run in PowerShell (from `backend/`):**
```powershell
notepad src\autoeval_ops\db\repository.py
```
Add this function (anywhere among the other `User`-related functions):
```python
async def get_or_create_user_by_email(db: AsyncSession, email: str) -> User:
    """Used by Clerk JIT provisioning: a verified Clerk login with no
    existing backend user gets one created on first sight, rather than
    permanently 401ing. Clerk-provisioned users have no API key."""
    user = await get_user_by_email(db, email)
    if user:
        return user
    user = User(email=email, api_key_hash=None)
    db.add(user)
    await db.flush()
    return user
```
Save, close.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\deps.py
```
Find, inside `_user_from_clerk_token`:
```python
    return await repository.get_user_by_email(db, email)
```
Replace with:
```python
    return await repository.get_or_create_user_by_email(db, email)
```
Save, close.

> Note: `create_user`'s `api_key_hash` parameter must accept `None` for this to work — confirm `models.py`'s `User.api_key_hash` is already nullable (it is, from Phase 3: `Mapped[str | None]`).

### Step 9.4: Confirm CORS is still correct

`server.py` already has CORS middleware from Phase 3, pointed at `http://localhost:3000` — confirm it's still correct now that a real Next.js app exists there.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\server.py
```
Confirm this line matches (it should already, from Phase 3):
```python
    allow_origins=["http://localhost:3000"],
```
No change needed unless it's different — just verifying.

### Task 9 Done When:
- [ ] `truststore` installed and injected at the top of `server.py`
- [ ] Clerk session token includes an `email` claim
- [ ] `get_or_create_user_by_email` added, `deps.py` uses it for the Clerk auth path
- [ ] CORS origin confirmed correct

---

## Task 10: Run and Verify

### Step 10.1: Start the backend

**Run in PowerShell (from `backend/`, venv active):**
```powershell
docker-compose up -d
python -m uvicorn autoeval_ops.server:app --reload --port 8001
```
> Using `python -m uvicorn` rather than bare `uvicorn` avoids ambiguity about which Python/venv is actually running it. Port `8001` rather than `8000` sidesteps a known Windows issue where a stale/orphaned kernel-level socket entry can hold `8000` in a `LISTEN` state indefinitely even after the owning process is confirmed dead — if `8000` works fine for you, it's safe to use instead; just keep Step 10.2's `NEXT_PUBLIC_API_URL` consistent with whichever port you actually use.

### Step 10.2: Start the dashboard

**Run in PowerShell (new tab, from `dashboard/`):**
```powershell
npm run dev
```
Confirm `dashboard/.env.local`'s `NEXT_PUBLIC_API_URL` matches the port used in Step 10.1 (`http://localhost:8001` if you used 8001).

### Step 10.3: Walk through it

1. Open http://localhost:3000
2. Should redirect to `/sign-in` (Clerk) — sign up with a real email
3. After signing in, should land on the projects page. **If this is a brand-new Clerk login with no backend history, expect "No projects registered yet"** — that's correct, not a bug; Step 9.3's JIT provisioning creates the user but not any projects/orgs for them. Register a project via the API (same flow as Phase 3's Task 15) under this exact email to see real data.
4. Click into a project → eval history → eval detail
5. Confirm any evaluation from Phase 3's Task 16 shows up with its real metric values

**If you get a 401 specifically, don't guess — check the actual backend log**, since the failure could be several different things (JWKS/TLS, missing email claim, or no matching user) and each looks identical from the browser alone:
```powershell
Get-Content $env:TEMP\uvicorn8001.out.log -Tail 30
```
(Or watch the terminal directly if not redirecting output to a file.) See the Troubleshooting Log below for what each specific failure looks like.

### Task 10 Done When:
- [ ] Full login → projects → history → detail flow works with real data
- [ ] Clerk's live JWT verification confirmed working end-to-end for the first time
- [ ] A brand-new Clerk login is auto-provisioned rather than permanently 401ing

---

## Task 11: Final Commit

**Run in PowerShell (from the repo root):**
```powershell
notepad .gitignore
```
Add, save, close:
```text
dashboard/node_modules/
dashboard/.next/
dashboard/.env.local
```

**Run in PowerShell:**
```powershell
git add -A
git commit -m "[PHASE 4] Frontend dashboard: Next.js + Clerk, terminal aesthetic

- Clerk auth wired end-to-end, live JWT verification confirmed for the first time
- Projects list, eval history, eval detail pages against the real Phase 3 API
- Terminal/CI design system: near-black base, acid accent, monospace data
- Functional motion: animated counters, staggered rows, morphing status pills
- Breaking changes: NO"
git push origin main
```

### Final Checklist:
- [ ] Clerk live login works
- [ ] All three pages render real backend data
- [ ] Design matches terminal aesthetic direction
- [ ] Committed and pushed

---

## Next Step

Write `PHASE_4_STATUS.md` (same audit pattern), then Phase 5: Observability.

## Troubleshooting Log (Phase 4)

| Symptom | Cause | Fix |
|---|---|---|
| `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` on any outbound HTTPS call from the backend (JWKS fetch, `pip install`, etc.) | Antivirus (commonly Avast/AVG) intercepting HTTPS with its own root certificate, which Windows trusts but Python's bundled `certifi` list does not | Install `truststore`, inject it at the very top of `server.py` before any other imports (Task 9, Step 9.1) — makes Python trust the same store Windows does |
| 401 on every API request even though the token verifies successfully and looks valid | Clerk's default session token has no `email` claim — `deps.py` finds nothing to look up | Add a custom `email` claim in Clerk Dashboard → Configure → Sessions (Task 9, Step 9.2). **Must sign out and back in** afterward — existing tokens don't retroactively gain the claim |
| Signing out via DevTools cookie-clearing doesn't actually force a new session; still 401s afterward | Clerk's session cookie may live on Clerk's own domain rather than `localhost:3000`, so clearing only the app's cookies misses it | Use a fresh Incognito/Private window instead of fighting DevTools cookie state — guarantees zero prior cookies of any kind |
| 401 even with a verified token containing a real `email` claim | The Clerk login's email has no matching row in the backend `users` table — a Clerk login never auto-creates one | Add JIT provisioning: `get_or_create_user_by_email` in `repository.py`, used by `deps.py`'s Clerk auth path instead of a lookup-only function (Task 9, Step 9.3) |
| `netstat` shows port 8000 as `LISTEN` for a PID that `Get-Process`/`taskkill` can't find, even after killing the real process and waiting | A stale/orphaned kernel-level socket entry on Windows — the owning process is genuinely dead, but the OS hasn't released the port | Use a different port (e.g. `8001`) rather than fighting the OS — update `NEXT_PUBLIC_API_URL` in `dashboard/.env.local` to match |
| Debug `print()`/logging statements added to diagnose a backend issue never appear in the log file being checked | `uvicorn` splits its output: `uvicorn.error`/startup messages go to **stderr**, but the per-request access log and any `print()`/`stdout` logging go to **stdout** | Check the correct stream — if redirecting output to files, check the `.out.log` (stdout) file specifically, not just `.err.log` (stderr) |
| `notepad src\proxy.ts` fails with "path cannot be found" | Target folder didn't exist at that moment, or a stale/partial file was left from a prior attempt | Verify the parent folder exists (`Test-Path src`), retry `notepad`, and if prompted "already exists, replace?" click Yes to ensure the correct content saves |
| `create-next-app` scaffolds `pages/` instead of `src/app/` even with `--app` passed | Leftover empty `dashboard/pages/`/`dashboard/components/` folders from Phase 0's original roadmap sketch signal Next.js to use the older Pages Router | Delete those folders (Task 1, Step 1.1) *before* running `create-next-app` |
| `npx tailwindcss init -p` fails with "could not determine executable to run"; `npm install` warns about moving `tailwindcss` to devDependencies | `create-next-app --tailwind` installed **Tailwind v4**, which removed the `init` command and `tailwind.config.js/ts` entirely | Use v4's `@theme` block in `globals.css` instead (Task 3) — no config file needed |
| `Attempted import error: 'createRouteMatcher'/'clerkMiddleware' is not exported from '@clerk/nextjs/server'` | `create-next-app` scaffolded onto Next.js 14, but `@clerk/nextjs` v5+ (which exports these) requires Next 15+ as a peer dependency | Upgrade first: `npm install next@latest react@latest react-dom@latest`, then `npm install @clerk/nextjs@latest` (Task 1, Steps 1.2-1.3) |
| `npm install @clerk/nextjs@latest` fails with `ERESOLVE ... peer next@"^15..."` | Same root cause as above — Next.js wasn't upgraded first | Upgrade Next.js to 15+ before installing Clerk, not after; do not use `--force`/`--legacy-peer-deps` to paper over it |
| `Error: auth(...).protect is not a function` in `middleware.ts`, alongside warnings that both the "middleware" file convention and `createRouteMatcher` are deprecated | `@clerk/nextjs@latest` (v7+) removed the old `.protect()` API from the middleware callback entirely, and Next.js 16 renamed `middleware` to `proxy` | Rename to `proxy.ts`, and drop `createRouteMatcher`/`.protect()` — Clerk's current guidance moves that logic into each page instead |
| `Clerk: auth() was called but Clerk can't detect usage of clerkMiddleware()` when a page calls `await auth()` | Deleting the middleware/proxy file entirely (to fix the `.protect()` error above) removes more than intended — `clerkMiddleware()` itself is still required to establish the auth context every page-level `auth()` call depends on; only the route-matching/`.protect()` part is deprecated | Create `proxy.ts` with a bare `clerkMiddleware()` call, no `createRouteMatcher`, no `.protect()` (Task 2, already included above). Auth checks stay in each page via `const { userId } = await auth(); if (!userId) redirect("/sign-in");` |
| Projects page 401s or errors on load | Clerk token isn't validating against `CLERK_JWKS_URL` | Confirm `.env`'s `CLERK_JWKS_URL` matches your Clerk app's actual Frontend API + `/.well-known/jwks.json`, and that `server.py` was restarted after filling it in |
| `@import rules must precede all rules aside from @charset and @layer statements`, pointing at a line number (e.g. `180:8`) that doesn't exist in your actual `globals.css` source | The error is in the **generated** CSS, not your source — `@import "tailwindcss"` expands into 170+ lines of real preflight/reset rules at build time. Anything textually *after* that import in your source ends up positioned after real CSS rules in the compiled output, even though the source file itself looks completely valid. Confirmed by checking `dashboard/.next/dev/logs/next-development.log`, which explicitly says "Generated code of PostCSS transform" | Put the font (or any other) `@import` **before** `@import "tailwindcss"` in `globals.css` (already fixed in Task 3, Step 3.2 above). If this error persists after fixing the order, verify with `Get-Content src\app\globals.css` that the fix actually saved, kill any lingering `node` processes, and delete `.next` before restarting — but check the import order first, since that's very likely the real cause regardless of how stale-cache-like the symptom looks |
| CORS error in browser console | Dashboard origin doesn't match `server.py`'s `allow_origins` | Confirm dashboard runs on `localhost:3000` (Next.js default) and matches Task 9's setting exactly |
| `Module not found: Can't resolve '@/lib/api'` (or any `@/components/...` import) despite the file existing | Task 4/5 got skipped over while working through an earlier task in a different order, or mid-troubleshooting | `Test-Path src\lib\api.ts` etc. to confirm; if genuinely missing, go back and complete Tasks 4-5 before returning to whichever later task raised the error |
