"""Runs all evaluators concurrently against one or many test cases."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


@dataclass
class EvaluationReport:
    results: list[EvaluationResult] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        if any(r.status == "fail" for r in self.results):
            return "fail"
        if any(r.status == "warning" for r in self.results):
            return "warning"
        return "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "results": [
                {
                    "metric_name": r.metric_name,
                    "metric_value": r.metric_value,
                    "status": r.status,
                    "details": r.details,
                }
                for r in self.results
            ],
        }


class EvaluationPipeline:
    def __init__(self, evaluators: list[Evaluator]):
        self.evaluators = evaluators

    async def evaluate_case(self, output: str, **kwargs: Any) -> EvaluationReport:
        tasks = [ev.evaluate(output, **kwargs) for ev in self.evaluators]
        results = await asyncio.gather(*tasks)
        return EvaluationReport(results=list(results))

    async def evaluate_batch(
        self, cases: list[dict[str, Any]], max_concurrency: int = 10
    ) -> list[EvaluationReport]:
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run(case: dict[str, Any]) -> EvaluationReport:
            async with semaphore:
                output = case.pop("output")
                return await self.evaluate_case(output, **case)

        return await asyncio.gather(*[_run(dict(c)) for c in cases])