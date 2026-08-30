"""Verifies /api/v1/status is genuinely public (no auth) and exposes only
aggregate data - no project names, repo URLs, emails, or prompt content."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autoeval_ops.api.routes.status import router as status_router
from autoeval_ops.db.session import get_db
from autoeval_ops.observability.metrics import StatusMetrics


@pytest.fixture
def client(monkeypatch):
    async def _fake_metrics(db):
        return StatusMetrics(
            total_evaluations=5,
            evaluations_24h=2,
            pass_rate=0.8,
            error_rate=0.2,
            latency_p50_ms=120.0,
            latency_p95_ms=300.0,
            latency_p99_ms=450.0,
            avg_cost_usd=0.0006,
            total_cost_usd=0.003,
            status_counts={"pass": 4, "fail": 1},
        )

    monkeypatch.setattr(
        "autoeval_ops.api.routes.status.collect_status_metrics", _fake_metrics
    )

    app = FastAPI()
    app.include_router(status_router)

    async def _no_db():
        yield None

    app.dependency_overrides[get_db] = _no_db
    return TestClient(app)


def test_status_requires_no_authentication(client):
    # No X-API-Key, no Authorization header - must still succeed.
    assert client.get("/api/v1/status").status_code == 200


def test_status_reports_operational(client):
    body = client.get("/api/v1/status").json()
    assert body["status"] == "operational"
    assert body["service"] == "AutoEvalOps"


def test_status_includes_expected_metric_shape(client):
    metrics = client.get("/api/v1/status").json()["metrics"]
    assert metrics["total_evaluations"] == 5
    assert metrics["latency"]["p95_ms"] == 300.0
    assert metrics["cost"]["total_usd"] == 0.003


def test_status_exposes_no_identifying_fields(client):
    """Regression guard: this endpoint is public, so it must never start
    leaking project/repo/user data as it evolves."""
    body = client.get("/api/v1/status").text.lower()
    for leaked in ["github_repo_url", "email", "api_key", "prompt_version", "commit_hash"]:
        assert leaked not in body


def test_status_includes_uptime(client):
    body = client.get("/api/v1/status").json()
    assert "uptime_seconds" in body
    assert body["uptime_seconds"] >= 0