"""MVP hallucination check via lexical overlap with provided context.

Upgrade path: once a vector store is available, swap this scoring logic
for embedding similarity without changing the Evaluator interface.
"""
from __future__ import annotations
import re

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class HallucinationEvaluator(Evaluator):
    name = "hallucination"

    def __init__(self, min_overlap: float = 0.3):
        self.min_overlap = min_overlap

    async def evaluate(self, output: str, context: str = "", **kwargs) -> EvaluationResult:
        if not output.strip():
            return EvaluationResult(self.name, 0.0, "pass", {"reason": "empty output"})
        if not context.strip():
            return EvaluationResult(
                self.name, 0.0, "warning", {"reason": "no context provided to check against"}
            )

        output_tokens = _tokenize(output)
        context_tokens = _tokenize(context)
        if not output_tokens:
            return EvaluationResult(self.name, 0.0, "pass", {})

        grounded = output_tokens & context_tokens
        overlap_ratio = len(grounded) / len(output_tokens)
        score = overlap_ratio * 100
        status = "pass" if overlap_ratio >= self.min_overlap else "fail"
        return EvaluationResult(self.name, score, status, {"overlap_ratio": overlap_ratio})