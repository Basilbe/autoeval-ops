"""End-to-end API tests against a real (rolled-back) database.
Exercises deps.py's real auth branches and the route handler bodies
that Task 12's unit tests (with get_db overridden to None) never
reach - those only tested the 401 rejection path.

Uses httpx.AsyncClient over ASGITransport rather than starlette's
TestClient: TestClient drives the app from a separate thread with its own
event loop, and the db_session fixture's asyncpg connection is bound to
the test's own loop - crossing loops raises "Future attached to a
different loop" the moment a route touches the database. AsyncClient runs
the app in-process on the same loop as the test, so the overridden
db_session works normally.

Run with: pytest -m integration   (requires docker-compose up -d)
"""
from __future__ import annotations
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from autoeval_ops.api.routes.evaluations import router as evaluations_router
from autoeval_ops.api.routes.organizations import router as organizations_router
from autoeval_ops.api.routes.projects import router as projects_router
from autoeval_ops.api.routes.users import router as users_router
from autoeval_ops.db import repository
from autoeval_ops.db.session import get_db

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(db_session):
    app = FastAPI()
    app.include_router(users_router)
    app.include_router(organizations_router)
    app.include_router(projects_router)
    app.include_router(evaluations_router)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_register_and_authenticate(client):
    resp = await client.post("/api/v1/users", json={"email": "integration@example.com"})
    assert resp.status_code == 201
    api_key = resp.json()["api_key"]

    me = await client.get("/api/v1/users/me", headers={"X-API-Key": api_key})
    assert me.status_code == 200
    assert me.json()["email"] == "integration@example.com"


async def test_duplicate_email_returns_409(client):
    await client.post("/api/v1/users", json={"email": "dupe@example.com"})
    resp = await client.post("/api/v1/users", json={"email": "dupe@example.com"})
    assert resp.status_code == 409


async def test_rotate_api_key_invalidates_old_key(client):
    resp = await client.post("/api/v1/users", json={"email": "rotate@example.com"})
    old_key = resp.json()["api_key"]

    rotated = await client.post("/api/v1/users/me/api-key", headers={"X-API-Key": old_key})
    assert rotated.status_code == 200
    new_key = rotated.json()["api_key"]
    assert new_key != old_key

    old_check = await client.get("/api/v1/users/me", headers={"X-API-Key": old_key})
    assert old_check.status_code == 401
    new_check = await client.get("/api/v1/users/me", headers={"X-API-Key": new_key})
    assert new_check.status_code == 200


async def test_create_and_list_organization(client):
    resp = await client.post("/api/v1/users", json={"email": "org@example.com"})
    headers = {"X-API-Key": resp.json()["api_key"]}

    created = await client.post(
        "/api/v1/organizations", json={"name": "Test Org"}, headers=headers
    )
    assert created.status_code == 201

    listed = await client.get("/api/v1/organizations", headers=headers)
    assert len(listed.json()) == 1
    assert listed.json()[0]["name"] == "Test Org"


async def test_create_project_under_owned_organization(client):
    resp = await client.post("/api/v1/users", json={"email": "proj@example.com"})
    headers = {"X-API-Key": resp.json()["api_key"]}
    org_resp = await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers)
    org = org_resp.json()

    project = await client.post(
        f"/api/v1/projects?org_id={org['id']}",
        json={"name": "Proj", "github_repo_url": "https://github.com/o/r"},
        headers=headers,
    )
    assert project.status_code == 201
    assert project.json()["github_repo_url"] == "o/r"


async def test_create_project_rejects_organization_you_dont_own(client):
    resp1 = await client.post("/api/v1/users", json={"email": "owner@example.com"})
    headers1 = {"X-API-Key": resp1.json()["api_key"]}
    org_resp = await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers1)
    org = org_resp.json()

    resp2 = await client.post("/api/v1/users", json={"email": "intruder@example.com"})
    headers2 = {"X-API-Key": resp2.json()["api_key"]}

    attempt = await client.post(
        f"/api/v1/projects?org_id={org['id']}",
        json={"name": "Proj", "github_repo_url": "o/r"},
        headers=headers2,
    )
    assert attempt.status_code == 404


async def test_list_evals_for_project_you_dont_own_returns_404(client):
    resp1 = await client.post("/api/v1/users", json={"email": "a@example.com"})
    headers1 = {"X-API-Key": resp1.json()["api_key"]}
    org_resp = await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers1)
    org = org_resp.json()
    project_resp = await client.post(
        f"/api/v1/projects?org_id={org['id']}",
        json={"name": "P", "github_repo_url": "o/r2"},
        headers=headers1,
    )
    project = project_resp.json()

    resp2 = await client.post("/api/v1/users", json={"email": "b@example.com"})
    headers2 = {"X-API-Key": resp2.json()["api_key"]}

    resp = await client.get(f"/api/v1/projects/{project['id']}/evals", headers=headers2)
    assert resp.status_code == 404


async def test_empty_evals_list_for_fresh_project(client):
    resp = await client.post("/api/v1/users", json={"email": "fresh@example.com"})
    headers = {"X-API-Key": resp.json()["api_key"]}
    org_resp = await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers)
    org = org_resp.json()
    project_resp = await client.post(
        f"/api/v1/projects?org_id={org['id']}",
        json={"name": "P", "github_repo_url": "o/r3"},
        headers=headers,
    )
    project = project_resp.json()

    evals = await client.get(f"/api/v1/projects/{project['id']}/evals", headers=headers)
    assert evals.status_code == 200
    assert evals.json() == []


async def test_get_project_by_id_returns_200_for_owner(client):
    resp = await client.post("/api/v1/users", json={"email": "getproj@example.com"})
    headers = {"X-API-Key": resp.json()["api_key"]}
    org = (
        await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers)
    ).json()
    project = (
        await client.post(
            f"/api/v1/projects?org_id={org['id']}",
            json={"name": "P", "github_repo_url": "o/r4"},
            headers=headers,
        )
    ).json()

    fetched = await client.get(f"/api/v1/projects/{project['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == project["id"]
    assert fetched.json()["github_repo_url"] == "o/r4"


async def test_get_project_by_id_returns_404_for_non_owner(client):
    resp1 = await client.post("/api/v1/users", json={"email": "owner2@example.com"})
    headers1 = {"X-API-Key": resp1.json()["api_key"]}
    org = (
        await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers1)
    ).json()
    project = (
        await client.post(
            f"/api/v1/projects?org_id={org['id']}",
            json={"name": "P", "github_repo_url": "o/r5"},
            headers=headers1,
        )
    ).json()

    resp2 = await client.post("/api/v1/users", json={"email": "intruder2@example.com"})
    headers2 = {"X-API-Key": resp2.json()["api_key"]}

    attempt = await client.get(f"/api/v1/projects/{project['id']}", headers=headers2)
    assert attempt.status_code == 404


async def test_get_evaluation_by_id_returns_200_for_owner(client, db_session):
    resp = await client.post("/api/v1/users", json={"email": "evalowner@example.com"})
    headers = {"X-API-Key": resp.json()["api_key"]}
    org = (
        await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers)
    ).json()
    project = (
        await client.post(
            f"/api/v1/projects?org_id={org['id']}",
            json={"name": "P", "github_repo_url": "o/r6"},
            headers=headers,
        )
    ).json()

    # No webhook fires in this test, so the evaluation row is created
    # directly via the repository layer, exactly as the orchestrator does.
    evaluation = await repository.create_evaluation(
        db_session,
        project_id=uuid.UUID(project["id"]),
        commit_hash="a" * 40,
        prompt_version="prompts/summarize.txt",
        model_name="gpt-4",
        test_cases_count=1,
    )
    await repository.complete_evaluation(
        db_session,
        evaluation,
        status="pass",
        results_json={"cases": []},
        metric_rows=[
            {"metric_name": "correctness", "metric_value": 90.0, "status": "pass", "details": {}}
        ],
    )

    fetched = await client.get(f"/api/v1/evals/{evaluation.id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "pass"
    assert len(fetched.json()["results"]) == 1


async def test_get_evaluation_by_id_returns_404_for_non_owner(client, db_session):
    resp1 = await client.post("/api/v1/users", json={"email": "evalowner2@example.com"})
    headers1 = {"X-API-Key": resp1.json()["api_key"]}
    org = (
        await client.post("/api/v1/organizations", json={"name": "Org"}, headers=headers1)
    ).json()
    project = (
        await client.post(
            f"/api/v1/projects?org_id={org['id']}",
            json={"name": "P", "github_repo_url": "o/r7"},
            headers=headers1,
        )
    ).json()

    evaluation = await repository.create_evaluation(
        db_session,
        project_id=uuid.UUID(project["id"]),
        commit_hash="b" * 40,
        prompt_version="p",
        model_name="gpt-4",
        test_cases_count=1,
    )
    await repository.complete_evaluation(
        db_session, evaluation, status="pass", results_json={}, metric_rows=[]
    )

    resp2 = await client.post("/api/v1/users", json={"email": "evalintruder@example.com"})
    headers2 = {"X-API-Key": resp2.json()["api_key"]}

    attempt = await client.get(f"/api/v1/evals/{evaluation.id}", headers=headers2)
    assert attempt.status_code == 404
