"""Integration tests against real Postgres. Each test rolls back afterwards.

Run with: pytest -m integration   (requires docker-compose up -d)
"""
from __future__ import annotations
import uuid

import pytest

from autoeval_ops.db import repository

pytestmark = pytest.mark.integration


async def test_create_and_fetch_user(db_session):
    user = await repository.create_user(
        db_session, email=f"{uuid.uuid4()}@example.com", api_key_hash="hashed"
    )
    fetched = await repository.get_user_by_email(db_session, user.email)
    assert fetched is not None
    assert fetched.id == user.id


async def test_project_lookup_by_repo_is_case_insensitive(db_session, sample_project):
    found = await repository.get_project_by_repo(db_session, "Fixture-Owner", "Fixture-Repo")
    assert found is not None
    assert found.id == sample_project.id


async def test_project_lookup_returns_none_for_unregistered_repo(db_session):
    assert await repository.get_project_by_repo(db_session, "nobody", "nothing") is None


async def test_create_and_complete_evaluation(db_session, sample_project):
    evaluation = await repository.create_evaluation(
        db_session,
        project_id=sample_project.id,
        commit_hash="a" * 40,
        prompt_version="prompts/summarize.txt",
        model_name="gpt-4",
        test_cases_count=2,
    )
    assert evaluation.status == "pending"

    await repository.complete_evaluation(
        db_session,
        evaluation,
        status="pass",
        results_json={"cases": []},
        metric_rows=[
            {"metric_name": "correctness", "metric_value": 90.0, "status": "pass", "details": {}}
        ],
    )
    detail = await repository.get_evaluation_detail(db_session, evaluation.id)
    assert detail.status == "pass"
    assert detail.completed_at is not None
    assert len(detail.results) == 1


async def test_list_evaluations_newest_first(db_session, sample_project):
    for i in range(3):
        await repository.create_evaluation(
            db_session,
            project_id=sample_project.id,
            commit_hash=str(i) * 40,
            prompt_version="p",
            model_name="gpt-4",
            test_cases_count=1,
        )
    evaluations = await repository.list_evaluations_for_project(db_session, sample_project.id)
    assert len(evaluations) == 3


async def test_user_owns_project_returns_false_for_other_user(db_session, sample_project):
    other = await repository.create_user(
        db_session, email=f"{uuid.uuid4()}@example.com", api_key_hash="x"
    )
    assert await repository.user_owns_project(db_session, other.id, sample_project.id) is False


async def test_fail_evaluation_records_reason(db_session, sample_project):
    evaluation = await repository.create_evaluation(
        db_session,
        project_id=sample_project.id,
        commit_hash="b" * 40,
        prompt_version="p",
        model_name="gpt-4",
        test_cases_count=1,
    )
    await repository.fail_evaluation(db_session, evaluation, "boom")
    assert evaluation.status == "failed"
    assert evaluation.results_json["error"] == "boom"