"""
Usage:
  python -m autoeval_ops.core.cli evaluate --prompt "Summarize: {text}" --model gpt-4 --test-cases test_cases.json
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

from autoeval_ops.core.pipeline import EvaluationPipeline
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator, NullToxicityScorer
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator
from autoeval_ops.core.llm_client import build_llm_client, EchoLLMClient  # noqa: F401 (re-exported for tests)


def build_pipeline(model: str) -> EvaluationPipeline:
    llm_client = build_llm_client(model)

    try:
        from autoeval_ops.core.evaluators.toxicity import DetoxifyScorer

        scorer = DetoxifyScorer()
    except Exception:
        print("WARNING: Detoxify unavailable - using placeholder toxicity scorer.", file=sys.stderr)
        scorer = NullToxicityScorer()

    return EvaluationPipeline(
        [
            CorrectnessEvaluator(llm_client),
            ToxicityEvaluator(scorer),
            HallucinationEvaluator(),
            CostEvaluator(model=model),
            LatencyEvaluator(),
        ]
    )


async def run_evaluate(args: argparse.Namespace) -> None:
    test_cases_path = Path(args.test_cases)
    cases = json.loads(test_cases_path.read_text())

    pipeline = build_pipeline(args.model)

    prepared = []
    for case in cases:
        prepared.append(
            {
                "output": case["output"],
                "expected": case.get("expected", ""),
                "context": case.get("context", ""),
                "prompt": args.prompt,
                "latency_ms": case.get("latency_ms", 0.0),
            }
        )

    reports = await pipeline.evaluate_batch(prepared)

    for i, report in enumerate(reports):
        print(f"\n=== Test case {i + 1}: {report.overall_status.upper()} ===")
        for result in report.results:
            print(f"  {result.metric_name:14s} {result.metric_value:8.2f}  [{result.status}]")


def main() -> None:  # pragma: no cover - entrypoint, verified manually
    parser = argparse.ArgumentParser(prog="autoeval-cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate", help="Run the evaluation pipeline against test cases")
    evaluate_parser.add_argument("--prompt", required=True)
    evaluate_parser.add_argument("--model", required=True)
    evaluate_parser.add_argument("--test-cases", required=True)

    args = parser.parse_args()

    if args.command == "evaluate":
        asyncio.run(run_evaluate(args))


if __name__ == "__main__":  # pragma: no cover
    main()