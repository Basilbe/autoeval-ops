"""Unit tests for the Clerk bearer-token branch in deps.get_current_user.
ClerkVerifier's own logic is covered in tests/api/test_clerk.py - this
file only checks that get_current_user handles a missing/malformed
Authorization header, and a failing verifier, without crashing (falls
through to a 401 rather than propagating the verifier's exception)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from autoeval_ops.api import deps
import autoeval_ops.api.clerk as clerk_module
from autoeval_ops.db import repository


async def test_missing_authorization_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(db=None, x_api_key="", authorization="")
    assert exc_info.value.status_code == 401


async def test_non_bearer_authorization_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(db=None, x_api_key="", authorization="Basic somecreds")
    assert exc_info.value.status_code == 401


async def test_clerk_verifier_exception_falls_through_to_401(monkeypatch):
    monkeypatch.setattr(deps.settings, "clerk_jwks_url", "https://fake.example.com/jwks")

    class ExplodingVerifier:
        def __init__(self, jwks_url):
            pass

        async def verify(self, token):
            raise ValueError("bad token")

    monkeypatch.setattr(clerk_module, "ClerkVerifier", ExplodingVerifier)

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(db=None, x_api_key="", authorization="Bearer sometoken")
    assert exc_info.value.status_code == 401


async def test_clerk_token_ignored_when_jwks_url_not_configured(monkeypatch):
    monkeypatch.setattr(deps.settings, "clerk_jwks_url", "")

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(db=None, x_api_key="", authorization="Bearer sometoken")
    assert exc_info.value.status_code == 401


async def test_clerk_token_with_no_email_claim_raises_401(monkeypatch):
    monkeypatch.setattr(deps.settings, "clerk_jwks_url", "https://fake.example.com/jwks")

    class NoEmailVerifier:
        def __init__(self, jwks_url):
            pass

        async def verify(self, token):
            return {"sub": "user_123"}  # Clerk's default session claims have no email

    monkeypatch.setattr(clerk_module, "ClerkVerifier", NoEmailVerifier)

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(db=None, x_api_key="", authorization="Bearer sometoken")
    assert exc_info.value.status_code == 401


async def test_clerk_verified_email_with_no_matching_user_is_provisioned(monkeypatch):
    """A verified Clerk token whose email has no existing users row must not
    401 - it should be provisioned just-in-time via
    repository.get_or_create_user_by_email, since Clerk logins never go
    through the manual POST /api/v1/users registration flow."""
    monkeypatch.setattr(deps.settings, "clerk_jwks_url", "https://fake.example.com/jwks")

    class FakeVerifier:
        def __init__(self, jwks_url):
            pass

        async def verify(self, token):
            return {"email": "new.clerk.user@example.com"}

    monkeypatch.setattr(clerk_module, "ClerkVerifier", FakeVerifier)

    calls = []

    async def fake_get_or_create(db, email):
        calls.append(email)
        return SimpleNamespace(id="fake-user-id", email=email)

    monkeypatch.setattr(repository, "get_or_create_user_by_email", fake_get_or_create)

    user = await deps.get_current_user(db=None, x_api_key="", authorization="Bearer sometoken")
    assert user.email == "new.clerk.user@example.com"
    assert calls == ["new.clerk.user@example.com"]
