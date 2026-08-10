# Phase 0: Setup & Architecture (PowerShell Edition v3)

> Every code block below is labeled with **where it goes**: either "Run in PowerShell" (type/paste into your terminal) or "Paste into `filename`" (opens in Notepad, you paste the content, save, close).

---

## Prerequisites (Check Before Starting)

### Docker Desktop must be installed AND running

**Run in PowerShell:**
```powershell
Get-Command docker -ErrorAction SilentlyContinue
```
If this returns nothing, install Docker Desktop from https://www.docker.com/products/docker-desktop/, restart your machine, launch Docker Desktop from the Start menu, and wait for the whale icon in your system tray to show "running."

**Run in PowerShell:**
```powershell
docker-compose --version
```
If this errors but `docker --version` works, use `docker compose` (space instead of hyphen) everywhere in this guide instead.

---

## Task 1: Create GitHub Repository

### Step 1.1: Initialize Local Repository

**Run in PowerShell:**
```powershell
mkdir autoeval-ops
cd autoeval-ops

git init
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

### Step 1.2: Create Directory Structure

**Run in PowerShell:**
```powershell
New-Item -ItemType Directory -Force -Path backend/core, backend/github, backend/api, backend/observability, backend/tests, backend/db, backend/src/autoeval_ops

New-Item -ItemType Directory -Force -Path dashboard/pages, dashboard/components, dashboard/public

New-Item -ItemType Directory -Force -Path docs

New-Item -ItemType File -Force -Path .env.example, .gitignore, README.md
```

### Step 1.3: VERIFY all directories were actually created
**Do not skip this — a missing folder here will cause errors several tasks later.**

**Run in PowerShell:**
```powershell
Test-Path backend/core, backend/github, backend/api, backend/observability, backend/tests, backend/db, backend/src/autoeval_ops, dashboard/pages, dashboard/components, dashboard/public, docs
```
Every line must say `True`. If any say `False`:

**Run in PowerShell (repeat for each missing path):**
```powershell
New-Item -ItemType Directory -Force -Path <the-missing-path>
```

### Step 1.4: Create GitHub Repository (in browser, not PowerShell)
1. Go to https://github.com/new
2. Repository name: `autoeval-ops`
3. Description: "Automated evaluation sandbox for LLM prompts"
4. Public (for portfolio)
5. Do NOT initialize with README/LICENSE
6. Click "Create repository"

### Step 1.5: Connect Local to GitHub

**Run in PowerShell:**
```powershell
# Replace YOUR_USERNAME with your GitHub username
git remote add origin https://github.com/YOUR_USERNAME/autoeval-ops.git
git branch -M main
git add .
git commit -m "[PHASE 0] Initial project structure"
git push -u origin main
```

### Task 1 Done When:
- [ ] Repository exists on GitHub
- [ ] `Test-Path` returned `True` for every directory
- [ ] Local git is connected to remote

---

## Task 2: Create `.env.example` and `.env` Files

### Step 2.1: Open the file

**Run in PowerShell:**
```powershell
notepad .env.example
```

**Paste into `.env.example`:**
```ini
DATABASE_URL=postgresql://user:password@localhost:5432/autoeval_dev
POSTGRES_USER=autoeval_user
POSTGRES_PASSWORD=dev_password
POSTGRES_DB=autoeval_dev
REDIS_URL=redis://localhost:6379
GITHUB_APP_ID=
GITHUB_PRIVATE_KEY=
GITHUB_WEBHOOK_SECRET=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
CLERK_SECRET_KEY=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```
Save, close Notepad.

### Step 2.2: Create local `.env` (not committed to git)

**Run in PowerShell:**
```powershell
Copy-Item .env.example .env
notepad .env
```
In Notepad, fill in real dev values for `POSTGRES_PASSWORD` etc. (even a simple placeholder like `dev_password123` is fine locally). Save, close.

### Step 2.3: Create `.gitignore`

**Run in PowerShell:**
```powershell
notepad .gitignore
```

**Paste into `.gitignore`:**
```text
.env
.env.local
__pycache__/
.pytest_cache/
node_modules/
.DS_Store
```
Save, close.

### Step 2.4: Verify both files are clean (no stray text)

**Run in PowerShell:**
```powershell
Get-Content .env
Get-Content .env.example
```
You should see only plain `KEY=value` lines. If you see anything starting with `@'` or ending with `'@`, delete those lines — they're leftover here-string syntax, not valid `.env` content.

### Task 2 Done When:
- [ ] `.env.example` exists and is clean
- [ ] `.env` exists locally, filled in, and is clean
- [ ] `.gitignore` prevents `.env` from being committed

---

## Task 3: Create Docker Compose File

### Step 3.1: Open the file

**Run in PowerShell:**
```powershell
notepad docker-compose.yml
```

**Paste into `docker-compose.yml`:**
```yaml
services:
  postgres:
    image: postgres:15-alpine
    container_name: autoeval_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: autoeval_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgvector:
    image: ankane/pgvector:latest
    container_name: autoeval_pgvector
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}_vectors
    ports:
      - "5433:5432"
    volumes:
      - pgvector_data:/var/lib/postgresql/data

volumes:
  postgres_data:
  redis_data:
  pgvector_data:
```
Save, close.

> Note: the `version:` field is intentionally omitted — it's obsolete in current Docker Compose and only produces a harmless warning.

> Note: `pgvector` is a **separate container on port 5433**, not an extension inside `autoeval_postgres`. Don't try to `CREATE EXTENSION vector` inside `autoeval_postgres` — it will fail (see Task 4).

### Step 3.2: Start services

**Run in PowerShell:**
```powershell
docker-compose up -d
docker-compose ps
```
All 3 services (`autoeval_postgres`, `autoeval_redis`, `autoeval_pgvector`) should show `Up` (give it 10-15 seconds for healthchecks to pass).

### Task 3 Done When:
- [ ] `docker-compose.yml` created
- [ ] `docker-compose up -d` starts all 3 services
- [ ] `docker-compose ps` shows all as `Up`

---

## Task 4: Create Database Schema

**Only the core relational tables — no `pgvector`/`embeddings` here.** The `autoeval_postgres` container doesn't have the `vector` extension installed, so a `CREATE EXTENSION vector` statement will fail. Embeddings are deferred to a later phase, and if/when needed will be created inside the separate `autoeval_pgvector` container (port 5433) instead.

### Step 4.1: Open the file

**Run in PowerShell:**
```powershell
notepad backend/db/schema.sql
```

**Paste into `backend/db/schema.sql`:**
```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    api_key VARCHAR(255) UNIQUE,
    api_key_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Organizations table
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    github_repo_url VARCHAR(255),
    github_token_encrypted TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Evaluations table
CREATE TABLE evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    commit_hash VARCHAR(40),
    prompt_version VARCHAR(255),
    model_name VARCHAR(100),
    test_cases_count INT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    results_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Evaluation Results table
CREATE TABLE eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    metric_name VARCHAR(100),
    metric_value FLOAT,
    status VARCHAR(50) DEFAULT 'pass',
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Traces table
CREATE TABLE traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID REFERENCES evaluations(id) ON DELETE CASCADE,
    trace_data JSONB,
    latency_ms INT,
    cost_usd FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_organizations_user_id ON organizations(user_id);
CREATE INDEX idx_projects_org_id ON projects(org_id);
CREATE INDEX idx_evaluations_project_id ON evaluations(project_id);
CREATE INDEX idx_evaluations_created_at ON evaluations(created_at);
CREATE INDEX idx_eval_results_eval_id ON eval_results(eval_id);
CREATE INDEX idx_traces_eval_id ON traces(eval_id);
```
Save, close.

### Step 4.2: Load schema into Postgres

**Run in PowerShell:**
```powershell
Get-Content backend/db/schema.sql | docker exec -i autoeval_postgres psql -U autoeval_user -d autoeval_dev
```
Expect to see `CREATE TABLE` x6 and `CREATE INDEX` x7, no errors.

### Step 4.3: Verify tables

**Run in PowerShell:**
```powershell
docker exec -it autoeval_postgres psql -U autoeval_user -d autoeval_dev -c "\dt"
```
Should list exactly 6 tables: `users`, `organizations`, `projects`, `evaluations`, `eval_results`, `traces`.

### Task 4 Done When:
- [ ] `backend/db/schema.sql` exists (core tables only, no vector/embeddings)
- [ ] 6 tables created in postgres with no errors
- [ ] Indexes created successfully
- [ ] `\dt` confirms all 6 tables

---

## Task 5: Create Architecture Documentation

### Step 5.1: Open the file

**Run in PowerShell:**
```powershell
notepad docs/ARCHITECTURE.md
```

**Paste into `docs/ARCHITECTURE.md`:**
```markdown
# AutoEvalOps Architecture

## System Overview
GitHub PR -> Webhook Receiver -> Task Queue -> Eval Engine -> Database -> PR Comment
                                                    |
                                              OpenTelemetry -> Traces
                                                    |
                                              Dashboard Display

## Components

### 1. Webhook Receiver (Phase 2)
- FastAPI endpoint: POST /github/webhook
- Verifies GitHub webhook signature
- Parses PR/push events
- Enqueues evaluation tasks

### 2. Async Evaluation Engine (Phase 1)
- Runs all evaluators in parallel
- Evaluators: Correctness, Toxicity, Hallucination, Cost, Latency
- Uses asyncio for concurrency
- Stores results in PostgreSQL

### 3. Task Queue (Phase 2-3)
- Redis + Celery (or asyncio.Queue for MVP)
- Max concurrency: 10 parallel evals
- Timeout per eval: 5 minutes
- Retry failed tasks: 2 times

### 4. Backend API (Phase 3)
- FastAPI application
- RESTful endpoints for projects, evals, results
- Authentication via Clerk
- Rate limiting: 100 req/min per API key

### 5. Frontend Dashboard (Phase 4)
- Next.js React app
- Pages: Projects, Eval History, Results Detail
- Real-time updates via polling (or WebSocket Phase 6)
- Connected to Backend API

### 6. Observability (Phase 5)
- OpenTelemetry instrumentation
- Traces emitted to Jaeger (local) / Datadog (prod)
- Metrics: latency, cost, error rate
- Public status page: /status

## Database Schema

### users
id, email, api_key_hash, created_at

### projects
id, org_id (FK), name, github_repo_url, github_token_encrypted

### evaluations
id, project_id (FK), commit_hash, prompt_version, results_json (JSONB), status, created_at

### eval_results
id, eval_id (FK), metric_name, metric_value, status

## Concurrency Model
- All I/O operations use async/await
- Evaluation engine uses asyncio.gather() to run evaluators in parallel
- Max 10 concurrent evals per process

## Rate Limiting
- API: 100 requests per minute per user
- Evaluations: 10 parallel evals max
- GitHub API: Respect GitHub rate limit (60 req/min unauthenticated)

## Error Handling
- Eval timeout > 5 min: mark as failed
- LLM API error: retry 2 times, then fail
- Database error: log and alert
- Invalid webhook signature: reject (400)
- Repo not found: PR comment "Error: repo not found"

## Security
- GitHub tokens encrypted with AES-256-GCM
- API keys hashed with bcrypt
- Database connection over TLS
- SQL injection prevention: SQLAlchemy ORM parameterized queries
- CORS: Only allow requests from dashboard domain

## Scalability

### Current (MVP)
- Single backend instance, single PostgreSQL, single Redis
- Max throughput: ~100 evals/hour

### Future (Phase 7+)
- Multiple backend instances behind load balancer
- PostgreSQL read replicas, ClickHouse for analytics
- Kubernetes deployment
- Max throughput: 1000+ evals/hour
```
Save, close.

### Step 5.2: Verify

**Run in PowerShell:**
```powershell
Get-Content docs/ARCHITECTURE.md | Select-Object -First 5
```

### Task 5 Done When:
- [ ] `docs/ARCHITECTURE.md` exists
- [ ] Contains system overview and all 6 components
- [ ] Includes database schema, concurrency, error handling, security

---

## Task 6: Create Concurrency Strategy Document

### Step 6.1: Open the file

**Run in PowerShell:**
```powershell
notepad docs/CONCURRENCY.md
```

**Paste into `docs/CONCURRENCY.md`:**
```markdown
# Concurrency & Async Strategy

## Why Async?
- Evaluation engine must run multiple evaluators in parallel
- GitHub API calls are I/O bound (network wait time)
- Can serve 10+ concurrent evaluation requests

## Technology Choices

### Backend Async
- Framework: FastAPI (built on Starlette)
- Runtime: Uvicorn (ASGI server)
- Concurrency: asyncio + Python 3.11+
- Max Workers: 10 (configurable)

### Database Access
- ORM: SQLAlchemy 2.0 (async mode)
- Driver: asyncpg
- Connection Pool: 10 connections

### Task Queue
- MVP: asyncio.Queue (in-memory)
- Production: Celery + Redis
- Max Concurrent Tasks: 10

## Evaluation Pipeline Concurrency

Example (5 evaluators run via asyncio.gather):
- Sequential: 5 evaluators x 5 sec each = 25 sec total
- Parallel: max(5 sec) = 5 sec total (5x faster)

## Concurrency Limits
- API requests: ~1000 concurrent (10 workers x 100 req/worker)
- Evaluations: 10 concurrent max
- Database connections: pool 10, overflow 5, max 15

## Timeouts
- Per evaluation: 5 minutes
- Per LLM API call: 30 seconds
- Per database query: 10 seconds
- Webhook processing: 10 seconds

## Testing Concurrency
- Load test: 10 evals in parallel, then 100 evals in parallel
- Expected: 100 evals < 2x time of 10 evals due to queueing

## Failure Modes
- Race conditions: prevented via database row-level locks and unique constraints
- Task queue overflow: max queue size 100, return 429 if full
- Resource exhaustion: ~50MB per eval, 10 parallel = 500MB max; connection pooling; Redis LRU eviction
```
Save, close.

### Step 6.2: Verify

**Run in PowerShell:**
```powershell
Get-Content docs/CONCURRENCY.md | Select-Object -First 5
```

### Task 6 Done When:
- [ ] `docs/CONCURRENCY.md` exists with all sections above

---

## Task 7: Create Backend Requirements

### Step 7.1: Open the file

**Run in PowerShell:**
```powershell
notepad backend/requirements.txt
```

**Paste into `backend/requirements.txt`:**
```text
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
sqlalchemy[asyncio]==2.0.23
asyncpg==0.29.0
alembic==1.12.1
aiohttp==3.9.1
httpx==0.25.2
PyGithub==2.1.1
cryptography==41.0.7
opentelemetry-api==1.21.0
opentelemetry-sdk==1.21.0
opentelemetry-exporter-jaeger==1.21.0
opentelemetry-instrumentation-fastapi==0.42b0
opentelemetry-instrumentation-sqlalchemy==0.42b0
python-json-logger==2.0.7
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
python-dotenv==1.0.0
openai==1.3.9
detoxify==0.5.1
celery==5.3.4
redis==5.0.1
```
Save, close.

### Step 7.2: Create `__init__.py` and `config.py`

**Run in PowerShell:**
```powershell
New-Item -ItemType File -Force -Path backend/src/autoeval_ops/__init__.py
notepad backend/src/autoeval_ops/config.py
```

**Paste into `backend/src/autoeval_ops/config.py`:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://autoeval_user:dev_password@localhost:5432/autoeval_dev"
    environment: str = "development"
    log_level: str = "DEBUG"
    max_concurrent_evals: int = 10
    eval_timeout_seconds: int = 300

    class Config:
        env_file = ".env"

settings = Settings()
```
Save, close.

### Task 7 Done When:
- [ ] `backend/requirements.txt` created with all dependencies
- [ ] `backend/src/autoeval_ops/config.py` created and loads from `.env`

---

## Task 8: Create Frontend Setup

### Step 8.1: Open the file

**Run in PowerShell:**
```powershell
notepad dashboard/package.json
```

**Paste into `dashboard/package.json`:**
```json
{
  "name": "autoeval-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "next": "^14.0.0",
    "@clerk/nextjs": "^4.29.0",
    "axios": "^1.6.2",
    "tailwindcss": "^3.3.6"
  },
  "devDependencies": {
    "typescript": "^5.3.3",
    "@types/react": "^18.2.37",
    "@types/node": "^20.9.0"
  }
}
```
Save, close.

### Task 8 Done When:
- [ ] `dashboard/package.json` created with correct dependencies

---

## Task 9: Lock Tech Stack

### Step 9.1: Open the file

**Run in PowerShell:**
```powershell
notepad docs/TECH_STACK.md
```

**Paste into `docs/TECH_STACK.md`:**
```markdown
# AutoEvalOps Tech Stack (LOCKED)

## Backend
- Language: Python 3.11+
- Framework: FastAPI
- Server: Uvicorn (ASGI)
- ORM: SQLAlchemy 2.0 (async)
- Database Driver: asyncpg
- Task Queue: asyncio.Queue (MVP), Celery (production)

## Frontend
- Framework: Next.js 14+
- Language: TypeScript
- UI Framework: React 18+
- Auth: Clerk
- Styling: Tailwind CSS
- HTTP Client: axios

## Database
- Relational: PostgreSQL 15+
- Vector DB: pgvector (separate container, deferred until needed)
- Cache: Redis 7+

## Observability
- Tracing: OpenTelemetry
- Tracing Backend: Jaeger (local), Datadog (production)
- Logging: JSON structured logs
- Metrics: OpenTelemetry metrics

## DevOps
- Containerization: Docker
- Orchestration: Docker Compose (dev), Kubernetes (production)
- Deployment: AWS/GCP/Vercel
- CI/CD: GitHub Actions

## Testing
- Backend: pytest + pytest-asyncio
- Frontend: Jest + React Testing Library
- Load Testing: Locust

## Security
- API Key: bcrypt hashing
- Secrets: AES-256-GCM encryption
- Authentication: Clerk

---

## NO CHANGES AFTER THIS POINT
This stack is locked. Do not introduce new ORMs, web frameworks, databases, or frontend frameworks without explicit decision and documentation.
```
Save, close.

### Step 9.2: Commit

**Run in PowerShell:**
```powershell
git add docs/TECH_STACK.md
git commit -m "[PHASE 0] Lock tech stack - no changes after this point"
```

### Task 9 Done When:
- [ ] `docs/TECH_STACK.md` created and committed

---

## Task 10: Final Commit and Verification

### Step 10.1: Stage and commit everything

**Run in PowerShell:**
```powershell
git add -A
git commit -m "[PHASE 0] Complete setup: docker-compose, schema, architecture, tech stack"
```

### Step 10.2: Full verification pass

**Run in PowerShell:**
```powershell
Write-Host "=== Git Status ===" -ForegroundColor Cyan
git status

Write-Host "=== Docker Services ===" -ForegroundColor Cyan
docker-compose ps

Write-Host "=== Database Tables ===" -ForegroundColor Cyan
docker exec -it autoeval_postgres psql -U autoeval_user -d autoeval_dev -c "\dt"

Write-Host "=== .env Security ===" -ForegroundColor Cyan
$envTracked = git ls-files | Select-String -Pattern "^\.env$"; if ($envTracked) { Write-Host "WARNING: .env is tracked in git!" -ForegroundColor Red } else { Write-Host ".env not in git (good)" -ForegroundColor Green }

Write-Host "=== Docs ===" -ForegroundColor Cyan
Get-ChildItem docs/
```

### Step 10.3: Push to GitHub

**Run in PowerShell:**
```powershell
git push origin main
```

### Final Checklist:
- [ ] Repository pushed to GitHub
- [ ] All 6 core tables in PostgreSQL
- [ ] Docker Compose starts all 3 services (postgres, redis, pgvector)
- [ ] `.env` is NOT tracked in git (only `.env.example`)
- [ ] ARCHITECTURE.md, CONCURRENCY.md, TECH_STACK.md all complete
- [ ] Backend requirements.txt and config.py ready
- [ ] Frontend package.json ready
- [ ] No errors from any command above

---

## Next Step
Once every box above is checked, move to **Phase 1: Core Evaluation Engine**. Before starting:
1. Re-read `GUIDELINES.md`
2. Review `DEVELOPMENT_ROADMAP.md`
3. Confirm all Phase 0 tasks are done
4. Review the evaluator architecture in `ARCHITECTURE.md`

---

## Troubleshooting Log (Issues Actually Hit, and Fixes)

| Symptom | Cause | Fix |
|---|---|---|
| `docker-compose : term not recognized` | Docker Desktop not installed or not running | Install Docker Desktop, restart machine, launch it, wait for whale icon to show "running" |
| `failed to read .env: unexpected character "@"` | Here-string wrapper (`@' ... '@`) got pasted as literal text into the file instead of being run as a command | Open file in Notepad, delete the `@'` and `'@ \| Set-Content...` lines, keep only real content |
| `Set-Content : Could not find a part of the path` | Target folder doesn't exist yet | Run `New-Item -ItemType Directory -Force -Path <folder>` first, or verify Task 1.2 fully completed with `Test-Path` |
| `ERROR: extension "vector" is not available` | Tried to `CREATE EXTENSION vector` inside the plain `autoeval_postgres` container, which doesn't have pgvector installed | Removed vector/embeddings section from schema.sql entirely; pgvector work is deferred to the separate `autoeval_pgvector` container on port 5433 |
| One subfolder (e.g. `backend/src/autoeval_ops`) missing despite running the multi-path `New-Item` command | Unclear — possibly a partial paste or manual folder creation earlier | Always run `Test-Path` right after directory creation (see Task 1.3) to catch this immediately instead of several tasks later |

## PowerShell Notes
- **Prefer `notepad <file>` + paste** over here-string (`@' ... '@`) blocks — more reliable when copying code blocks from chat into a live terminal.
- `docker` and `git` commands are identical to bash — no changes needed there.
- If `docker-compose` isn't recognized but `docker` is, use `docker compose` (space, not hyphen).
- Run PowerShell **as Administrator** if you hit permission errors creating files/folders.
