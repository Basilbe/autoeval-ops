"""Tests for server.py's testable pieces: _load_app_auth() in isolation,
and the full app (health + lifespan startup/shutdown) via a temp key file."""
from __future__ import annotations

from fastapi.testclient import TestClient

from autoeval_ops.config import settings
from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.server import _load_app_auth, app


def test_load_app_auth_reads_key_file(tmp_path, monkeypatch):
    key_file = tmp_path / "key.pem"
    key_file.write_text("fake-key-content")
    monkeypatch.setattr(settings, "github_app_private_key_path", str(key_file))
    monkeypatch.setattr(settings, "github_app_id", "12345")

    app_auth = _load_app_auth()
    assert isinstance(app_auth, GitHubAppAuth)
    assert app_auth.app_id == "12345"
    assert app_auth.private_key == "fake-key-content"


def test_health_endpoint_with_full_app_lifespan(tmp_path, monkeypatch):
    key_file = tmp_path / "key.pem"
    key_file.write_text("fake-key-content")
    monkeypatch.setattr(settings, "github_app_private_key_path", str(key_file))
    monkeypatch.setattr(settings, "github_app_id", "12345")

    with TestClient(app) as client:  # triggers real lifespan startup/shutdown
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}