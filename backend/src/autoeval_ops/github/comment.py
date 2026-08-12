"""Formats an evaluation run into a Markdown PR comment."""
from __future__ import annotations

from autoeval_ops.core.pipeline import EvaluationReport

_ICON = {"pass": "PASS", "fail": "FAIL", "warning": "WARN"}


def _overall(reports: list[EvaluationReport]) -> str:
    if any(r.overall_status == "fail" for r in reports):
        return "fail"
    if any(r.overall_status == "warning" for r in reports):
        return "warning"
    return "pass"


def format_comment(prompt_name: str, reports: list[EvaluationReport]) -> str:
    overall = _overall(reports)
    lines = [
        f"## AutoEvalOps Report -- `{prompt_name}`",
        "",
        f"**Overall: {_ICON[overall]}** ({len(reports)} test case(s))",
        "",
        "| Case | Status | Correctness | Toxicity | Hallucination | Cost ($) | Latency (ms) |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, report in enumerate(reports, start=1):
        by_metric = {r.metric_name: r for r in report.results}
        lines.append(
            f"| {i} | {_ICON[report.overall_status]} | "
            f"{by_metric['correctness'].metric_value:.0f} | "
            f"{by_metric['toxicity'].metric_value:.0f} | "
            f"{by_metric['hallucination'].metric_value:.0f} | "
            f"{by_metric['cost'].metric_value:.4f} | "
            f"{by_metric['latency'].metric_value:.0f} |"
        )
    lines.append("")
    lines.append("_Posted automatically by AutoEvalOps._")
    return "\n".join(lines)