"""LLM-as-judge correctness evaluator."""
from __future__ import annotations
from typing import Protocol

from autoeval_ops.core.evaluator import Evaluator, EvaluationResult


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class CorrectnessEvaluator(Evaluator):
    name = "correctness"

    def __init__(self, llm_client: LLMClient, pass_threshold: float = 70.0):
        self.llm_client = llm_client
        self.pass_threshold = pass_threshold

    async def evaluate(self, output: str, expected: str = "", **kwargs) -> EvaluationResult:
        if not output.strip():
            return EvaluationResult(self.name, 0.0, "fail", {"reason": "empty output"})

        judge_prompt = (
            "You are grading an AI answer against a reference answer.\n"
            f"Reference: {expected}\n"
            f"Candidate: {output}\n"
            "Score the candidate's correctness from 0 to 100. "
            "Respond with only the number."
        )
        raw = await self.llm_client.complete(judge_prompt)
        try:
            score = float(raw.strip())
        except ValueError:
            score = 0.0
        score = max(0.0, min(100.0, score))
        status = "pass" if score >= self.pass_threshold else "fail"
        return EvaluationResult(self.name, score, status, {"raw_judge_response": raw})