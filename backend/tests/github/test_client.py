"""Tests for GitHubClient. Uses httpx.MockTransport - no real network calls."""
from __future__ import annotations
import base64

import httpx
import pytest

from autoeval_ops.github.client import GitHubClient


def make_client(handler) -> GitHubClient:
    transport = httpx.MockTransport(handler)
    return GitHubClient(token="fake-token", http_client=httpx.AsyncClient(transport=transport))


async def test_get_pr_files_returns_filenames():
    def handler(request):
        assert request.headers["authorization"] == "Bearer fake-token"
        return httpx.Response(200, json=[{"filename": "prompts/summarize.txt"}])

    client = make_client(handler)
    files = await client.get_pr_files("owner", "repo", 1)
    assert files[0]["filename"] == "prompts/summarize.txt"


async def test_get_file_content_decodes_base64():
    encoded = base64.b64encode(b"Summarize: {text}").decode()

    def handler(request):
        return httpx.Response(200, json={"content": encoded})

    client = make_client(handler)
    content = await client.get_file_content("owner", "repo", "prompts/summarize.txt", "main")
    assert content == "Summarize: {text}"


async def test_post_pr_comment_sends_body():
    captured = {}

    def handler(request):
        captured["body"] = request.content
        return httpx.Response(201, json={"id": 1})

    client = make_client(handler)
    await client.post_pr_comment("owner", "repo", 1, "hello world")
    assert b"hello world" in captured["body"]


async def test_get_pr_files_raises_on_http_error():
    def handler(request):
        return httpx.Response(404, json={"message": "Not Found"})

    client = make_client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_pr_files("owner", "repo", 999)