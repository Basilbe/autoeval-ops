"""Runs all evaluators concurrently against one or many test cases."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Any

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult
from autoeval_ops.observability.telemetry import get_tracer


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
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("evaluate_case") as span:
            span.set_attribute("evaluator.count", len(self.evaluators))

            async def _run_traced(evaluator: Evaluator):
                with tracer.start_as_current_span(f"evaluator.{evaluator.name}") as ev_span:
                    result = await evaluator.evaluate(output, **kwargs)
                    ev_span.set_attribute("metric.name", result.metric_name)
                    ev_span.set_attribute("metric.value", result.metric_value)
                    ev_span.set_attribute("metric.status", result.status)
                    return result

            results = await asyncio.gather(*[_run_traced(ev) for ev in self.evaluators])
            report = EvaluationReport(results=list(results))
            span.set_attribute("overall.status", report.overall_status)
            return report

    async def evaluate_batch(
        self, cases: list[dict[str, Any]], max_concurrency: int = 10
    ) -> list[EvaluationReport]:
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run(case: dict[str, Any]) -> EvaluationReport:
            async with semaphore:
                output = case.pop("output")
                return await self.evaluate_case(output, **case)

        return await asyncio.gather(*[_run(dict(c)) for c in cases])