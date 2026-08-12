from autoeval_ops.core.evaluator import EvaluationResult
from autoeval_ops.core.pipeline import EvaluationReport
from autoeval_ops.github.comment import format_comment


def _report(status: str) -> EvaluationReport:
    return EvaluationReport(
        results=[
            EvaluationResult("correctness", 90.0, status),
            EvaluationResult("toxicity", 5.0, "pass"),
            EvaluationResult("hallucination", 80.0, "pass"),
            EvaluationResult("cost", 0.001, "pass"),
            EvaluationResult("latency", 200.0, "pass"),
        ]
    )


def test_format_comment_includes_prompt_name():
    body = format_comment("prompts/summarize.txt", [_report("pass")])
    assert "prompts/summarize.txt" in body


def test_format_comment_overall_pass_when_all_pass():
    body = format_comment("p", [_report("pass"), _report("pass")])
    assert "PASS" in body


def test_format_comment_overall_fail_if_any_case_fails():
    body = format_comment("p", [_report("pass"), _report("fail")])
    assert "FAIL" in body


def test_format_comment_includes_one_row_per_case():
    body = format_comment("p", [_report("pass"), _report("pass"), _report("pass")])
    table_rows = [line for line in body.splitlines() if line.startswith("|")]
    assert len(table_rows) == 5  # header + separator + 3 data rows