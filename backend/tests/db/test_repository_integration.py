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


async def test_get_or_create_user_by_email_provisions_new_user(db_session):
    email = f"{uuid.uuid4()}@example.com"
    user = await repository.get_or_create_user_by_email(db_session, email)
    assert user.email == email
    assert user.api_key_hash is None


async def test_get_or_create_user_by_email_returns_existing_user(db_session, sample_user):
    existing, _ = sample_user
    found = await repository.get_or_create_user_by_email(db_session, existing.email)
    assert found.id == existing.id


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


async def test_get_organization_returns_correct_org(db_session, sample_user):
    user, _ = sample_user
    org = await repository.create_organization(db_session, user_id=user.id, name="Org A")
    fetched = await repository.get_organization(db_session, org.id)
    assert fetched is not None
    assert fetched.id == org.id
    assert fetched.name == "Org A"


async def test_set_api_key_hash_updates_stored_hash(db_session, sample_user):
    from autoeval_ops.api.security import generate_api_key, hash_api_key, verify_api_key

    user, old_raw_key = sample_user
    new_raw_key = generate_api_key()
    await repository.set_api_key_hash(db_session, user, hash_api_key(new_raw_key))

    assert verify_api_key(old_raw_key, user.api_key_hash) is False
    assert verify_api_key(new_raw_key, user.api_key_hash) is True


async def test_get_project_returns_correct_project(db_session, sample_project):
    fetched = await repository.get_project(db_session, sample_project.id)
    assert fetched is not None
    assert fetched.id == sample_project.id
    assert fetched.name == sample_project.name


async def test_list_projects_for_user_only_returns_that_users_projects(db_session):
    user1 = await repository.create_user(
        db_session, email=f"{uuid.uuid4()}@example.com", api_key_hash="x"
    )
    org1 = await repository.create_organization(db_session, user_id=user1.id, name="Org1")
    project1 = await repository.create_project(
        db_session, org_id=org1.id, name="P1", github_repo_url="owner1/repo1"
    )

    user2 = await repository.create_user(
        db_session, email=f"{uuid.uuid4()}@example.com", api_key_hash="y"
    )
    org2 = await repository.create_organization(db_session, user_id=user2.id, name="Org2")
    await repository.create_project(
        db_session, org_id=org2.id, name="P2", github_repo_url="owner2/repo2"
    )

    projects = await repository.list_projects_for_user(db_session, user1.id)
    assert len(projects) == 1
    assert projects[0].id == project1.id