from autoeval_ops.core.evaluators.cost import CostEvaluator, _estimate_tokens


async def test_cost_within_budget_passes():
    ev = CostEvaluator(model="gpt-3.5-turbo", max_cost_usd=1.0)
    result = await ev.evaluate("short output", prompt="short prompt")
    assert result.status == "pass"


async def test_cost_over_budget_fails():
    ev = CostEvaluator(model="gpt-4", max_cost_usd=0.00001)
    result = await ev.evaluate("a" * 2000, prompt="a" * 2000)
    assert result.status == "fail"


async def test_cost_unknown_model_uses_default_pricing():
    ev = CostEvaluator(model="some-unlisted-model", max_cost_usd=1.0)
    result = await ev.evaluate("output text", prompt="prompt text")
    assert result.details["model"] == "some-unlisted-model"


def test_estimate_tokens_roughly_matches_character_count():
    assert _estimate_tokens("a" * 400) == 100


def test_estimate_tokens_minimum_is_one():
    assert _estimate_tokens("") == 1