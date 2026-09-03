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