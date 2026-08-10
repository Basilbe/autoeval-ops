# AutoEvalOps Development Roadmap

## Project Goal
**Build a deployed B2B SaaS platform that automatically tests LLM prompts/models on every GitHub PR and reports results.**

---

## Phase 0: Setup & Architecture (Week 1)

### Deliverables
- [ ] Project repository created (GitHub)
- [ ] Development environment configured (Python 3.11+, Node.js 18+, Docker)
- [ ] Architecture diagram documented
- [ ] Database schema designed
- [ ] Async/concurrency strategy documented
- [ ] Tech stack locked (no changes after this phase)

### Tasks

1. **Create Repository Structure**
   ```
   autoeval-ops/
   ├── backend/
   │   ├── core/           (Phase 1)
   │   ├── github/         (Phase 2)
   │   ├── api/            (Phase 3)
   │   ├── observability/  (Phase 5)
   │   ├── config.py
   │   ├── requirements.txt
   │   └── tests/
   ├── dashboard/          (Phase 4)
   │   ├── pages/
   │   ├── components/
   │   └── package.json
   ├── docs/
   │   ├── README.md
   │   ├── ARCHITECTURE.md
   │   └── API.md
   ├── docker-compose.yml
   └── .env.example
   ```

2. **Tech Stack Lock-In**
   - Backend: Python 3.11 + FastAPI + asyncio
   - Async HTTP: `httpx` + `aiohttp`
   - Async Task Queue: Celery + Redis (or simple asyncio.Queue for MVP)
   - Database: PostgreSQL + SQLAlchemy ORM
   - Vector DB: pgvector (built into PostgreSQL)
   - Analytics: ClickHouse (optional for MVP, add in Phase 5)
   - Traces: OpenTelemetry + Jaeger (local) / Datadog (prod)
   - Frontend: Next.js 14+ (React + TypeScript)
   - Auth: Clerk or Supabase Auth
   - Deployment: Docker + AWS/GCP/Vercel

3. **Database Schema**
   ```sql
   - users (id, email, api_key, created_at)
   - organizations (id, user_id, name, plan, created_at)
   - projects (id, org_id, github_repo_url, github_token_encrypted)
   - evaluations (id, project_id, commit_hash, prompt_version, 
                  results_json, created_at)
   - eval_results (id, eval_id, metric_name, metric_value, status)
   - traces (id, eval_id, trace_data_json, latency_ms, cost_usd)
   ```

4. **Architecture Document**
   - Flow diagram: GitHub push → Webhook → Queue → Eval Engine → DB → PR Comment
   - Concurrency model: How many evals run in parallel? (e.g., 10 at a time)
   - Error handling: What happens if eval fails? Retry? Timeout?
   - Security: How is GitHub token stored? API keys?

5. **Environment Setup**
   ```bash
   # Create .env.example
   DATABASE_URL=postgresql://user:pass@localhost/autoeval
   GITHUB_APP_ID=xxx
   GITHUB_PRIVATE_KEY=xxx
   OPENAI_API_KEY=xxx
   CLERK_SECRET_KEY=xxx
   REDIS_URL=redis://localhost:6379
   ```

### Definition of Done
- [ ] Repository is ready
- [ ] Docker Compose file starts all services (postgres, redis)
- [ ] ARCHITECTURE.md describes full flow with diagrams
- [ ] Database migrations can run
- [ ] No code written yet—only structure and config

### Success Criteria
You can run `docker-compose up` and have a working dev environment with no code errors.

---

## Phase 1: Core Evaluation Engine (Weeks 2-3)

### Deliverables
- [ ] Evaluator classes (Correctness, Toxicity, Hallucination, Cost, Latency)
- [ ] Async evaluation pipeline
- [ ] Unit tests (100% coverage for this phase)
- [ ] Benchmarks (latency for 10 evals, 100 evals)
- [ ] Local CLI tool to run evals

### Tasks

1. **Build Evaluator Base Class**
   ```python
   # backend/core/evaluator.py
   class Evaluator(ABC):
       async def evaluate(self, text: str) -> EvaluationResult:
           pass
   
   class CorrectnessEvaluator(Evaluator):
       # LLM-as-judge: Compare output to gold standard
   
   class ToxicityEvaluator(Evaluator):
       # Use Detoxify or Perspective API
   
   class HallucinationEvaluator(Evaluator):
       # Fact check against context
   
   class CostEvaluator(Evaluator):
       # Track tokens × model pricing
   
   class LatencyEvaluator(Evaluator):
       # Measure response time
   ```

2. **Build Async Evaluation Pipeline**
   ```python
   # backend/core/pipeline.py
   class EvaluationPipeline:
       async def evaluate_prompt(
           self, 
           prompt: str, 
           model: str, 
           test_cases: List[str]
       ) -> EvaluationReport:
           # Run all evaluators in parallel
           # Return aggregated results
   ```

3. **Write Unit Tests**
   - 5+ tests per evaluator
   - Mock LLM API calls (don't use real API in tests)
   - Test edge cases (empty input, very long input, unicode)
   - Test concurrent eval pipeline (10 evals at once)

4. **Create CLI Tool**
   ```bash
   python -m backend.core.cli evaluate \
     --prompt "Summarize: {text}" \
     --model gpt-4 \
     --test-cases test_cases.json
   ```

5. **Benchmark**
   ```
   Time 10 sequential evals: ___ ms
   Time 10 parallel evals: ___ ms
   Time 100 parallel evals: ___ ms
   Time 1000 parallel evals: ___ ms
   ```

### Definition of Done
- [ ] All evaluators work independently
- [ ] Async pipeline runs 10+ evals in parallel without errors
- [ ] Unit test suite passes with 100% coverage
- [ ] CLI tool works locally
- [ ] Benchmark results documented in BENCHMARK.md

### Success Criteria
```bash
pytest backend/core/tests/ -v --cov
# All tests pass
# Coverage ≥ 95%
# No warnings
```

---

## Phase 2: GitHub Integration (Weeks 4-5)

### Deliverables
- [ ] GitHub App created and configured
- [ ] Webhook receiver (FastAPI endpoint)
- [ ] PR comment generator
- [ ] Async task queue (Celery or asyncio.Queue)
- [ ] Integration tests (mocked GitHub API)
- [ ] Deployed to staging environment

### Tasks

1. **Create GitHub App**
   - Name: AutoEvalOps
   - Permissions: Read code, Read pull requests, Write pull requests
   - Events: push, pull_request
   - Webhooks: Configure webhook URL (will be your API endpoint)

2. **Build Webhook Receiver**
   ```python
   # backend/github/webhooks.py
   @app.post("/github/webhook")
   async def handle_webhook(payload: dict) -> dict:
       if payload["action"] == "opened":
           # New PR
           await process_pr(payload)
       elif payload["ref"].startswith("refs/heads/"):
           # Push to branch
           await process_push(payload)
   ```

3. **Build Task Queue**
   ```python
   # backend/github/tasks.py
   async def evaluate_pr(repo: str, pr_number: int) -> None:
       # 1. Fetch PR files
       # 2. Extract prompt/config changes
       # 3. Run Phase 1 evaluators
       # 4. Post comment
   ```

4. **Build PR Comment Generator**
   ```python
   # backend/github/commenter.py
   async def post_pr_comment(repo: str, pr_number: int, results: dict) -> None:
       comment = f"""
       ## ✅ AutoEvalOps Evaluation Report
       
       **Correctness:** {results['correctness']} / 100
       **Toxicity:** {results['toxicity']} / 100
       **Latency:** {results['latency']}ms (avg)
       **Cost:** ${results['cost']}
       
       [Full Report](#)
       """
   ```

5. **Write Integration Tests**
   - Mock GitHub API responses
   - Test webhook signature verification
   - Test PR comment creation
   - Test error handling (bad webhook, missing fields)

6. **Deploy to Staging**
   - Docker container pushed to registry
   - Deployed to staging server (AWS/GCP)
   - GitHub webhook URL points to staging
   - Test with real PR in test repo

### Definition of Done
- [ ] GitHub App is registered and installed on test repo
- [ ] Webhook receiver accepts and processes events
- [ ] PR comments are posted with evaluation results
- [ ] All integration tests pass
- [ ] No errors in production logs (staging)

### Success Criteria
```
1. Create test PR in test repo
2. Webhook fires
3. Evaluation completes
4. Comment appears on PR
5. No errors in logs
```

---

## Phase 3: Backend API (Weeks 6-7)

### Deliverables
- [ ] FastAPI application with core endpoints
- [ ] User authentication (Clerk)
- [ ] API key management
- [ ] Database ORM models
- [ ] Rate limiting & error handling
- [ ] API documentation (Swagger/OpenAPI)
- [ ] API tests (100% endpoint coverage)

### Tasks

1. **Set Up FastAPI Application**
   ```python
   # backend/api/main.py
   app = FastAPI()
   
   @app.get("/health")
   async def health() -> dict:
       return {"status": "ok"}
   ```

2. **Authentication & API Keys**
   ```python
   # backend/api/auth.py
   @app.post("/auth/login")
   async def login(email: str, password: str) -> dict:
       # Use Clerk SDK
   
   @app.post("/auth/generate-api-key")
   async def generate_api_key(user_id: str) -> dict:
       # Generate and store encrypted key
   ```

3. **Core Endpoints**
   ```
   POST   /api/v1/projects          # Create project
   GET    /api/v1/projects/{id}     # Get project
   POST   /api/v1/projects/{id}/evals        # Trigger evaluation
   GET    /api/v1/projects/{id}/evals       # List evals
   GET    /api/v1/evals/{id}                 # Get eval results
   ```

4. **Database Models (SQLAlchemy)**
   ```python
   # backend/api/models.py
   class User(Base):
       id: UUID
       email: str
       created_at: datetime
   
   class Project(Base):
       id: UUID
       user_id: UUID
       github_repo: str
   
   class Evaluation(Base):
       id: UUID
       project_id: UUID
       results: JSON
   ```

5. **Write API Tests**
   - Test all endpoints with valid/invalid inputs
   - Test authentication (missing token, expired token)
   - Test rate limiting
   - Test error responses (400, 401, 404, 500)

6. **API Documentation**
   - OpenAPI schema auto-generated by FastAPI
   - Swagger UI at `/docs`
   - README with example cURL commands

### Definition of Done
- [ ] All endpoints implemented
- [ ] Authentication works (can login, get API key)
- [ ] All API tests pass (100% coverage)
- [ ] No console warnings
- [ ] OpenAPI docs are complete

### Success Criteria
```bash
pytest backend/api/tests/ -v --cov
# All tests pass
# Coverage ≥ 95%
# Swagger UI shows all endpoints
```

---

## Phase 4: Frontend Dashboard (Weeks 8-9)

### Deliverables
- [ ] Next.js application scaffold
- [ ] Authentication UI (login/signup)
- [ ] Projects list page
- [ ] Evaluation results page (table view)
- [ ] Real-time updates (WebSocket or polling)
- [ ] Component library (buttons, cards, tables)
- [ ] Responsive design (mobile + desktop)

### Tasks

1. **Set Up Next.js**
   ```bash
   npx create-next-app@latest dashboard --typescript
   ```

2. **Authentication Flow**
   ```tsx
   // dashboard/pages/login.tsx
   import { SignInButton } from "@clerk/nextjs";
   
   export default function LoginPage() {
       return <SignInButton />;
   }
   ```

3. **Projects Page**
   ```tsx
   // dashboard/pages/projects/index.tsx
   // List all projects
   // Create new project
   // Link to GitHub repo
   ```

4. **Evaluation Results Page**
   ```tsx
   // dashboard/pages/projects/[id]/evals.tsx
   // Table: timestamp, commit, correctness, toxicity, cost, latency
   // Filter by status (passed, failed, warning)
   // Real-time updates
   ```

5. **Component Library**
   - Button
   - Card
   - Table
   - Loading spinner
   - Error message
   - Success message

6. **Styling**
   - Tailwind CSS
   - Dark mode support
   - Mobile responsive

### Definition of Done
- [ ] Can log in via Clerk
- [ ] Can view list of projects
- [ ] Can click on project and see evaluation history
- [ ] Page loads without errors
- [ ] Responsive on mobile and desktop

### Success Criteria
```bash
npm run dev
# Navigate to http://localhost:3000
# Can log in, see projects, see evals
# No console errors
# Mobile view works
```

---

## Phase 5: Observability & Telemetry (Weeks 10-11)

### Deliverables
- [ ] OpenTelemetry instrumentation
- [ ] Trace generation for all evals
- [ ] Latency & cost metrics collection
- [ ] ClickHouse integration (optional for MVP)
- [ ] Public `/status` page with metrics
- [ ] Production monitoring setup
- [ ] Error tracking (Sentry)

### Tasks

1. **Add OpenTelemetry**
   ```python
   # backend/observability/telemetry.py
   from opentelemetry import trace, metrics
   
   tracer = trace.get_tracer(__name__)
   
   async def evaluate_with_tracing(prompt: str):
       with tracer.start_as_current_span("evaluate_prompt"):
           # Evaluation logic
   ```

2. **Collect Metrics**
   ```python
   # Track:
   # - Evaluation latency (p50, p95, p99)
   # - Cost per request
   # - Error rate
   # - Concurrency
   ```

3. **Public Status Page**
   ```tsx
   // dashboard/pages/status.tsx
   // Real-time metrics:
   // - Current RPS
   // - Average latency
   // - Cost per eval
   // - Uptime
   // - Sample traces
   ```

4. **Jaeger/Datadog Integration**
   - Local Jaeger for dev
   - Datadog for production
   - View traces: `http://localhost:16686` (Jaeger)

5. **Error Tracking**
   - Sentry integration
   - Alert on error rate > 1%

### Definition of Done
- [ ] All major code paths emit traces
- [ ] Metrics are collected and stored
- [ ] Status page shows live data
- [ ] Error tracking works
- [ ] Local tracing works with Jaeger

### Success Criteria
```bash
# Run eval
# Check Jaeger: http://localhost:16686
# See complete trace with latency
# Check status page: metrics update in real-time
```

---

## Phase 6: Deployment & Polish (Weeks 12)

### Deliverables
- [ ] Production deployment pipeline (CI/CD)
- [ ] Custom domain & SSL
- [ ] Database backups
- [ ] Security audit (secrets, SQL injection, CORS)
- [ ] Load testing (500+ RPS)
- [ ] Documentation complete
- [ ] README with architecture & trade-offs
- [ ] Marketing site / landing page

### Tasks

1. **CI/CD Pipeline**
   ```yaml
   # .github/workflows/deploy.yml
   - Run tests
   - Build Docker image
   - Push to registry
   - Deploy to production
   ```

2. **Custom Domain**
   - Buy domain
   - Point DNS to deployment (Vercel/AWS)
   - SSL certificate (Let's Encrypt)

3. **Security**
   - Rotate GitHub token
   - Encrypt API keys in database
   - Add CORS headers
   - SQL injection testing (SQLAlchemy ORM protects, but verify)
   - Rate limiting (100 req/min per user)

4. **Load Testing**
   ```bash
   # Simulate 500 concurrent evals
   # Measure: throughput, latency, errors
   ```

5. **Documentation**
   - README with full setup instructions
   - ARCHITECTURE.md with diagrams
   - API.md with all endpoints
   - POSTMORTEM.md with trade-offs and lessons learned

6. **Landing Page**
   - Clerk authentication
   - Pricing page (if SaaS)
   - Docs link
   - GitHub link

### Definition of Done
- [ ] Deployed to production with custom domain
- [ ] SSL certificate valid
- [ ] All tests pass in production
- [ ] Can handle 500+ RPS without errors
- [ ] Documentation is complete and accurate

### Success Criteria
```bash
# Visit https://yourdomain.com
# Can log in
# Can create project
# Can trigger eval
# See results in dashboard
# No errors in logs
# /status page shows live metrics
```

---

## Critical Milestones

| Week | Milestone | Gate |
|------|-----------|------|
| 1 | Setup complete | Docker Compose works |
| 3 | Core engine done | CLI tool works, benchmarks logged |
| 5 | GitHub integration done | PR comments post automatically |
| 7 | Backend API done | All endpoints tested |
| 9 | Frontend done | Can view evals in dashboard |
| 11 | Observability done | Traces visible, status page works |
| 12 | Deployed to production | Live with custom domain |

---

## Escalation: If You Get Stuck

1. **Engine evaluators fail?** → Phase 1 gate blocks Phase 2. Debug it.
2. **GitHub webhook doesn't work?** → Phase 2 gate blocks Phase 3. Check logs, verify webhook secret.
3. **API tests fail?** → Phase 3 gate blocks Phase 4. Add debug logging, isolate issue.
4. **Dashboard won't connect to API?** → Phase 4 gate blocks Phase 5. Check network, CORS, auth token.
5. **Traces missing?** → Phase 5 gate blocks Phase 6. Verify tracer is initialized, spans are created.

**Do NOT skip a phase or move forward with incomplete work.**

---

## Success Definition

You're done when:

1. ✅ Code is deployed and live at a custom domain
2. ✅ All phases complete with zero broken code
3. ✅ Status page shows live metrics
4. ✅ README documents architecture + trade-offs
5. ✅ Can handle a real customer's workflow (GitHub PR → eval → comment → dashboard view)