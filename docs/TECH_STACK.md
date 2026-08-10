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