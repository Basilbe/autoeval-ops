"""GitHub App authentication: signs a JWT with the App's private key, then
exchanges it for a short-lived installation access token, caching until
shortly before expiry."""
from __future__ import annotations
import time
from datetime import datetime

import httpx
import jwt


class GitHubAppAuth:
    def __init__(self, app_id: str, private_key: str, http_client: httpx.AsyncClient | None = None):
        self.app_id = app_id
        self.private_key = private_key
        self._http = http_client or httpx.AsyncClient()
        self._tokens: dict[int, tuple[str, float]] = {}

    def generate_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + (9 * 60), "iss": self.app_id}
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached and cached[1] > time.time() + 30:
            return cached[0]

        token_jwt = self.generate_jwt()
        resp = await self._http.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {token_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
        self._tokens[installation_id] = (data["token"], expires_at)
        return data["token"]