"""Clerk session-token verification via JWKS.

Cannot be verified against a real Clerk login until Phase 4's dashboard
exists to produce real session tokens - Phase 3 tests this against a
mocked JWKS endpoint.
"""
from __future__ import annotations
import time

import httpx
import jwt
from jwt import PyJWKClient


class ClerkVerifier:
    def __init__(self, jwks_url: str, http_client: httpx.AsyncClient | None = None):
        self.jwks_url = jwks_url
        self._http = http_client
        self._jwks_cache: dict | None = None
        self._jwks_fetched_at: float = 0.0
        self._cache_ttl_seconds = 3600

    async def _get_jwks(self) -> dict:
        now = time.time()
        if self._jwks_cache and (now - self._jwks_fetched_at) < self._cache_ttl_seconds:
            return self._jwks_cache
        client = self._http or httpx.AsyncClient()
        resp = await client.get(self.jwks_url)
        resp.raise_for_status()
        self._jwks_cache = resp.json()
        self._jwks_fetched_at = now
        return self._jwks_cache

    async def verify(self, token: str) -> dict:
        """Returns the decoded claims, or raises jwt.PyJWTError."""
        jwks = await self._get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            raise jwt.InvalidTokenError("No matching key in JWKS")
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        return jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})