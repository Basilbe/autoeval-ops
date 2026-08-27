"""Tests for ClerkVerifier. Uses a freshly generated throwaway RSA key
(not a real Clerk key) and httpx.MockTransport to fake the JWKS endpoint -
no network calls, no real Clerk account. Mirrors the pattern already used
for GitHubAppAuth in tests/github/test_app_auth.py."""
from __future__ import annotations
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from autoeval_ops.api.clerk import ClerkVerifier


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture
def jwk(rsa_keypair):
    _, public_key = rsa_keypair
    jwk_dict = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk_dict["kid"] = "test-kid-1"
    return jwk_dict


def make_mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_init_sets_jwks_url_and_empty_cache():
    verifier = ClerkVerifier("https://clerk.example.com/.well-known/jwks.json")
    assert verifier.jwks_url == "https://clerk.example.com/.well-known/jwks.json"
    assert verifier._jwks_cache is None
    assert verifier._jwks_fetched_at == 0.0


async def test_get_jwks_fetches_and_caches(jwk):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(200, json={"keys": [jwk]})

    verifier = ClerkVerifier("https://clerk.example.com/jwks", http_client=make_mock_client(handler))
    result1 = await verifier._get_jwks()
    result2 = await verifier._get_jwks()

    assert result1 == {"keys": [jwk]}
    assert result2 == {"keys": [jwk]}
    assert call_count["n"] == 1  # second call used the cache


async def test_get_jwks_returns_cached_when_fresh(jwk):
    def handler(request):
        raise AssertionError("should not fetch while cache is fresh")

    verifier = ClerkVerifier("https://clerk.example.com/jwks", http_client=make_mock_client(handler))
    verifier._jwks_cache = {"keys": [jwk]}
    verifier._jwks_fetched_at = time.time()

    result = await verifier._get_jwks()
    assert result == {"keys": [jwk]}


async def test_get_jwks_refetches_when_cache_expired(jwk):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(200, json={"keys": [jwk]})

    verifier = ClerkVerifier("https://clerk.example.com/jwks", http_client=make_mock_client(handler))
    verifier._jwks_cache = {"keys": []}
    verifier._jwks_fetched_at = time.time() - verifier._cache_ttl_seconds - 1

    await verifier._get_jwks()
    assert call_count["n"] == 1


async def test_verify_returns_claims_for_valid_token(rsa_keypair, jwk):
    private_key, _ = rsa_keypair

    def handler(request):
        return httpx.Response(200, json={"keys": [jwk]})

    verifier = ClerkVerifier("https://clerk.example.com/jwks", http_client=make_mock_client(handler))
    token = jwt.encode(
        {"email": "clerk-user@example.com"},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid-1"},
    )

    claims = await verifier.verify(token)
    assert claims["email"] == "clerk-user@example.com"


async def test_verify_raises_for_unknown_kid(rsa_keypair, jwk):
    private_key, _ = rsa_keypair

    def handler(request):
        return httpx.Response(200, json={"keys": [jwk]})

    verifier = ClerkVerifier("https://clerk.example.com/jwks", http_client=make_mock_client(handler))
    token = jwt.encode(
        {"email": "clerk-user@example.com"},
        private_key,
        algorithm="RS256",
        headers={"kid": "no-such-kid"},
    )

    with pytest.raises(jwt.InvalidTokenError):
        await verifier.verify(token)
