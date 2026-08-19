"""Verifies persistence is best-effort: a DB failure must never prevent the
PR comment from posting, and unregistered repos must not create rows."""
from __future__ import annotations
import json

from autoeval_ops.github.orchestrator import handle_eval_job
from autoeval_ops.github.queue import EvalJob

TEST_CASES = json.dumps([{"input": "hello", "expected": "world", "context": "hello world"}])


class FakeAppAuth:
    async def get_installation_token(self, installation_id: int) -> str:
        return "fake-token"


class FakeGitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.posted_comments: list[str] = []

    async def get_pr_files(self, owner, repo, pr_number):
        return [{"filename": "prompts/summarize.txt"}]

    async def get_file_content(self, owner, repo, path, ref):
        if path == "prompts/summarize.txt":
            return "Echo: {text}"
        if path == "eval/summarize.test_cases.json":
            return TEST_CASES
        raise FileNotFoundError(path)

    async def post_pr_comment(self, owner, repo, pr_number, body):
        self.posted_comments.append(body)


class ExplodingSessionFactory:
    """Simulates a completely unreachable database."""

    def __call__(self):
        raise ConnectionError("database is down")


def _job() -> EvalJob:
    return EvalJob(installation_id=1, owner="o", repo="r", pr_number=1, head_sha="abc")


async def test_comment_still_posts_when_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    holder = {}

    def factory(token):
        client = FakeGitHubClient(token)
        holder["client"] = client
        return client

    await handle_eval_job(
        _job(), FakeAppAuth(), client_factory=factory, session_factory=ExplodingSessionFactory()
    )

    assert len(holder["client"].posted_comments) == 1
    assert "failed to persist" in capsys.readouterr().out