"""Tests for the orchestrator. Uses fakes throughout - no real network
calls, no real OpenAI key needed (falls back to EchoLLMClient)."""
from __future__ import annotations
import json

from autoeval_ops.github.orchestrator import handle_eval_job, is_prompt_file, resolve_test_cases_path
from autoeval_ops.github.queue import EvalJob


class FakeAppAuth:
    async def get_installation_token(self, installation_id: int) -> str:
        return "fake-token"


class FakeGitHubClient:
    def __init__(self, token: str, files=None, contents=None):
        self.token = token
        self.files = files or []
        self.contents = contents or {}
        self.posted_comments: list[str] = []

    async def get_pr_files(self, owner, repo, pr_number):
        return self.files

    async def get_file_content(self, owner, repo, path, ref):
        if path not in self.contents:
            raise FileNotFoundError(path)
        return self.contents[path]

    async def post_pr_comment(self, owner, repo, pr_number, body):
        self.posted_comments.append(body)


def _job() -> EvalJob:
    return EvalJob(installation_id=1, owner="bazil", repo="autoeval-ops", pr_number=7, head_sha="abc")


def test_is_prompt_file_matches_convention():
    assert is_prompt_file("prompts/summarize.txt") is True
    assert is_prompt_file("src/main.py") is False
    assert is_prompt_file("prompts/readme.md") is False


def test_test_cases_path_for_derives_matching_path():
    assert resolve_test_cases_path("prompts/summarize.txt") == "eval/summarize.test_cases.json"


async def test_handle_eval_job_skips_prs_with_no_prompt_files():
    client_holder = {}

    def factory(token):
        c = FakeGitHubClient(token, files=[{"filename": "README.md"}])
        client_holder["client"] = c
        return c

    await handle_eval_job(_job(), FakeAppAuth(), client_factory=factory)
    assert client_holder["client"].posted_comments == []


async def test_handle_eval_job_skips_when_no_matching_test_cases_file():
    client_holder = {}

    def factory(token):
        c = FakeGitHubClient(
            token,
            files=[{"filename": "prompts/summarize.txt"}],
            contents={"prompts/summarize.txt": "Summarize: {text}"},
            # no eval/summarize.test_cases.json in contents -> get_file_content raises
        )
        client_holder["client"] = c
        return c

    await handle_eval_job(_job(), FakeAppAuth(), client_factory=factory)
    assert client_holder["client"].posted_comments == []


async def test_handle_eval_job_posts_comment_when_prompt_and_tests_present(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    test_cases = json.dumps([{"input": "hello", "expected": "world", "context": "hello world"}])
    client_holder = {}

    def factory(token):
        c = FakeGitHubClient(
            token,
            files=[{"filename": "prompts/summarize.txt"}],
            contents={
                "prompts/summarize.txt": "Echo: {text}",
                "eval/summarize.test_cases.json": test_cases,
            },
        )
        client_holder["client"] = c
        return c

    await handle_eval_job(_job(), FakeAppAuth(), client_factory=factory)
    assert len(client_holder["client"].posted_comments) == 1
    assert "prompts/summarize.txt" in client_holder["client"].posted_comments[0]