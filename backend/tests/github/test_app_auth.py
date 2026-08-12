"""Tests for GitHubAppAuth. Uses a freshly generated throwaway RSA key
(not a real GitHub App key) purely to exercise JWT signing - no network
calls, no real credentials."""
from __future__ import annotations

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from autoeval_ops.github.app_auth import GitHubAppAuth


@pytest.fixture(scope="module")
def test_private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def make_mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_generate_jwt_has_expected_claims(test_private_key):
    auth = GitHubAppAuth(app_id="12345", private_key=test_private_key)
    token = auth.generate_jwt()
    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["iss"] == "12345"
    assert decoded["exp"] > decoded["iat"]


def test_generate_jwt_uses_rs256_algorithm(test_private_key):
    auth = GitHubAppAuth(app_id="999", private_key=test_private_key)
    token = auth.generate_jwt()
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"


async def test_get_installation_token_fetches_and_caches(test_private_key):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(
            200, json={"token": "installation-token-abc", "expires_at": "2099-01-01T00:00:00Z"}
        )

    auth = GitHubAppAuth(
        app_id="12345", private_key=test_private_key, http_client=make_mock_client(handler)
    )
    token1 = await auth.get_installation_token(999)
    token2 = await auth.get_installation_token(999)

    assert token1 == "installation-token-abc"
    assert token2 == "installation-token-abc"
    assert call_count["n"] == 1  # second call used the cache


async def test_get_installation_token_refetches_when_cache_expired(test_private_key):
    def handler(request):
        return httpx.Response(200, json={"token": "fresh-token", "expires_at": "2000-01-01T00:00:00Z"})

    auth = GitHubAppAuth(
        app_id="12345", private_key=test_private_key, http_client=make_mock_client(handler)
    )
    token = await auth.get_installation_token(1)
    assert token == "fresh-token"