import json
import argparse

from autoeval_ops.core.cli import build_pipeline, run_evaluate, EchoLLMClient, NullToxicityScorer


def test_build_pipeline_uses_echo_client_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    pipeline = build_pipeline("gpt-4")
    correctness_evaluator = pipeline.evaluators[0]
    assert isinstance(correctness_evaluator.llm_client, EchoLLMClient)


def test_build_pipeline_falls_back_to_null_toxicity_scorer(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    pipeline = build_pipeline("gpt-4")
    toxicity_evaluator = pipeline.evaluators[1]
    assert isinstance(toxicity_evaluator.scorer, NullToxicityScorer)


def test_build_pipeline_returns_five_evaluators():
    pipeline = build_pipeline("gpt-4")
    assert len(pipeline.evaluators) == 5


async def test_echo_llm_client_always_returns_fixed_score():
    client = EchoLLMClient()
    result = await client.complete("any prompt")
    assert result == "50"


def test_null_toxicity_scorer_always_returns_zero():
    scorer = NullToxicityScorer()
    assert scorer.score("any text") == 0.0


async def test_run_evaluate_prints_results_for_single_case(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    test_cases_file = tmp_path / "cases.json"
    test_cases_file.write_text(json.dumps([
        {
            "output": "Paris is the capital of France.",
            "expected": "Paris",
            "context": "Paris is the capital of France.",
            "latency_ms": 100,
        }
    ]))
    args = argparse.Namespace(
        prompt="Summarize: {text}", model="gpt-4", test_cases=str(test_cases_file)
    )
    await run_evaluate(args)
    captured = capsys.readouterr()
    assert "Test case 1" in captured.out
    assert "correctness" in captured.out
    assert "toxicity" in captured.out


async def test_run_evaluate_handles_multiple_cases(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    test_cases_file = tmp_path / "cases.json"
    test_cases_file.write_text(json.dumps([
        {"output": "First output", "expected": "ref one"},
        {"output": "Second output", "expected": "ref two"},
    ]))
    args = argparse.Namespace(
        prompt="Summarize: {text}", model="gpt-4", test_cases=str(test_cases_file)
    )
    await run_evaluate(args)
    captured = capsys.readouterr()
    assert "Test case 1" in captured.out
    assert "Test case 2" in captured.out


async def test_run_evaluate_uses_defaults_for_missing_optional_fields(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    test_cases_file = tmp_path / "cases.json"
    # only "output" provided — expected/context/latency_ms must default cleanly
    test_cases_file.write_text(json.dumps([{"output": "minimal case"}]))
    args = argparse.Namespace(
        prompt="Summarize: {text}", model="gpt-4", test_cases=str(test_cases_file)
    )
    await run_evaluate(args)
    captured = capsys.readouterr()
    assert "Test case 1" in captured.out
