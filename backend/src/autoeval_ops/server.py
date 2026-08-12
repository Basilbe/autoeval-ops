"""Minimal FastAPI app hosting the GitHub webhook receiver.
Phase 3 expands this into the full backend API rather than replacing it.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI

from autoeval_ops.github.queue import eval_queue
from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.orchestrator import handle_eval_job
from autoeval_ops.github.webhook import router as github_router
from autoeval_ops.config import settings, resolve_repo_path

def _load_app_auth() -> GitHubAppAuth:
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


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(github_router)