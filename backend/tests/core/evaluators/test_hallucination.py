from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator


async def test_hallucination_grounded_output_passes():
    ev = HallucinationEvaluator(min_overlap=0.3)
    context = "The Eiffel Tower is located in Paris France and was completed in 1889"
    output = "The Eiffel Tower is in Paris"
    result = await ev.evaluate(output, context=context)
    assert result.status == "pass"


async def test_hallucination_ungrounded_output_fails():
    ev = HallucinationEvaluator(min_overlap=0.5)
    context = "The Eiffel Tower is in Paris"
    output = "Dinosaurs invented the telephone in 1200 BC"
    result = await ev.evaluate(output, context=context)
    assert result.status == "fail"


async def test_hallucination_no_context_returns_warning():
    ev = HallucinationEvaluator()
    result = await ev.evaluate("some output", context="")
    assert result.status == "warning"


async def test_hallucination_empty_output_passes():
    ev = HallucinationEvaluator()
    result = await ev.evaluate("", context="some context")
    assert result.status == "pass"


async def test_hallucination_case_insensitive_matching():
    ev = HallucinationEvaluator(min_overlap=0.5)
    context = "PARIS is a CITY"
    output = "paris is a city"
    result = await ev.evaluate(output, context=context)
    assert result.status == "pass"