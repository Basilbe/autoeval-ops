"""
Benchmarks the evaluation pipeline at 10, 100, and 1000 parallel cases.
Run with: python scripts/benchmark.py
"""
from __future__ import annotations
import asyncio
import time

from autoeval_ops.core.pipeline import EvaluationPipeline
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator


class FakeLLMClient:
    async def complete(self, prompt: str) -> str:
        await asyncio.sleep(0.01)  # simulate small network latency
        return "80"


class FakeToxicityScorer:
    def score(self, text: str) -> float:
        return 0.05


def build_pipeline() -> EvaluationPipeline:
    return EvaluationPipeline(
        [
            CorrectnessEvaluator(FakeLLMClient()),
            ToxicityEvaluator(FakeToxicityScorer()),
            HallucinationEvaluator(),
            CostEvaluator(model="gpt-4"),
            LatencyEvaluator(),
        ]
    )


async def run_n(n: int, max_concurrency: int) -> float:
    pipeline = build_pipeline()
    cases = [
        {
            "output": f"This is test output number {i}",
            "expected": "reference answer",
            "context": "This is test output number context",
            "prompt": "Summarize: {text}",
            "latency_ms": 120.0,
        }
        for i in range(n)
    ]
    start = time.perf_counter()
    await pipeline.evaluate_batch(cases, max_concurrency=max_concurrency)
    return (time.perf_counter() - start) * 1000


async def main() -> None:
    print("Benchmarking EvaluationPipeline (fake clients, no real network calls)\n")
    results = {}
    for n in (10, 100, 1000):
        elapsed_ms = await run_n(n, max_concurrency=10)
        results[n] = elapsed_ms
        print(f"{n:5d} parallel evals: {elapsed_ms:8.1f} ms  ({elapsed_ms / n:6.2f} ms/eval)")

    with open("BENCHMARK.md", "w") as f:
        f.write("# Phase 1 Benchmark Results\n\n")
        f.write("Measured with fake LLM/toxicity clients (simulated 10ms latency), max_concurrency=10.\n\n")
        f.write("| Parallel Evals | Total Time (ms) | ms/eval |\n")
        f.write("|---|---|---|\n")
        for n, ms in results.items():
            f.write(f"| {n} | {ms:.1f} | {ms / n:.2f} |\n")
    print("\nWrote BENCHMARK.md")


if __name__ == "__main__":
    asyncio.run(main())