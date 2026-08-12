import pytest

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


def test_evaluator_is_abstract():
    with pytest.raises(TypeError):
        Evaluator()


def test_evaluation_result_defaults():
    result = EvaluationResult(metric_name="x", metric_value=1.0, status="pass")
    assert result.details == {}


async def test_concrete_evaluator_can_be_instantiated_and_run():
    class DummyEvaluator(Evaluator):
        name = "dummy"

        async def evaluate(self, output, **kwargs):
            return EvaluationResult(self.name, 1.0, "pass")

    ev = DummyEvaluator()
    result = await ev.evaluate("hello")
    assert result.status == "pass"