"""FastAPI application: GitHub webhook receiver (Phase 2) + backend API
(Phase 3). Expanded from Phase 2's minimal server, not replaced.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from autoeval_ops.github.queue import eval_queue
from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.orchestrator import handle_eval_job
from autoeval_ops.github.webhook import router as github_router
from autoeval_ops.api.routes.users import router as users_router
from autoeval_ops.api.routes.organizations import router as organizations_router
from autoeval_ops.api.routes.projects import router as projects_router
from autoeval_ops.api.routes.evaluations import router as evaluations_router
from autoeval_ops.db.session import dispose_engine
from autoeval_ops.config import settings, resolve_repo_path

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


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
    await dispose_engine()


app = FastAPI(
    title="AutoEvalOps",
    description="Automated LLM prompt evaluation on every pull request.",
    version="0.3.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Phase 4 dashboard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(github_router)
app.include_router(users_router)
app.include_router(organizations_router)
app.include_router(projects_router)
app.include_router(evaluations_router)