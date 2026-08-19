"""Wires together GitHub API access, prompt execution, and evaluation for a
single PR job, posts the results as a PR comment, and (Phase 3) persists
each run to Postgres.

Convention: a prompt file at prompts/<name>.txt is evaluated against test
cases at eval/<name>.test_cases.json in the same repo/ref.

Persistence is best-effort and never blocks commenting: if the database is
unreachable, the PR comment must still post.
"""
from __future__ import annotations
import json

from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.client import GitHubClient
from autoeval_ops.github.queue import EvalJob
from autoeval_ops.github.runner import PromptRunner
from autoeval_ops.github.comment import format_comment
from autoeval_ops.core.llm_client import build_llm_client
from autoeval_ops.core.pipeline import EvaluationPipeline, EvaluationReport
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator, NullToxicityScorer
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator
from autoeval_ops.db import repository
from autoeval_ops.db.session import get_session_factory

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


def aggregate_reports(reports: list[EvaluationReport]) -> tuple[str, dict, list[dict]]:
    """Roll per-case reports up into (overall_status, results_json, metric_rows).

    metric_rows averages each metric across cases, and marks a metric failed
    if it failed in any case - one bad case shouldn't be averaged away.
    """
    overall = "pass"
    if any(r.overall_status == "fail" for r in reports):
        overall = "fail"
    elif any(r.overall_status == "warning" for r in reports):
        overall = "warning"

    results_json = {"cases": [r.as_dict() for r in reports]}

    totals: dict[str, list[float]] = {}
    statuses: dict[str, list[str]] = {}
    for report in reports:
        for result in report.results:
            totals.setdefault(result.metric_name, []).append(result.metric_value)
            statuses.setdefault(result.metric_name, []).append(result.status)

    metric_rows = []
    for metric_name, values in totals.items():
        metric_statuses = statuses[metric_name]
        if "fail" in metric_statuses:
            status = "fail"
        elif "warning" in metric_statuses:
            status = "warning"
        else:
            status = "pass"
        metric_rows.append(
            {
                "metric_name": metric_name,
                "metric_value": sum(values) / len(values) if values else 0.0,
                "status": status,
                "details": {"case_count": len(values)},
            }
        )
    return overall, results_json, metric_rows


async def handle_eval_job(
    job: EvalJob,
    app_auth: GitHubAppAuth,
    model: str = "gpt-4",
    client_factory=GitHubClient,
    session_factory=None,
) -> None:
    token = await app_auth.get_installation_token(job.installation_id)
    gh = client_factory(token)

    files = await gh.get_pr_files(job.owner, job.repo, job.pr_number)
    prompt_files = [f["filename"] for f in files if is_prompt_file(f["filename"])]
    if not prompt_files:
        return

    llm_client = build_llm_client(model)
    runner = PromptRunner(llm_client)

    if session_factory is None:
        session_factory = get_session_factory()

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

        # Persist - best effort, never blocks the PR comment below.
        try:
            async with session_factory() as db:
                project = await repository.get_project_by_repo(db, job.owner, job.repo)
                if project is None:
                    print(
                        f"AutoEvalOps: repo {job.owner}/{job.repo} is not a registered "
                        f"project - evaluation not persisted. Register it via "
                        f"POST /api/v1/projects to enable history."
                    )
                else:
                    evaluation = await repository.create_evaluation(
                        db,
                        project_id=project.id,
                        commit_hash=job.head_sha,
                        prompt_version=prompt_path,
                        model_name=model,
                        test_cases_count=len(test_cases),
                    )
                    overall, results_json, metric_rows = aggregate_reports(reports)
                    await repository.complete_evaluation(
                        db,
                        evaluation,
                        status=overall,
                        results_json=results_json,
                        metric_rows=metric_rows,
                    )
                    await db.commit()
        except Exception as exc:
            print(f"AutoEvalOps: failed to persist evaluation - {exc}")

        comment_body = format_comment(prompt_path, reports)
        await gh.post_pr_comment(job.owner, job.repo, job.pr_number, comment_body)