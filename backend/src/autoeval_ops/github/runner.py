"""Runs a prompt template against a set of test cases through a real (or
injected) LLM client, producing outputs shaped for EvaluationPipeline."""
from __future__ import annotations
import time
from typing import Protocol


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...


class PromptRunner:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def run(self, prompt_template: str, test_cases: list[dict]) -> list[dict]:
        prepared = []
        for case in test_cases:
            rendered = prompt_template.format(text=case.get("input", ""))
            start = time.perf_counter()
            output = await self.llm_client.complete(rendered)
            latency_ms = (time.perf_counter() - start) * 1000
            prepared.append(
                {
                    "output": output,
                    "expected": case.get("expected", ""),
                    "context": case.get("context", ""),
                    "prompt": rendered,
                    "latency_ms": latency_ms,
                }
            )
        return prepared