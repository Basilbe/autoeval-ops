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
