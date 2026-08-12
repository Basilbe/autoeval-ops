"""Wires together GitHub API access, prompt execution, and evaluation for a
single PR job, then posts the results as a PR comment.

Convention: a prompt file at prompts/<name>.txt is evaluated against test
cases at eval/<name>.test_cases.json in the same repo/ref.
"""
from __future__ import annotations
import json

from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.client import GitHubClient
from autoeval_ops.github.queue import EvalJob
from autoeval_ops.github.runner import PromptRunner
from autoeval_ops.github.comment import format_comment
from autoeval_ops.core.llm_client import build_llm_client
from autoeval_ops.core.pipeline import EvaluationPipeline
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator, NullToxicityScorer
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator

PROMPT_DIR_PREFIX = "prompts/"
PROMPT_SUFFIX = ".txt"


def is_prompt_file(path: str) -> bool:
    return path.startswith(PROMPT_DIR_PREFIX) and path.endswith(PROMPT_SUFFIX)


def resolve_test_cases_path(prompt_path: str) -> str:
    return prompt_path.replace("prompts/", "eval/", 1).replace(".txt", ".test_cases.json")


def build_default_pipeline(model: str, llm_client) -> EvaluationPipeline:
    return EvaluationPipeline(
        [
            CorrectnessEvaluator(llm_client),
            ToxicityEvaluator(NullToxicityScorer()),
            HallucinationEvaluator(),
            CostEvaluator(model=model),
            LatencyEvaluator(),
        ]
    )


async def handle_eval_job(
    job: EvalJob,
    app_auth: GitHubAppAuth,
    model: str = "gpt-4",
    client_factory=GitHubClient,
) -> None:
    token = await app_auth.get_installation_token(job.installation_id)
    gh = client_factory(token)

    files = await gh.get_pr_files(job.owner, job.repo, job.pr_number)
    prompt_files = [f["filename"] for f in files if is_prompt_file(f["filename"])]
    if not prompt_files:
        return

    llm_client = build_llm_client(model)
    runner = PromptRunner(llm_client)

    for prompt_path in prompt_files:
        prompt_text = await gh.get_file_content(job.owner, job.repo, prompt_path, job.head_sha)

        tc_path = resolve_test_cases_path(prompt_path)
        try:
            test_cases_raw = await gh.get_file_content(job.owner, job.repo, tc_path, job.head_sha)
        except Exception:
            continue  # no matching test suite for this prompt, skip

        test_cases = json.loads(test_cases_raw)
        prepared_cases = await runner.run(prompt_text, test_cases)

        pipeline = build_default_pipeline(model, llm_client)
        reports = await pipeline.evaluate_batch([dict(c) for c in prepared_cases])

        comment_body = format_comment(prompt_path, reports)
        await gh.post_pr_comment(job.owner, job.repo, job.pr_number, comment_body)