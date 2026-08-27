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