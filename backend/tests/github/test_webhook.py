"""Tests for the webhook receiver: signature verification and event/action
filtering. Uses a minimal test app (just the router, no lifespan) so these
tests don't need a real private key file on disk."""
from __future__ import annotations
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autoeval_ops.github.webhook import router
from autoeval_ops.github.queue import eval_queue
from autoeval_ops.config import settings

WEBHOOK_SECRET = "test-secret"


@pytest.fixture(autouse=True)
def set_webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", WEBHOOK_SECRET)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _pr_payload(action: str = "opened") -> dict:
    return {
        "action": action,
        "installation": {"id": 42},
        "repository": {"owner": {"login": "bazil"}, "name": "autoeval-ops"},
        "pull_request": {"number": 7, "head": {"sha": "deadbeef"}},
    }


def test_rejects_invalid_signature(client):
    body = json.dumps(_pr_payload()).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 401


def test_ignores_non_pull_request_events(client):
    body = json.dumps(_pr_payload()).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "push"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_ignores_irrelevant_pr_actions(client):
    body = json.dumps(_pr_payload(action="closed")).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_enqueues_job_for_opened_pr(client):
    body = json.dumps(_pr_payload(action="opened")).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert eval_queue.queue.qsize() >= 1
    eval_queue.queue.get_nowait()  # drain so this doesn't leak into other tests


def test_enqueues_job_for_synchronize_action(client):
    body = json.dumps(_pr_payload(action="synchronize")).encode()
    resp = client.post(
        "/github/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    eval_queue.queue.get_nowait()