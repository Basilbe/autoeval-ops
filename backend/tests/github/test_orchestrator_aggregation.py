from autoeval_ops.core.evaluator import EvaluationResult
from autoeval_ops.core.pipeline import EvaluationReport
from autoeval_ops.github.orchestrator import aggregate_reports


def _report(correctness_value: float, correctness_status: str) -> EvaluationReport:
    return EvaluationReport(
        results=[
            EvaluationResult("correctness", correctness_value, correctness_status),
            EvaluationResult("toxicity", 0.0, "pass"),
        ]
    )


def test_aggregate_overall_pass_when_all_pass():
    overall, _, _ = aggregate_reports([_report(90, "pass"), _report(80, "pass")])
    assert overall == "pass"


def test_aggregate_overall_fail_if_any_case_fails():
    overall, _, _ = aggregate_reports([_report(90, "pass"), _report(10, "fail")])
    assert overall == "fail"


def test_aggregate_averages_metric_values_across_cases():
    _, _, metric_rows = aggregate_reports([_report(100, "pass"), _report(50, "pass")])
    correctness = next(r for r in metric_rows if r["metric_name"] == "correctness")
    assert correctness["metric_value"] == 75.0


def test_aggregate_metric_marked_failed_if_failed_in_any_case():
    _, _, metric_rows = aggregate_reports([_report(100, "pass"), _report(10, "fail")])
    correctness = next(r for r in metric_rows if r["metric_name"] == "correctness")
    assert correctness["status"] == "fail"


def test_aggregate_results_json_contains_every_case():
    _, results_json, _ = aggregate_reports([_report(90, "pass"), _report(80, "pass")])
    assert len(results_json["cases"]) == 2


def test_aggregate_records_case_count_in_details():
    _, _, metric_rows = aggregate_reports([_report(90, "pass"), _report(80, "pass")])
    assert metric_rows[0]["details"]["case_count"] == 2