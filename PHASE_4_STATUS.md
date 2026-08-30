# Phase 4 Complete — 2026-08-28

Task 10's remaining gap — the eval detail page's happy path with real data — is now closed by direct visual confirmation, not inference. Committed to `main` (`0bfb02f`), working tree clean, local `main` == `origin/main`.

---

## What Was Built

**Clerk authentication** (`dashboard/proxy.ts`, `dashboard/app/layout.tsx`, sign-in/sign-up routes): session handling via a bare `clerkMiddleware()` in `proxy.ts` (Next.js 16's rename of `middleware.ts`), with `<ClerkProvider>` wrapping the app in `layout.tsx` and per-page `redirect()` checks doing the actual auth gating.

**Terminal-aesthetic design system** (Task 3's `@theme` tokens): near-black background, acid accent, monospace data rendering — a deliberate departure from a generic SaaS look, applied consistently across every page.

**Typed API client**: wraps every call into the Phase 3 FastAPI backend, sharing request/response shapes with the backend's Pydantic schemas.

**Three shared components**: `StatusPill` (PASS/FAIL/WARN with morphing color states), `AnimatedNumber` (counting transitions for metric values), `SkeletonRow` (loading-state placeholder for list/table rows).

**Three pages**: projects list, eval history, and eval detail — all confirmed working end-to-end against the real, running Phase 3 API (not mocked).

**Test coverage**: no dedicated frontend automated test suite was added this phase — verification was direct, logged-in, end-to-end browser confirmation against real backend data (see Task 10 section below), consistent with this phase's scope being UI/integration rather than unit-testable business logic.

---

## Scope Decisions Confirmed for This Phase

- **Claude Design was considered for the visual language, but the actual build stayed in Next.js.** The auth flow (Clerk) and live data requirements (typed calls into the Phase 3 API) needed a real app framework, not a static/visual-first tool.
- **Terminal/CI aesthetic chosen deliberately over a generic SaaS look.** Near-black background, acid accent color, monospace for data — matches the identity of a tool that reports on CI/eval runs rather than a marketing product.
- **Functional motion over decorative animation.** Counters (`AnimatedNumber`), staggered row entry, and morphing `StatusPill` states were chosen because this is a logged-in data tool, not a marketing page — motion communicates state changes, not decoration.

---

## Real Debugging Chain From This Phase

1. **Next.js version mismatch.** `create-next-app` scaffolded onto Next 14, but `@clerk/nextjs` v5+ requires Next 15+. Fixed by upgrading Next first (landed on 16.3.3), then adding Clerk.

2. **Next.js 16 renamed `middleware` to `proxy`; Clerk simultaneously deprecated route-matching-based `auth().protect()`.** Resolved with `proxy.ts` using a bare `clerkMiddleware()` (still required to establish auth context) plus per-page `redirect()` calls for the actual auth checks. An intermediate wrong turn — removing middleware entirely — was corrected once "Clerk: `auth()` was called but can't detect `clerkMiddleware()`" surfaced.

3. **Tailwind v4's `@import "tailwindcss"` expands into 170+ lines of real CSS at build time**, so anything after it in source ends up positioned after real rules in the compiled output. The build error pointed at a line number that never existed in the actual source file — genuinely confusing until `dashboard/.next/dev/logs/next-development.log` was checked directly. Fixed by ordering the font `@import` before `@import "tailwindcss"`.

4. **TLS interception from Avast's local HTTPS scanning proxy.** Avast injects its own root certificate, trusted by Windows but not by Python's bundled `certifi` list, breaking every outbound HTTPS call from the backend (JWKS fetches included). Fixed with the `truststore` package, injected at the very top of `server.py`, before any other import.

5. **Clerk's default session token has no `email` claim.** `deps.py`'s Clerk auth path looks for `claims.get("email")` and found nothing, producing a 401 indistinguishable from several other possible failure modes. Fixed via a custom claim in Clerk Dashboard → Configure → Sessions → Customize session token. Required signing out and back in afterward, since existing tokens don't retroactively gain claims.

6. **A verified Clerk login with a valid email claim still 401'd**, because a Clerk login never automatically creates a backend `users` row — only the Phase 3 API-key registration flow did that. Fixed with `get_or_create_user_by_email` in `repository.py`, used by `deps.py`'s Clerk auth path for JIT provisioning instead of a lookup-only function.

7. **`get_project_by_repo()` had no uniqueness guarantee on `github_repo_url`.** Two `projects` rows both pointed at `basilbe/autoeval-ops` — the original Phase 3 project and a new one created under the Clerk user for this test — and the lookup silently resolved to whichever row existed first, causing evaluations to land under the wrong project. Fixed by renaming the legacy Phase 3 project's `github_repo_url` to `basilbe/autoeval-ops-phase3-legacy` (a data change, not a code change — no migration needed). Flagged as worth a real uniqueness constraint or better resolution logic in a future phase, not fully solved architecturally here.

---

## Tooling Note

**PowerShell gotcha, independent of the app itself**: `Test-Path` without `-LiteralPath` misinterprets `[id]` (Next.js's dynamic-route folder syntax) as a wildcard character class, producing false negatives even when the path is real. Cost real time mid-session before being caught.

---

## Task 10: Full Flow Confirmed End-to-End With Real Data

Login → projects → history → detail was directly observed, not inferred. The eval detail page at `/evals/776d6899-1fe7-4fde-90ac-6a6d5c284a73` — the one gap still open as of the initial audit — is now confirmed closed: it correctly rendered real data under a project owned by the Clerk user (`AutoEvalOps Real`, `basilbe/autoeval-ops`) — commit `7070005`, model `gpt-4`, all 5 metrics with correct values and `StatusPill`s:

- Correctness — 50.00 — FAIL
- Toxicity — 0.00 — PASS
- Hallucination — 0.00 — FAIL
- Cost — 0.00 — PASS
- Latency — 0.00 — PASS

All values consistent with the `EchoLLMClient`/`NullToxicityScorer` placeholder behavior seen throughout this project whenever a real `OPENAI_API_KEY` isn't set — not a new anomaly.

---

## Follow-Up (Not Auto-Applied)

`TECH_STACK.md` should get a small addendum for the `truststore` dependency — a real, necessary addition discovered this phase, same category as Phase 1's PyJWT addition. Flagged here as a follow-up; not edited automatically without the user's go-ahead.

---

## Next Step: Phase 5 — Observability

See `Roadmap.md` for the full task breakdown.

Per `CLAUDE.md`'s golden rule: do not begin Phase 5 until this status doc is reviewed and Phase 4 is reconfirmed complete in that session.
