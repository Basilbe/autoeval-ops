"""Percentile maths - pure functions, no database needed."""
from autoeval_ops.observability.metrics import StatusMetrics, _percentile


def test_percentile_of_empty_list_is_zero():
    assert _percentile([], 0.95) == 0.0


def test_percentile_p50_of_simple_range():
    assert _percentile([10.0, 20.0, 30.0, 40.0, 50.0], 0.50) == 30.0


def test_percentile_p99_returns_near_max():
    values = [float(i) for i in range(1, 101)]
    assert _percentile(values, 0.99) >= 99.0


def test_percentile_never_indexes_out_of_range():
    assert _percentile([5.0], 0.99) == 5.0


def test_status_metrics_as_dict_shape():
    metrics = StatusMetrics(total_evaluations=3, pass_rate=0.6667)
    data = metrics.as_dict()
    assert data["total_evaluations"] == 3
    assert data["pass_rate"] == 0.6667
    assert "latency" in data and "cost" in data


def test_status_metrics_defaults_are_zero():
    data = StatusMetrics().as_dict()
    assert data["total_evaluations"] == 0
    assert data["latency"]["p95_ms"] == 0.0