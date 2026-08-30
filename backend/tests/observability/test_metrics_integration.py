"""Metrics aggregation against real Postgres.
Run with: pytest -m integration   (requires docker-compose up -d)
"""
from __future__ import annotations

import pytest

from autoeval_ops.db import repository
from autoeval_ops.observability.metrics import collect_status_metrics

pytestmark = pytest.mark.integration


async def test_metrics_on_empty_slice_do_not_error(db_session):
    metrics = await collect_status_metrics(db_session)
    assert metrics.total_evaluations >= 0
    assert metrics.latency_p95_ms >= 0.0


async def test_metrics_count_a_created_evaluation(db_session, sample_project):
    before = await collect_status_metrics(db_session)
    await repository.create_evaluation(
        db_session,
        project_id=sample_project.id,
        commit_hash="c" * 40,
        prompt_version="prompts/x.txt",
        model_name="gpt-4",
        test_cases_count=1,
    )
    after = await collect_status_metrics(db_session)
    assert after.total_evaluations == before.total_evaluations + 1


async def test_trace_row_feeds_latency_and_cost(db_session, sample_project):
    evaluation = await repository.create_evaluation(
        db_session,
        project_id=sample_project.id,
        commit_hash="d" * 40,
        prompt_version="prompts/x.txt",
        model_name="gpt-4",
        test_cases_count=1,
    )
    await repository.create_trace(
        db_session,
        eval_id=evaluation.id,
        trace_data={"model": "gpt-4"},
        latency_ms=250,
        cost_usd=0.0012,
    )
    metrics = await collect_status_metrics(db_session)
    assert metrics.latency_p50_ms > 0
    assert metrics.total_cost_usd > 0