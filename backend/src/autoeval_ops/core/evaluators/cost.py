"""Cost evaluator: estimates spend from prompt+output length and model pricing."""
from __future__ import annotations

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult

# USD per 1K tokens, blended input+output estimate. Update as pricing changes.
MODEL_PRICING = {
    "gpt-4": 0.03,
    "gpt-4o": 0.005,
    "gpt-3.5-turbo": 0.0015,
}
DEFAULT_PRICE_PER_1K = 0.01


def _estimate_tokens(text: str) -> int:
    # ~4 characters per token (OpenAI's rule of thumb). Avoids a tiktoken
    # dependency for Phase 1; revisit if precise counts become necessary.
    return max(1, len(text) // 4)


class CostEvaluator(Evaluator):
    name = "cost"

    def __init__(self, model: str, max_cost_usd: float = 0.05):
        self.model = model
        self.max_cost_usd = max_cost_usd

    async def evaluate(self, output: str, prompt: str = "", **kwargs) -> EvaluationResult:
        tokens = _estimate_tokens(prompt) + _estimate_tokens(output)
        price_per_1k = MODEL_PRICING.get(self.model, DEFAULT_PRICE_PER_1K)
        cost_usd = (tokens / 1000) * price_per_1k
        status = "pass" if cost_usd <= self.max_cost_usd else "fail"
        return EvaluationResult(
            self.name, cost_usd, status, {"estimated_tokens": tokens, "model": self.model}
        )