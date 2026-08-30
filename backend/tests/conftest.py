"""Ensures the src package is importable even without an editable install.

Also hosts db_session at the root so it's visible to every test package
(tests/db/, tests/api/, ...) - a conftest.py fixture is only visible within
its own directory subtree, and integration tests now live in more than one
of those subtrees.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autoeval_ops.config import settings


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Each test runs inside a transaction that is rolled back afterwards,
    so tests never leave rows behind and can run in any order against the
    same database."""
    engine = create_async_engine(settings.database_url, poolclass=None)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(bind=connection, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


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