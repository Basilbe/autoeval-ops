"""Integration-test fixtures built on top of the db_session fixture in the
root tests/conftest.py (kept there, not here, so tests/api/ can use it too)."""
from __future__ import annotations

import pytest_asyncio


@pytest_asyncio.fixture
async def sample_user(db_session):
    from autoeval_ops.db import repository
    from autoeval_ops.api.security import generate_api_key, hash_api_key

    raw_key = generate_api_key()
    user = await repository.create_user(
        db_session, email="fixture@example.com", api_key_hash=hash_api_key(raw_key)
    )
    return user, raw_key


@pytest_asyncio.fixture
async def sample_project(db_session, sample_user):
    from autoeval_ops.db import repository

    user, _ = sample_user
    org = await repository.create_organization(db_session, user_id=user.id, name="Fixture Org")
    project = await repository.create_project(
        db_session,
        org_id=org.id,
        name="Fixture Project",
        github_repo_url="https://github.com/fixture-owner/fixture-repo",
    )
    return project