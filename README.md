\# AutoEvalOps



Automated LLM prompt evaluation on every pull request. Change a prompt,

open a PR, get correctness/toxicity/hallucination/cost/latency scores

posted as a comment before you merge.



\*\*Live:\*\* https://autoeval-ops.vercel.app

\*\*Status:\*\* https://autoeval-ops.vercel.app/status (public, no login)



\---



\## How it works



```

PR opened/updated on a repo with the GitHub App installed

&#x20;       │

&#x20;       ▼

GitHub sends a webhook  ──►  HMAC signature verified

&#x20;       │

&#x20;       ▼

Job enqueued on an in-process asyncio queue (no broker to operate)

&#x20;       │

&#x20;       ▼

Orchestrator finds every changed prompts/\*.txt file and its matching

eval/\*.test\_cases.json

&#x20;       │

&#x20;       ▼

Each test case is run through the real model, then scored by five

evaluators in parallel: correctness (LLM-as-judge), toxicity,

hallucination (lexical grounding), cost, latency

&#x20;       │

&#x20;       ├──►  Results posted as a PR comment (Markdown table)

&#x20;       │

&#x20;       ├──►  Persisted to Postgres (evaluations, eval\_results, traces)

&#x20;       │       — this succeeds or fails independently of the PR

&#x20;       │         comment; a database outage never blocks feedback

&#x20;       │         on the PR

&#x20;       │

&#x20;       └──►  Traced with OpenTelemetry — one span per evaluator,

&#x20;               visible end-to-end in Jaeger locally

```



Everything downstream — the dashboard, the public status page — reads

from the same Postgres rows the webhook wrote. There's no separate

"demo mode": what you see in the dashboard is exactly what the pipeline

actually computed.



\## Try it on your own repo



1\. \*\*Install the GitHub App\*\* on your repo — \[link to your App's public

&#x20;  install page]

2\. \*\*Sign in\*\* at the \[live dashboard](https://autoeval-ops.vercel.app)

&#x20;  and use \*\*Add a Project\*\*, pointing it at `owner/repo`

3\. \*\*Add prompt files\*\* to your repo:

&#x20;  - `prompts/summarize.txt` — the prompt itself, with a `{text}`

&#x20;    placeholder for the input

&#x20;  - `eval/summarize.test\_cases.json` — a matching file with test

&#x20;    inputs and expected outputs

4\. \*\*Open a PR\*\* that touches a prompt file. A comment appears with

&#x20;  scores before you merge, and the run shows up in the dashboard.



\## Architecture



FastAPI backend (async throughout), Next.js dashboard, Postgres for

everything — evaluations, users, traces. Full write-up, including the

six phases this was built in and the real trade-offs made along the

way, is in \[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and

\[`docs/POSTMORTEM.md`](docs/POSTMORTEM.md).



A few decisions worth calling out here:



\- \*\*`asyncio.Queue`, not Celery.\*\* One backend instance, no message

&#x20; broker to run or pay for. Revisit if this ever needs to scale

&#x20; horizontally.

\- \*\*Postgres for traces, not a dedicated time-series store.\*\* The

&#x20; `traces` table sat unused for four phases before Phase 5 finally

&#x20; wrote to it — a second database before the first one saw real use

&#x20; would have been pure overhead.

\- \*\*Google Gemini by default, OpenAI supported.\*\* Both implement the

&#x20; same `LLMClient` protocol; the app doesn't know or care which one is

&#x20; configured. Gemini's free tier fits a project that's evaluated

&#x20; occasionally, not run at production volume.



\## Tech stack



\*\*Backend:\*\* FastAPI · SQLAlchemy (async) + Alembic · PostgreSQL ·

`asyncio`-based evaluation queue · OpenTelemetry (OTLP → Jaeger) ·

`slowapi` rate limiting · `bcrypt` for API keys



\*\*Frontend:\*\* Next.js (App Router) · Clerk auth · Tailwind CSS v4



\*\*Integrations:\*\* GitHub App (JWT-authenticated) · Google Gemini API /

OpenAI API (pluggable) · Clerk JWT verification



\*\*Infrastructure:\*\* Docker Compose (local) · Render (backend + managed

Postgres) · Vercel (dashboard) · GitHub Actions (CI)



\*\*Testing:\*\* pytest + `pytest-asyncio`, 149+ tests, \~98% coverage,

unit and Postgres-backed integration suites



Full list with reasoning for each addition:

\[`docs/TECH\_STACK.md`](docs/TECH\_STACK.md).



\## Running locally



\*\*Backend:\*\*

```bash

docker-compose up -d

cd backend

python -m venv .venv

.venv\\Scripts\\Activate.ps1          # Windows

pip install -r requirements.txt

pip install -e .

alembic upgrade head

python -m uvicorn autoeval\_ops.server:app --reload --port 8001

```



\*\*Dashboard\*\* (separate terminal):

```bash

cd dashboard

npm install

npm run dev

```



You'll need your own `.env` (copy `.env.example`) with a GitHub App,

a Clerk application, and a `GOOGLE\_API\_KEY` — see

\[`docs/TECH\_STACK.md`](docs/TECH\_STACK.md) for what each is for.



\## Status \& Observability



`/api/v1/status` (and the `/status` dashboard page) is the one

deliberately unauthenticated route in the whole API — real aggregate

numbers, no login required, no project or user data exposed. Locally,

every evaluation is traced end-to-end and viewable in Jaeger at

`localhost:16686`.



\## License



\[MIT / whatever you choose]

