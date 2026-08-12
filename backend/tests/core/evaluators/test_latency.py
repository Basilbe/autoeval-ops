from autoeval_ops.core.evaluators.latency import LatencyEvaluator


async def test_latency_within_sla_passes():
    ev = LatencyEvaluator(max_latency_ms=1000)
    result = await ev.evaluate("output", latency_ms=250)
    assert result.status == "pass"


async def test_latency_over_sla_fails():
    ev = LatencyEvaluator(max_latency_ms=1000)
    result = await ev.evaluate("output", latency_ms=5000)
    assert result.status == "fail"


async def test_latency_exactly_at_sla_passes():
    ev = LatencyEvaluator(max_latency_ms=1000)
    result = await ev.evaluate("output", latency_ms=1000)
    assert result.status == "pass"


async def test_latency_default_zero_passes():
    ev = LatencyEvaluator()
    result = await ev.evaluate("output")
    assert result.status == "pass"


async def test_latency_reports_max_in_details():
    ev = LatencyEvaluator(max_latency_ms=1500)
    result = await ev.evaluate("output", latency_ms=100)
    assert result.details["max_latency_ms"] == 1500