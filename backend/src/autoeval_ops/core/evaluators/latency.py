"""Latency evaluator: validates a pre-measured generation time against an SLA."""
from __future__ import annotations

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


class LatencyEvaluator(Evaluator):
    name = "latency"

    def __init__(self, max_latency_ms: float = 5000.0):
        self.max_latency_ms = max_latency_ms

    async def evaluate(self, output: str, latency_ms: float = 0.0, **kwargs) -> EvaluationResult:
        status = "pass" if latency_ms <= self.max_latency_ms else "fail"
        return EvaluationResult(
            self.name, latency_ms, status, {"max_latency_ms": self.max_latency_ms}
        )