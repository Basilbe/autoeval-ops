from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response

    async def complete(self, prompt: str) -> str:
        return self.response


async def test_correctness_high_score_passes():
    ev = CorrectnessEvaluator(FakeLLMClient("95"))
    result = await ev.evaluate("Paris is the capital of France.", expected="Paris")
    assert result.status == "pass"
    assert result.metric_value == 95.0


async def test_correctness_low_score_fails():
    ev = CorrectnessEvaluator(FakeLLMClient("20"))
    result = await ev.evaluate("The moon is made of cheese.", expected="rock")
    assert result.status == "fail"
    assert result.metric_value == 20.0


async def test_correctness_empty_output_fails_without_calling_llm():
    ev = CorrectnessEvaluator(FakeLLMClient("100"))
    result = await ev.evaluate("", expected="anything")
    assert result.status == "fail"
    assert result.metric_value == 0.0


async def test_correctness_handles_non_numeric_judge_response():
    ev = CorrectnessEvaluator(FakeLLMClient("not a number"))
    result = await ev.evaluate("some output", expected="ref")
    assert result.metric_value == 0.0
    assert result.status == "fail"


async def test_correctness_clamps_out_of_range_score():
    ev = CorrectnessEvaluator(FakeLLMClient("150"))
    result = await ev.evaluate("output", expected="ref")
    assert result.metric_value == 100.0