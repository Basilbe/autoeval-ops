from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator


class FakeScorer:
    def __init__(self, value: float):
        self.value = value

    def score(self, text: str) -> float:
        return self.value


async def test_toxicity_clean_text_passes():
    ev = ToxicityEvaluator(FakeScorer(0.05))
    result = await ev.evaluate("Have a wonderful day!")
    assert result.status == "pass"


async def test_toxicity_toxic_text_fails():
    ev = ToxicityEvaluator(FakeScorer(0.9))
    result = await ev.evaluate("some toxic text")
    assert result.status == "fail"


async def test_toxicity_empty_output_passes_without_scoring():
    ev = ToxicityEvaluator(FakeScorer(0.9))
    result = await ev.evaluate("")
    assert result.status == "pass"
    assert result.metric_value == 0.0


async def test_toxicity_boundary_at_threshold_fails():
    ev = ToxicityEvaluator(FakeScorer(0.5), fail_threshold=0.5)
    result = await ev.evaluate("borderline text")
    assert result.status == "fail"


async def test_toxicity_score_converted_to_percentage():
    ev = ToxicityEvaluator(FakeScorer(0.3))
    result = await ev.evaluate("mild text")
    assert result.metric_value == 30.0