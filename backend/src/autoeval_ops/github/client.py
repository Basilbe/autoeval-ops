"""Thin async GitHub REST API client built on httpx, per TECH_STACK.md's
commitment to httpx for async HTTP. (PyGithub is listed in requirements.txt
but unused, kept in case a future phase wants its higher-level helpers.)"""
from __future__ import annotations
import base64

import httpx


class GitHubClient:
    def __init__(self, token: str, http_client: httpx.AsyncClient | None = None):
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._http = http_client or httpx.AsyncClient()

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=self._headers,
            params={"ref": ref},
        )
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    async def post_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        resp = await self._http.post(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=self._headers,
            json={"body": body},
        )
        resp.raise_for_status()