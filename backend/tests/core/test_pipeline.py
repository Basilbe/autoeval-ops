import asyncio

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult
from autoeval_ops.core.pipeline import EvaluationPipeline


class FixedEvaluator(Evaluator):
    def __init__(self, name, status, value=1.0):
        self.name = name
        self._status = status
        self._value = value

    async def evaluate(self, output, **kwargs):
        return EvaluationResult(self.name, self._value, self._status)


class ConcurrencyTrackingEvaluator(Evaluator):
    name = "tracker"
    active = 0
    max_active = 0

    async def evaluate(self, output, **kwargs):
        type(self).active += 1
        type(self).max_active = max(type(self).max_active, type(self).active)
        await asyncio.sleep(0.01)
        type(self).active -= 1
        return EvaluationResult(self.name, 1.0, "pass")


async def test_pipeline_runs_all_evaluators_in_parallel():
    evaluators = [FixedEvaluator("a", "pass"), FixedEvaluator("b", "pass")]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("some output")
    assert len(report.results) == 2


async def test_pipeline_overall_status_fail_if_any_fails():
    evaluators = [FixedEvaluator("a", "pass"), FixedEvaluator("b", "fail")]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("some output")
    assert report.overall_status == "fail"


async def test_pipeline_overall_status_warning_when_no_failures():
    evaluators = [FixedEvaluator("a", "pass"), FixedEvaluator("b", "warning")]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("some output")
    assert report.overall_status == "warning"


async def test_pipeline_batch_respects_max_concurrency():
    ConcurrencyTrackingEvaluator.active = 0
    ConcurrencyTrackingEvaluator.max_active = 0
    pipeline = EvaluationPipeline([ConcurrencyTrackingEvaluator()])
    cases = [{"output": f"case {i}"} for i in range(20)]
    await pipeline.evaluate_batch(cases, max_concurrency=5)
    assert ConcurrencyTrackingEvaluator.max_active <= 5


async def test_pipeline_as_dict_serializes_cleanly():
    evaluators = [FixedEvaluator("a", "pass", value=42.0)]
    pipeline = EvaluationPipeline(evaluators)
    report = await pipeline.evaluate_case("output")
    data = report.as_dict()
    assert data["results"][0]["metric_value"] == 42.0