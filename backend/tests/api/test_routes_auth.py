"""Verifies protected routes reject unauthenticated requests. Uses a
dependency override so no database is needed - a request that gets past
auth would fail on the DB, so most of these deliberately only assert on
401s.

test_invalid_uuid_path_returns_422 additionally overrides get_current_user
itself (not just get_db) to bypass auth entirely, isolating path-parameter
validation from auth - a dependency that raises during resolution (like
get_current_user's 401) short-circuits FastAPI's normal path-validation
error handling, so without this override the request never gets far enough
to reach the invalid-UUID check.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autoeval_ops.api.deps import get_current_user
from autoeval_ops.api.routes.evaluations import router as evaluations_router
from autoeval_ops.api.routes.organizations import router as organizations_router
from autoeval_ops.api.routes.projects import router as projects_router
from autoeval_ops.api.routes.users import router as users_router
from autoeval_ops.db.session import get_db


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(users_router)
    app.include_router(organizations_router)
    app.include_router(projects_router)
    app.include_router(evaluations_router)
    return app


@pytest.fixture
def client():
    app = _build_app()

    async def _no_db():
        yield None

    app.dependency_overrides[get_db] = _no_db
    return TestClient(app)


@pytest.fixture
def authenticated_client():
    app = _build_app()

    class _DummyUser:
        id = "00000000-0000-0000-0000-000000000099"

    async def _no_db():
        yield None

    async def _fake_user():
        return _DummyUser()

    app.dependency_overrides[get_db] = _no_db
    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def test_users_me_requires_auth(client):
    assert client.get("/api/v1/users/me").status_code == 401


def test_list_organizations_requires_auth(client):
    assert client.get("/api/v1/organizations").status_code == 401


def test_list_projects_requires_auth(client):
    assert client.get("/api/v1/projects").status_code == 401


def test_get_evaluation_requires_auth(client):
    eval_id = "00000000-0000-0000-0000-000000000001"
    assert client.get(f"/api/v1/evals/{eval_id}").status_code == 401


def test_invalid_uuid_path_returns_422(authenticated_client):
    assert authenticated_client.get("/api/v1/evals/not-a-uuid").status_code == 422