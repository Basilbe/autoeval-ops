# Phase 3: Backend API + Database Persistence (PowerShell Edition)

> Every code block is labeled where it goes: **"Run in PowerShell"** or **"Paste into `filename`"**. Same conventions as Phases 0-2.

## Scope Decisions (confirmed before building)

- **Projects must be pre-registered.** A webhook for an unregistered `owner/repo` is logged and ignored — it does not auto-create a `projects` row. Auto-creating records from an unauthenticated webhook would let anyone point a webhook at the server and write to the database.
- **Alembic adopted now.** `schema.sql` stays as a historical artifact but is no longer the mechanism. All schema changes go through migrations from here on — required for Phase 6 deployability.
- **Hybrid testing.** Business logic keeps using fakes (fast, no Docker). A smaller `@pytest.mark.integration` set hits real Postgres, each test wrapped in a transaction that rolls back. Day-to-day you can run just the fast set; the phase gate requires both.
- **Both auth paths built now**, but Clerk's live login flow can only be end-to-end verified in Phase 4 once a dashboard exists. Phase 3 tests Clerk JWT handling against mocked JWKS; API-key auth is fully verifiable now.
- **`server.py` is expanded, not replaced.** It already exists from Phase 2 with the webhook router and lifespan queue startup. Phase 3 adds the API routers, DB session lifecycle, and middleware to it.
- **The orchestrator is retrofitted, not rewritten.** It keeps posting PR comments exactly as it does now; persistence is added alongside that behavior.

---

## Prerequisites

### Reactivate the environment and start Postgres

**Run in PowerShell (from the repo root):**
```powershell
docker-compose up -d
docker-compose ps
```
Confirm `autoeval_postgres` shows `Up`.

**Run in PowerShell:**
```powershell
cd backend
.venv\Scripts\Activate.ps1
python --version
```
Confirm `Python 3.11.x`.

### Add new dependencies

**Run in PowerShell:**
```powershell
notepad requirements.txt
```
Add these lines, save, close:
```text
bcrypt==4.1.2
slowapi==0.1.9
greenlet==3.0.3
pytest-mock==3.12.0
email-validator==2.1.0
```
> `greenlet` is required by SQLAlchemy's async engine on Windows and isn't always pulled in automatically. `slowapi` provides rate limiting for FastAPI. `bcrypt` hashes API keys per `TECH_STACK.md`. `email-validator` is required by Pydantic's `EmailStr` type (used for user registration) — not bundled with base `pydantic`. Clerk is handled via `PyJWT` (already installed in Phase 2) rather than an SDK — the verification is a standard JWKS lookup.

**Run in PowerShell:**
```powershell
pip install -r requirements.txt
```

### Verify DATABASE_URL uses the async driver scheme

Phase 0's `.env` template used `postgresql://`, which routes SQLAlchemy to the **sync** `psycopg2` driver. This project uses `asyncpg`, which requires the `postgresql+asyncpg://` scheme. Nothing before Phase 3 actually opened a database connection, so a wrong scheme here stays invisible until Alembic or the API tries to connect.

**Run in PowerShell:**
```powershell
python -c "from autoeval_ops.config import settings; print(settings.database_url)"
```
If this prints anything not starting with `postgresql+asyncpg://`, fix both env files:

```powershell
notepad ..\.env
```
Set (matching your Phase 0 credentials), save, close:
```ini
DATABASE_URL=postgresql+asyncpg://autoeval_user:dev_password@localhost:5432/autoeval_dev
```

```powershell
notepad ..\.env.example
```
Set, save, close:
```ini
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/autoeval_dev
```

Re-run the check above and confirm the scheme is correct before continuing.

### Task Done When:
- [ ] `docker-compose ps` shows `autoeval_postgres` as `Up`
- [ ] `.venv` active, Python 3.11.x
- [ ] New dependencies installed without errors
- [ ] `settings.database_url` starts with `postgresql+asyncpg://`

---

## Task 1: Package Skeleton

**Run in PowerShell (from `backend/`):**
```powershell
New-Item -ItemType Directory -Force -Path src\autoeval_ops\db, src\autoeval_ops\api, src\autoeval_ops\api\routes
New-Item -ItemType File -Force -Path src\autoeval_ops\db\__init__.py, src\autoeval_ops\api\__init__.py, src\autoeval_ops\api\routes\__init__.py
New-Item -ItemType Directory -Force -Path tests\db, tests\api
New-Item -ItemType File -Force -Path tests\db\__init__.py, tests\api\__init__.py
```

**Verify:**
```powershell
Test-Path src\autoeval_ops\db, src\autoeval_ops\api, src\autoeval_ops\api\routes, tests\db, tests\api
```
All five must print `True`.

### Task 1 Done When:
- [ ] All five directories exist with `__init__.py` files where needed

---

## Task 2: SQLAlchemy ORM Models

Mirrors the 6 tables created in Phase 0. Note `evaluations.status` and `eval_results.status` are plain strings matching the DB defaults, not enums — keeps the ORM aligned with what's already in Postgres.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\db\models.py
```

**Paste into `backend/src/autoeval_ops/db/models.py`:**
```python
"""SQLAlchemy ORM models mirroring the schema created in Phase 0.

Column types and defaults deliberately match backend/db/schema.sql so the
ORM and the live database stay in agreement. Nullability matches
schema.sql's DEFAULT-only columns (no explicit NOT NULL beyond what's
listed there), and named indexes match schema.sql exactly - both matter
for alembic check to pass without phantom drift.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("idx_users_email", "email"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    api_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    organizations: Mapped[list["Organization"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (Index("idx_organizations_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str | None] = mapped_column(String(50), server_default="free")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="organizations")
    projects: Mapped[list["Project"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("idx_projects_org_id", "org_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    github_repo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        Index("idx_evaluations_project_id", "project_id"),
        Index("idx_evaluations_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    test_cases_count: Mapped[int | None] = mapped_column(Integer, server_default="0")
    status: Mapped[str | None] = mapped_column(String(50), server_default="pending")
    results_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="evaluations")
    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    traces: Mapped[list["Trace"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    __tablename__ = "eval_results"
    __table_args__ = (Index("idx_eval_results_eval_id", "eval_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    eval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), server_default="pass")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    evaluation: Mapped["Evaluation"] = relationship(back_populates="results")


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (Index("idx_traces_eval_id", "eval_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    eval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=True
    )
    trace_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    evaluation: Mapped["Evaluation"] = relationship(back_populates="traces")
```
Save, close.

### Task 2 Done When:
- [ ] `models.py` created with all 6 models
- [ ] `python -c "from autoeval_ops.db.models import Base, User, Project, Evaluation"` runs without error

---

## Task 3: Async Database Session

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\db\session.py
```

**Paste into `backend/src/autoeval_ops/db/session.py`:**
```python
"""Async SQLAlchemy engine and session factory.

The engine is created lazily so importing this module never opens a
connection - important for unit tests that don't need a database.
"""
from __future__ import annotations
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from autoeval_ops.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session, committing on success and
    rolling back on any exception."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Called on app shutdown to close the connection pool cleanly."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
```
Save, close.

### Task 3 Done When:
- [ ] `session.py` created
- [ ] Importing it does not open a database connection (lazy engine)

---

## Task 4: Alembic Migrations

Replaces the "pipe `schema.sql` into `docker exec`" approach from Phase 0. `schema.sql` stays in the repo as a historical record of what Phase 0 created.

### Step 4.1: Initialize Alembic

**Run in PowerShell (from `backend/`):**
```powershell
alembic init -t async alembic
```
This creates `backend/alembic/` and `backend/alembic.ini`.

### Step 4.2: Point Alembic at the app's config and models

**Run in PowerShell:**
```powershell
notepad alembic.ini
```
Find the line starting `sqlalchemy.url = ` and set it to empty (the URL comes from `settings` at runtime instead), save, close:
```text
sqlalchemy.url =
```

**Run in PowerShell:**
```powershell
notepad alembic\env.py
```

**Paste into `backend/alembic/env.py`** (full replacement):
```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from autoeval_ops.config import settings
from autoeval_ops.db.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```
Save, close.

### Step 4.3: Create the baseline migration by hand

The 6 tables already exist in your database from Phase 0. `alembic revision --autogenerate` compares against the live database, but `schema.sql` and the ORM models differ in small ways it won't smooth over on its own (explicit `NOT NULL` on server-defaulted columns, unnamed vs. named indexes) — so this baseline is written directly rather than generated, guaranteeing it matches both `schema.sql` and `models.py` exactly and can build the schema from nothing on a fresh database.

**Run in PowerShell to create an empty revision file:**
```powershell
alembic revision -m "baseline: phase 0 schema"
```

**Note the exact filename it created:**
```powershell
Get-ChildItem alembic\versions\*.py | Select-Object -Last 1 | Select-Object Name
```

**Run in PowerShell:**
```powershell
notepad alembic\versions\<the_filename_from_above>.py
```

**Paste into that file** (full replacement — keep whatever revision ID Alembic already generated at the top; the `revision = '...'` line in this template is just a placeholder, use yours instead):
```python
"""baseline: phase 0 schema

Revision ID: <your_revision_id>
Revises:
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '<your_revision_id>'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('api_key', sa.String(255), unique=True, nullable=True),
        sa.Column('api_key_hash', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_users_email', 'users', ['email'])

    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('plan', sa.String(50), server_default='free'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_organizations_user_id', 'organizations', ['user_id'])

    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('github_repo_url', sa.String(255), nullable=True),
        sa.Column('github_token_encrypted', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_projects_org_id', 'projects', ['org_id'])

    op.create_table(
        'evaluations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('commit_hash', sa.String(40), nullable=True),
        sa.Column('prompt_version', sa.String(255), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('test_cases_count', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('results_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_evaluations_project_id', 'evaluations', ['project_id'])
    op.create_index('idx_evaluations_created_at', 'evaluations', ['created_at'])

    op.create_table(
        'eval_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('eval_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=True),
        sa.Column('metric_value', sa.Float(), nullable=True),
        sa.Column('status', sa.String(50), server_default='pass'),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_eval_results_eval_id', 'eval_results', ['eval_id'])

    op.create_table(
        'traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('eval_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('trace_data', postgresql.JSONB(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_traces_eval_id', 'traces', ['eval_id'])


def downgrade() -> None:
    op.drop_table('traces')
    op.drop_table('eval_results')
    op.drop_table('evaluations')
    op.drop_table('projects')
    op.drop_table('organizations')
    op.drop_table('users')
```
Save, close.

**Mark it as already applied (does not run the SQL — the tables already exist from Phase 0):**
```powershell
alembic stamp head
```

**Verify:**
```powershell
alembic current
```
Should print your revision ID followed by `(head)`.

**Confirm models and the live schema fully agree — run this only after stamping**, since `alembic check` first verifies the database's recorded version matches `head`; before stamping, that check fails regardless of whether the models themselves are correct:
```powershell
alembic check
```
Should print nothing and exit cleanly. If it reports drift, recheck that `models.py`'s nullability and index names match this migration exactly.

### Step 4.4: Add a note to the old schema file

**Run in PowerShell:**
```powershell
notepad db\schema.sql
```
Add these lines at the very top, save, close:
```sql
-- HISTORICAL ARTIFACT (Phase 0). Do not run this directly.
-- As of Phase 3, all schema changes go through Alembic migrations:
--   alembic revision --autogenerate -m "description"
--   alembic upgrade head
-- This file records what Phase 0 originally created.
```

### Task 4 Done When:
- [ ] `alembic/` and `alembic.ini` exist
- [ ] A baseline migration exists in `alembic/versions/` containing all 6 tables
- [ ] `alembic current` prints a revision (not empty)
- [ ] `schema.sql` marked as historical

---

## Task 5: Pydantic Schemas (API Request/Response Models)

Separate from ORM models — these define the API's public contract.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\schemas.py
```

**Paste into `backend/src/autoeval_ops/api/schemas.py`:**
```python
"""Pydantic request/response models. Deliberately separate from the ORM
models - these are the API's public contract and shouldn't leak internal
columns (e.g. github_token_encrypted, api_key_hash)."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    # protected_namespaces=() silences Pydantic's warning about
    # EvaluationRead.model_name colliding with the reserved "model_" prefix
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# --- Users ---

class UserCreate(BaseModel):
    email: EmailStr


class UserRead(ORMModel):
    id: uuid.UUID
    email: str
    created_at: datetime


class ApiKeyIssued(BaseModel):
    """The raw key is returned exactly once, at creation. Only its hash is
    stored, so it cannot be retrieved again."""
    api_key: str
    message: str = "Store this key now - it will not be shown again."


# --- Organizations ---

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationRead(ORMModel):
    id: uuid.UUID
    name: str
    plan: str
    created_at: datetime


# --- Projects ---

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    github_repo_url: str = Field(
        min_length=1,
        max_length=255,
        description="Full repo URL or owner/repo, e.g. https://github.com/owner/repo",
    )


class ProjectRead(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    github_repo_url: str | None
    created_at: datetime


# --- Evaluations ---

class EvalResultRead(ORMModel):
    id: uuid.UUID
    metric_name: str | None
    metric_value: float | None
    status: str


class EvaluationRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    commit_hash: str | None
    prompt_version: str | None
    model_name: str | None
    test_cases_count: int
    status: str
    created_at: datetime
    completed_at: datetime | None


class EvaluationDetail(EvaluationRead):
    results_json: dict[str, Any] | None
    results: list[EvalResultRead] = []
```
Save, close.

### Task 5 Done When:
- [ ] `schemas.py` created and imports cleanly

---

## Task 6: Repository Layer

All database access lives here so routes and the orchestrator never write raw queries.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\db\repository.py
```

**Paste into `backend/src/autoeval_ops/db/repository.py`:**
```python
"""Database access layer. Routes and the orchestrator call these functions
rather than writing queries inline."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autoeval_ops.db.models import (
    EvalResult,
    Evaluation,
    Organization,
    Project,
    User,
)


def normalize_repo(github_repo_url: str) -> str:
    """Reduce any GitHub repo reference to a canonical lowercase
    'owner/repo' so webhook payloads and user-entered URLs match.

    Handles: https://github.com/Owner/Repo, github.com/Owner/Repo.git,
    Owner/Repo
    """
    value = github_repo_url.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break
    if value.lower().endswith(".git"):
        value = value[:-4]
    return value.lower()


# --- Users ---

async def create_user(db: AsyncSession, email: str, api_key_hash: str) -> User:
    user = User(email=email, api_key_hash=api_key_hash)
    db.add(user)
    await db.flush()
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def list_users_with_api_keys(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.api_key_hash.is_not(None)))
    return list(result.scalars().all())


async def set_api_key_hash(db: AsyncSession, user: User, api_key_hash: str) -> User:
    user.api_key_hash = api_key_hash
    await db.flush()
    return user


# --- Organizations ---

async def create_organization(db: AsyncSession, user_id: uuid.UUID, name: str) -> Organization:
    org = Organization(user_id=user_id, name=name)
    db.add(org)
    await db.flush()
    return org


async def list_organizations_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Organization]:
    result = await db.execute(select(Organization).where(Organization.user_id == user_id))
    return list(result.scalars().all())


async def get_organization(db: AsyncSession, org_id: uuid.UUID) -> Organization | None:
    return await db.get(Organization, org_id)


# --- Projects ---

async def create_project(
    db: AsyncSession, org_id: uuid.UUID, name: str, github_repo_url: str
) -> Project:
    project = Project(
        org_id=org_id, name=name, github_repo_url=normalize_repo(github_repo_url)
    )
    db.add(project)
    await db.flush()
    return project


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> Project | None:
    return await db.get(Project, project_id)


async def get_project_by_repo(db: AsyncSession, owner: str, repo: str) -> Project | None:
    """Look up a pre-registered project from webhook payload fields.
    Returns None for unregistered repos - the caller must ignore those."""
    normalized = normalize_repo(f"{owner}/{repo}")
    result = await db.execute(
        select(Project).where(Project.github_repo_url == normalized)
    )
    return result.scalars().first()


async def list_projects_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Project]:
    result = await db.execute(
        select(Project)
        .join(Organization, Project.org_id == Organization.id)
        .where(Organization.user_id == user_id)
    )
    return list(result.scalars().all())


async def user_owns_project(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(Project.id)
        .join(Organization, Project.org_id == Organization.id)
        .where(Project.id == project_id, Organization.user_id == user_id)
    )
    return result.scalar_one_or_none() is not None


# --- Evaluations ---

async def create_evaluation(
    db: AsyncSession,
    project_id: uuid.UUID,
    commit_hash: str | None,
    prompt_version: str | None,
    model_name: str | None,
    test_cases_count: int,
) -> Evaluation:
    evaluation = Evaluation(
        project_id=project_id,
        commit_hash=commit_hash,
        prompt_version=prompt_version,
        model_name=model_name,
        test_cases_count=test_cases_count,
        status="pending",
    )
    db.add(evaluation)
    await db.flush()
    return evaluation


async def complete_evaluation(
    db: AsyncSession,
    evaluation: Evaluation,
    status: str,
    results_json: dict[str, Any],
    metric_rows: list[dict[str, Any]],
) -> Evaluation:
    evaluation.status = status
    evaluation.results_json = results_json
    evaluation.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in metric_rows:
        db.add(
            EvalResult(
                eval_id=evaluation.id,
                metric_name=row["metric_name"],
                metric_value=row["metric_value"],
                status=row["status"],
                details=row.get("details"),
            )
        )
    await db.flush()
    return evaluation


async def fail_evaluation(db: AsyncSession, evaluation: Evaluation, reason: str) -> Evaluation:
    evaluation.status = "failed"
    evaluation.results_json = {"error": reason}
    evaluation.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    return evaluation


async def list_evaluations_for_project(
    db: AsyncSession, project_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[Evaluation]:
    result = await db.execute(
        select(Evaluation)
        .where(Evaluation.project_id == project_id)
        .order_by(Evaluation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_evaluation_detail(db: AsyncSession, eval_id: uuid.UUID) -> Evaluation | None:
    result = await db.execute(
        select(Evaluation)
        .where(Evaluation.id == eval_id)
        .options(selectinload(Evaluation.results))
    )
    return result.scalar_one_or_none()
```
Save, close.

### Task 6 Done When:
- [ ] `repository.py` created and imports cleanly

---

## Task 7: Authentication

Two paths: API keys (fully testable now) and Clerk JWTs (verifiable end-to-end only once Phase 4's dashboard exists).

### Step 7.1: API key generation and hashing

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\security.py
```

**Paste into `backend/src/autoeval_ops/api/security.py`:**
```python
"""API key generation/verification (bcrypt) and Clerk JWT verification.

Only the bcrypt hash of an API key is stored - the raw key is shown to the
user exactly once at creation and cannot be recovered afterwards.
"""
from __future__ import annotations
import secrets

import bcrypt

API_KEY_PREFIX = "aeo_"


def generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(api_key: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(api_key.encode(), stored_hash.encode())
    except (ValueError, TypeError):
        return False
```
Save, close.

### Step 7.2: Clerk JWT verification

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\clerk.py
```

**Paste into `backend/src/autoeval_ops/api/clerk.py`:**
```python
"""Clerk session-token verification via JWKS.

Cannot be verified against a real Clerk login until Phase 4's dashboard
exists to produce real session tokens - Phase 3 tests this against a
mocked JWKS endpoint.
"""
from __future__ import annotations
import time

import httpx
import jwt
from jwt import PyJWKClient


class ClerkVerifier:
    def __init__(self, jwks_url: str, http_client: httpx.AsyncClient | None = None):
        self.jwks_url = jwks_url
        self._http = http_client
        self._jwks_cache: dict | None = None
        self._jwks_fetched_at: float = 0.0
        self._cache_ttl_seconds = 3600

    async def _get_jwks(self) -> dict:
        now = time.time()
        if self._jwks_cache and (now - self._jwks_fetched_at) < self._cache_ttl_seconds:
            return self._jwks_cache
        client = self._http or httpx.AsyncClient()
        resp = await client.get(self.jwks_url)
        resp.raise_for_status()
        self._jwks_cache = resp.json()
        self._jwks_fetched_at = now
        return self._jwks_cache

    async def verify(self, token: str) -> dict:
        """Returns the decoded claims, or raises jwt.PyJWTError."""
        jwks = await self._get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if key_data is None:
            raise jwt.InvalidTokenError("No matching key in JWKS")
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        return jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})
```
Save, close.

### Step 7.3: FastAPI auth dependencies

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\deps.py
```

**Paste into `backend/src/autoeval_ops/api/deps.py`:**
```python
"""FastAPI dependencies for authentication.

Accepts either an API key (X-API-Key header) or a Clerk session token
(Authorization: Bearer ...). API keys are the machine-to-machine path;
Clerk is what the Phase 4 dashboard will use.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.api.security import verify_api_key
from autoeval_ops.config import settings
from autoeval_ops.db import repository
from autoeval_ops.db.models import User
from autoeval_ops.db.session import get_db

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _user_from_api_key(db: AsyncSession, api_key: str) -> User | None:
    # bcrypt hashes are salted, so the key can't be looked up directly -
    # each candidate hash must be checked. Fine at this scale; revisit with
    # a lookup-prefix column if the user table grows large.
    for user in await repository.list_users_with_api_keys(db):
        if user.api_key_hash and verify_api_key(api_key, user.api_key_hash):
            return user
    return None


async def _user_from_clerk_token(db: AsyncSession, token: str) -> User | None:
    if not settings.clerk_jwks_url:
        return None
    from autoeval_ops.api.clerk import ClerkVerifier

    verifier = ClerkVerifier(settings.clerk_jwks_url)
    try:
        claims = await verifier.verify(token)
    except Exception:
        return None
    email = claims.get("email")
    if not email:
        return None
    return await repository.get_user_by_email(db, email)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(default=""),
    authorization: str = Header(default=""),
) -> User:
    if x_api_key:
        user = await _user_from_api_key(db, x_api_key)
        if user:
            return user

    if authorization.startswith("Bearer "):
        user = await _user_from_clerk_token(db, authorization.removeprefix("Bearer "))
        if user:
            return user

    raise _CREDENTIALS_ERROR
```
Save, close.

### Step 7.4: Add Clerk settings to config

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\config.py
```
Add these two fields inside the `Settings` class (below the GitHub App fields), save, close:
```python
    # Clerk (Phase 3; live verification deferred to Phase 4)
    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""
```

**Run in PowerShell (from the repo root):**
```powershell
notepad ..\.env.example
```
Add these lines, save, close:
```ini
CLERK_JWKS_URL=
```
Then mirror it into your real `.env`:
```powershell
notepad ..\.env
```
Add (leave blank for now — fill in when you set up Clerk in Phase 4), save, close:
```ini
CLERK_JWKS_URL=
```

### Task 7 Done When:
- [ ] `security.py`, `clerk.py`, `deps.py` created
- [ ] `config.py` has `clerk_secret_key` and `clerk_jwks_url`
- [ ] `.env` and `.env.example` have `CLERK_JWKS_URL`

---

## Task 8: API Routes

### Step 8.1: Users and API keys

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\routes\users.py
```

**Paste into `backend/src/autoeval_ops/api/routes/users.py`:**
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.api import schemas
from autoeval_ops.api.deps import get_current_user
from autoeval_ops.api.security import generate_api_key, hash_api_key
from autoeval_ops.db import repository
from autoeval_ops.db.models import User
from autoeval_ops.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.post("/users", response_model=schemas.ApiKeyIssued, status_code=status.HTTP_201_CREATED)
async def register_user(payload: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await repository.get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    raw_key = generate_api_key()
    await repository.create_user(db, email=payload.email, api_key_hash=hash_api_key(raw_key))
    return schemas.ApiKeyIssued(api_key=raw_key)


@router.get("/users/me", response_model=schemas.UserRead)
async def read_current_user(user: User = Depends(get_current_user)):
    return user


@router.post("/users/me/api-key", response_model=schemas.ApiKeyIssued)
async def rotate_api_key(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    raw_key = generate_api_key()
    await repository.set_api_key_hash(db, user, hash_api_key(raw_key))
    return schemas.ApiKeyIssued(api_key=raw_key)
```
Save, close.

### Step 8.2: Organizations

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\routes\organizations.py
```

**Paste into `backend/src/autoeval_ops/api/routes/organizations.py`:**
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.api import schemas
from autoeval_ops.api.deps import get_current_user
from autoeval_ops.db import repository
from autoeval_ops.db.models import User
from autoeval_ops.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["organizations"])


@router.post(
    "/organizations", response_model=schemas.OrganizationRead, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    payload: schemas.OrganizationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await repository.create_organization(db, user_id=user.id, name=payload.name)


@router.get("/organizations", response_model=list[schemas.OrganizationRead])
async def list_organizations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await repository.list_organizations_for_user(db, user.id)
```
Save, close.

### Step 8.3: Projects

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\routes\projects.py
```

**Paste into `backend/src/autoeval_ops/api/routes/projects.py`:**
```python
from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.api import schemas
from autoeval_ops.api.deps import get_current_user
from autoeval_ops.db import repository
from autoeval_ops.db.models import User
from autoeval_ops.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["projects"])


@router.post("/projects", response_model=schemas.ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: schemas.ProjectCreate,
    org_id: uuid.UUID = Query(..., description="Organization to create the project under"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org = await repository.get_organization(db, org_id)
    if org is None or org.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return await repository.create_project(
        db, org_id=org_id, name=payload.name, github_repo_url=payload.github_repo_url
    )


@router.get("/projects", response_model=list[schemas.ProjectRead])
async def list_projects(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await repository.list_projects_for_user(db, user.id)


@router.get("/projects/{project_id}", response_model=schemas.ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await repository.user_owns_project(db, user.id, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return await repository.get_project(db, project_id)
```
Save, close.

### Step 8.4: Evaluations

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\api\routes\evaluations.py
```

**Paste into `backend/src/autoeval_ops/api/routes/evaluations.py`:**
```python
from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.api import schemas
from autoeval_ops.api.deps import get_current_user
from autoeval_ops.db import repository
from autoeval_ops.db.models import User
from autoeval_ops.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


@router.get("/projects/{project_id}/evals", response_model=list[schemas.EvaluationRead])
async def list_evaluations(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await repository.user_owns_project(db, user.id, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return await repository.list_evaluations_for_project(db, project_id, limit=limit, offset=offset)


@router.get("/evals/{eval_id}", response_model=schemas.EvaluationDetail)
async def get_evaluation(
    eval_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    evaluation = await repository.get_evaluation_detail(db, eval_id)
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found")
    if not await repository.user_owns_project(db, user.id, evaluation.project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found")
    return evaluation
```
Save, close.

### Task 8 Done When:
- [ ] All four route modules created and importing cleanly

---

## Task 9: Retrofit the Orchestrator for Persistence

The orchestrator keeps posting PR comments exactly as before. Persistence is added *alongside* that, and a database failure must never prevent the comment from posting.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\github\orchestrator.py
```

**Paste into `backend/src/autoeval_ops/github/orchestrator.py`** (full replacement):
```python
"""Wires together GitHub API access, prompt execution, and evaluation for a
single PR job, posts the results as a PR comment, and (Phase 3) persists
each run to Postgres.

Convention: a prompt file at prompts/<name>.txt is evaluated against test
cases at eval/<name>.test_cases.json in the same repo/ref.

Persistence is best-effort and never blocks commenting: if the database is
unreachable, the PR comment must still post.
"""
from __future__ import annotations
import json

from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.client import GitHubClient
from autoeval_ops.github.queue import EvalJob
from autoeval_ops.github.runner import PromptRunner
from autoeval_ops.github.comment import format_comment
from autoeval_ops.core.llm_client import build_llm_client
from autoeval_ops.core.pipeline import EvaluationPipeline, EvaluationReport
from autoeval_ops.core.evaluators.correctness import CorrectnessEvaluator
from autoeval_ops.core.evaluators.toxicity import ToxicityEvaluator, NullToxicityScorer
from autoeval_ops.core.evaluators.hallucination import HallucinationEvaluator
from autoeval_ops.core.evaluators.cost import CostEvaluator
from autoeval_ops.core.evaluators.latency import LatencyEvaluator
from autoeval_ops.db import repository
from autoeval_ops.db.session import get_session_factory

PROMPT_DIR_PREFIX = "prompts/"
PROMPT_SUFFIX = ".txt"


def is_prompt_file(path: str) -> bool:
    return path.startswith(PROMPT_DIR_PREFIX) and path.endswith(PROMPT_SUFFIX)


def resolve_test_cases_path(prompt_path: str) -> str:
    return prompt_path.replace("prompts/", "eval/", 1).replace(".txt", ".test_cases.json")


def build_default_pipeline(model: str, llm_client) -> EvaluationPipeline:
    return EvaluationPipeline(
        [
            CorrectnessEvaluator(llm_client),
            ToxicityEvaluator(NullToxicityScorer()),
            HallucinationEvaluator(),
            CostEvaluator(model=model),
            LatencyEvaluator(),
        ]
    )


def aggregate_reports(reports: list[EvaluationReport]) -> tuple[str, dict, list[dict]]:
    """Roll per-case reports up into (overall_status, results_json, metric_rows).

    metric_rows averages each metric across cases, and marks a metric failed
    if it failed in any case - one bad case shouldn't be averaged away.
    """
    overall = "pass"
    if any(r.overall_status == "fail" for r in reports):
        overall = "fail"
    elif any(r.overall_status == "warning" for r in reports):
        overall = "warning"

    results_json = {"cases": [r.as_dict() for r in reports]}

    totals: dict[str, list[float]] = {}
    statuses: dict[str, list[str]] = {}
    for report in reports:
        for result in report.results:
            totals.setdefault(result.metric_name, []).append(result.metric_value)
            statuses.setdefault(result.metric_name, []).append(result.status)

    metric_rows = []
    for metric_name, values in totals.items():
        metric_statuses = statuses[metric_name]
        if "fail" in metric_statuses:
            status = "fail"
        elif "warning" in metric_statuses:
            status = "warning"
        else:
            status = "pass"
        metric_rows.append(
            {
                "metric_name": metric_name,
                "metric_value": sum(values) / len(values) if values else 0.0,
                "status": status,
                "details": {"case_count": len(values)},
            }
        )
    return overall, results_json, metric_rows


async def handle_eval_job(
    job: EvalJob,
    app_auth: GitHubAppAuth,
    model: str = "gpt-4",
    client_factory=GitHubClient,
    session_factory=None,
) -> None:
    token = await app_auth.get_installation_token(job.installation_id)
    gh = client_factory(token)

    files = await gh.get_pr_files(job.owner, job.repo, job.pr_number)
    prompt_files = [f["filename"] for f in files if is_prompt_file(f["filename"])]
    if not prompt_files:
        return

    llm_client = build_llm_client(model)
    runner = PromptRunner(llm_client)

    if session_factory is None:
        session_factory = get_session_factory()

    for prompt_path in prompt_files:
        prompt_text = await gh.get_file_content(job.owner, job.repo, prompt_path, job.head_sha)

        tc_path = resolve_test_cases_path(prompt_path)
        try:
            test_cases_raw = await gh.get_file_content(job.owner, job.repo, tc_path, job.head_sha)
        except Exception:
            continue  # no matching test suite for this prompt, skip

        test_cases = json.loads(test_cases_raw)
        prepared_cases = await runner.run(prompt_text, test_cases)

        pipeline = build_default_pipeline(model, llm_client)
        reports = await pipeline.evaluate_batch([dict(c) for c in prepared_cases])

        # Persist - best effort, never blocks the PR comment below.
        try:
            async with session_factory() as db:
                project = await repository.get_project_by_repo(db, job.owner, job.repo)
                if project is None:
                    print(
                        f"AutoEvalOps: repo {job.owner}/{job.repo} is not a registered "
                        f"project - evaluation not persisted. Register it via "
                        f"POST /api/v1/projects to enable history."
                    )
                else:
                    evaluation = await repository.create_evaluation(
                        db,
                        project_id=project.id,
                        commit_hash=job.head_sha,
                        prompt_version=prompt_path,
                        model_name=model,
                        test_cases_count=len(test_cases),
                    )
                    overall, results_json, metric_rows = aggregate_reports(reports)
                    await repository.complete_evaluation(
                        db,
                        evaluation,
                        status=overall,
                        results_json=results_json,
                        metric_rows=metric_rows,
                    )
                    await db.commit()
        except Exception as exc:
            print(f"AutoEvalOps: failed to persist evaluation - {exc}")

        comment_body = format_comment(prompt_path, reports)
        await gh.post_pr_comment(job.owner, job.repo, job.pr_number, comment_body)
```
Save, close.

### Task 9 Done When:
- [ ] `orchestrator.py` updated with persistence
- [ ] Persistence wrapped in try/except so it can never block PR commenting
- [ ] Unregistered repos are logged and skipped, not auto-created

---

## Task 10: Expand server.py

`server.py` already exists from Phase 2. This **adds** to it — API routers, DB pool cleanup, CORS, and rate limiting — rather than replacing it.

**Run in PowerShell:**
```powershell
notepad src\autoeval_ops\server.py
```

**Paste into `backend/src/autoeval_ops/server.py`** (full replacement — note the Phase 2 webhook router and queue lifespan are preserved):
```python
"""FastAPI application: GitHub webhook receiver (Phase 2) + backend API
(Phase 3). Expanded from Phase 2's minimal server, not replaced.
"""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from autoeval_ops.github.queue import eval_queue
from autoeval_ops.github.app_auth import GitHubAppAuth
from autoeval_ops.github.orchestrator import handle_eval_job
from autoeval_ops.github.webhook import router as github_router
from autoeval_ops.api.routes.users import router as users_router
from autoeval_ops.api.routes.organizations import router as organizations_router
from autoeval_ops.api.routes.projects import router as projects_router
from autoeval_ops.api.routes.evaluations import router as evaluations_router
from autoeval_ops.db.session import dispose_engine
from autoeval_ops.config import settings, resolve_repo_path

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


def _load_app_auth() -> GitHubAppAuth:
    # .env's GITHUB_APP_PRIVATE_KEY_PATH is relative to the repo root, not
    # to whichever directory uvicorn was launched from - resolve_repo_path
    # (see config.py) makes this work regardless of cwd.
    key_path = resolve_repo_path(settings.github_app_private_key_path)
    with open(key_path, "r") as f:
        private_key = f.read()
    return GitHubAppAuth(app_id=settings.github_app_id, private_key=private_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_auth = _load_app_auth()

    async def handler(job):
        await handle_eval_job(job, app_auth)

    eval_queue.start(handler)
    yield
    await eval_queue.stop()
    await dispose_engine()


app = FastAPI(
    title="AutoEvalOps",
    description="Automated LLM prompt evaluation on every pull request.",
    version="0.3.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Phase 4 dashboard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(github_router)
app.include_router(users_router)
app.include_router(organizations_router)
app.include_router(projects_router)
app.include_router(evaluations_router)
```
Save, close.

### Task 10 Done When:
- [ ] `server.py` includes all four API routers plus the Phase 2 webhook router
- [ ] Queue lifespan startup/shutdown preserved from Phase 2
- [ ] `dispose_engine()` called on shutdown

---

## Task 11: Test Configuration

Splits fast unit tests from Docker-dependent integration tests.

### Step 11.1: Register the integration marker

**Run in PowerShell:**
```powershell
notepad pytest.ini
```

**Paste into `backend/pytest.ini`** (full replacement):
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
markers =
    integration: requires a live Postgres from docker-compose
```
Save, close.

### Step 11.2: Database fixtures

**Run in PowerShell:**
```powershell
notepad tests\db\conftest.py
```

**Paste into `backend/tests/db/conftest.py`:**
```python
"""Integration-test fixtures. Each test runs inside a transaction that is
rolled back afterwards, so tests never leave rows behind and can run in any
order against the same database."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autoeval_ops.config import settings


@pytest_asyncio.fixture(scope="function")
async def db_session():
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
```
Save, close.

### Task 11 Done When:
- [ ] `pytest.ini` registers the `integration` marker
- [ ] `tests/db/conftest.py` created with rollback-per-test fixtures

---

## Task 12: Unit Tests (No Database Required)

### Step 12.1: Security

**Run in PowerShell:**
```powershell
notepad tests\api\test_security.py
```

**Paste into `backend/tests/api/test_security.py`:**
```python
from autoeval_ops.api.security import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


def test_generated_key_has_expected_prefix():
    assert generate_api_key().startswith(API_KEY_PREFIX)


def test_generated_keys_are_unique():
    assert generate_api_key() != generate_api_key()


def test_hash_then_verify_roundtrip():
    key = generate_api_key()
    assert verify_api_key(key, hash_api_key(key)) is True


def test_verify_rejects_wrong_key():
    stored = hash_api_key(generate_api_key())
    assert verify_api_key(generate_api_key(), stored) is False


def test_verify_rejects_malformed_hash():
    assert verify_api_key("some-key", "not-a-bcrypt-hash") is False


def test_hash_is_salted_so_same_key_hashes_differently():
    key = generate_api_key()
    assert hash_api_key(key) != hash_api_key(key)
```
Save, close.

### Step 12.2: Repo normalization

**Run in PowerShell:**
```powershell
notepad tests\db\test_repository_helpers.py
```

**Paste into `backend/tests/db/test_repository_helpers.py`:**
```python
"""Pure-function tests for repository helpers - no database needed."""
from autoeval_ops.db.repository import normalize_repo


def test_normalize_strips_https_prefix():
    assert normalize_repo("https://github.com/Owner/Repo") == "owner/repo"


def test_normalize_strips_git_suffix():
    assert normalize_repo("https://github.com/Owner/Repo.git") == "owner/repo"


def test_normalize_handles_bare_owner_repo():
    assert normalize_repo("Owner/Repo") == "owner/repo"


def test_normalize_strips_trailing_slash():
    assert normalize_repo("https://github.com/Owner/Repo/") == "owner/repo"


def test_normalize_is_idempotent():
    once = normalize_repo("https://github.com/Owner/Repo.git")
    assert normalize_repo(once) == once
```
Save, close.

### Step 12.3: Report aggregation

**Run in PowerShell:**
```powershell
notepad tests\github\test_orchestrator_aggregation.py
```

**Paste into `backend/tests/github/test_orchestrator_aggregation.py`:**
```python
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
```
Save, close.

### Step 12.4: Orchestrator persistence behavior

**Run in PowerShell:**
```powershell
notepad tests\github\test_orchestrator_persistence.py
```

**Paste into `backend/tests/github/test_orchestrator_persistence.py`:**
```python
"""Verifies persistence is best-effort: a DB failure must never prevent the
PR comment from posting, and unregistered repos must not create rows."""
from __future__ import annotations
import json

from autoeval_ops.github.orchestrator import handle_eval_job
from autoeval_ops.github.queue import EvalJob

TEST_CASES = json.dumps([{"input": "hello", "expected": "world", "context": "hello world"}])


class FakeAppAuth:
    async def get_installation_token(self, installation_id: int) -> str:
        return "fake-token"


class FakeGitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.posted_comments: list[str] = []

    async def get_pr_files(self, owner, repo, pr_number):
        return [{"filename": "prompts/summarize.txt"}]

    async def get_file_content(self, owner, repo, path, ref):
        if path == "prompts/summarize.txt":
            return "Echo: {text}"
        if path == "eval/summarize.test_cases.json":
            return TEST_CASES
        raise FileNotFoundError(path)

    async def post_pr_comment(self, owner, repo, pr_number, body):
        self.posted_comments.append(body)


class ExplodingSessionFactory:
    """Simulates a completely unreachable database."""

    def __call__(self):
        raise ConnectionError("database is down")


def _job() -> EvalJob:
    return EvalJob(installation_id=1, owner="o", repo="r", pr_number=1, head_sha="abc")


async def test_comment_still_posts_when_database_is_unreachable(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    holder = {}

    def factory(token):
        client = FakeGitHubClient(token)
        holder["client"] = client
        return client

    await handle_eval_job(
        _job(), FakeAppAuth(), client_factory=factory, session_factory=ExplodingSessionFactory()
    )

    assert len(holder["client"].posted_comments) == 1
    assert "failed to persist" in capsys.readouterr().out
```
Save, close.

### Step 12.5: Route auth behavior (no DB)

**Run in PowerShell:**
```powershell
notepad tests\api\test_routes_auth.py
```

**Paste into `backend/tests/api/test_routes_auth.py`:**
```python
"""Verifies protected routes reject unauthenticated requests. Uses a
dependency override so no database is needed - a request that gets past
auth would fail on the DB, so most of these deliberately only assert on
401s.

test_invalid_uuid_path_returns_422 additionally overrides get_current_user
itself (not just get_db) to bypass auth entirely, isolating path-parameter
validation from auth - a dependency that raises during resolution (like
get_current_user's 401) short-circuits FastAPI's normal path-validation
error handling, so without this override the request never gets far enough
to reach the invalid-UUID check.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autoeval_ops.api.deps import get_current_user
from autoeval_ops.api.routes.evaluations import router as evaluations_router
from autoeval_ops.api.routes.organizations import router as organizations_router
from autoeval_ops.api.routes.projects import router as projects_router
from autoeval_ops.api.routes.users import router as users_router
from autoeval_ops.db.session import get_db


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(users_router)
    app.include_router(organizations_router)
    app.include_router(projects_router)
    app.include_router(evaluations_router)
    return app


@pytest.fixture
def client():
    app = _build_app()

    async def _no_db():
        yield None

    app.dependency_overrides[get_db] = _no_db
    return TestClient(app)


@pytest.fixture
def authenticated_client():
    app = _build_app()

    class _DummyUser:
        id = "00000000-0000-0000-0000-000000000099"

    async def _no_db():
        yield None

    async def _fake_user():
        return _DummyUser()

    app.dependency_overrides[get_db] = _no_db
    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def test_users_me_requires_auth(client):
    assert client.get("/api/v1/users/me").status_code == 401


def test_list_organizations_requires_auth(client):
    assert client.get("/api/v1/organizations").status_code == 401


def test_list_projects_requires_auth(client):
    assert client.get("/api/v1/projects").status_code == 401


def test_get_evaluation_requires_auth(client):
    eval_id = "00000000-0000-0000-0000-000000000001"
    assert client.get(f"/api/v1/evals/{eval_id}").status_code == 401


def test_invalid_uuid_path_returns_422(authenticated_client):
    assert authenticated_client.get("/api/v1/evals/not-a-uuid").status_code == 422
```
Save, close.

### Task 12 Done When:
- [ ] All five unit test files created
- [ ] `pytest -m "not integration"` passes with no database running

---

## Task 13: Integration Tests (Require Postgres)

**Run in PowerShell:**
```powershell
notepad tests\db\test_repository_integration.py
```

**Paste into `backend/tests/db/test_repository_integration.py`:**
```python
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
```
Save, close.

### Task 13 Done When:
- [ ] Integration test file created
- [ ] `pytest -m integration` passes with `docker-compose up -d` running

---

## Task 14: Run Both Test Suites

### Step 14.1: Fast suite (no Docker needed)

**Run in PowerShell:**
```powershell
pytest -m "not integration" -v
```
All previous Phase 0-2 tests plus the new unit tests should pass.

### Step 14.2: Integration suite (Docker required)

**Run in PowerShell (from the repo root, then back):**
```powershell
cd ..
docker-compose up -d
cd backend
pytest -m integration -v
```

### Step 14.3: Everything, with coverage

**Run in PowerShell:**
```powershell
pytest -v --cov=autoeval_ops --cov-report=term-missing
```
Expect roughly 105 tests (75 from Phase 2 + ~23 unit + 7 integration), all passing, coverage ≥95%. Expected uncovered code, same as before: `OpenAILLMClient`'s real-API branch, `DetoxifyScorer`, `main()`/`__main__`, plus `clerk.py`'s live JWKS path (verified against mocks only until Phase 4).

### Task 14 Done When:
- [ ] `pytest -m "not integration"` passes with Docker stopped
- [ ] `pytest -m integration` passes with Docker running
- [ ] Full run passes with ≥95% coverage, no warnings

---

## Task 15: Manual API Verification

### Step 15.1: Start the server

**Run in PowerShell (from `backend/`, venv active, Docker running):**
```powershell
uvicorn autoeval_ops.server:app --reload --port 8000
```

### Step 15.2: Explore the interactive docs

Open http://localhost:8000/docs in a browser. FastAPI generates this from the route definitions — every endpoint should be listed with its request/response schemas.

### Step 15.3: Walk the full flow

**Run in PowerShell (new tab):**
```powershell
# 1. Register a user - save the api_key from the response, it is shown only once
$user = Invoke-RestMethod -Uri http://localhost:8000/api/v1/users -Method Post -ContentType "application/json" -Body '{"email":"you@example.com"}'
$apiKey = $user.api_key
Write-Host "API key: $apiKey"

# 2. Confirm the key authenticates
Invoke-RestMethod -Uri http://localhost:8000/api/v1/users/me -Headers @{"X-API-Key"=$apiKey}

# 3. Create an organization
$org = Invoke-RestMethod -Uri http://localhost:8000/api/v1/organizations -Method Post -Headers @{"X-API-Key"=$apiKey} -ContentType "application/json" -Body '{"name":"My Org"}'

# 4. Register your repo as a project (use YOUR repo URL)
$body = '{"name":"AutoEvalOps","github_repo_url":"https://github.com/Basilbe/autoeval-ops"}'
$project = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects?org_id=$($org.id)" -Method Post -Headers @{"X-API-Key"=$apiKey} -ContentType "application/json" -Body $body
$project

# 5. List evaluations (empty until a webhook fires for this repo)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/$($project.id)/evals" -Headers @{"X-API-Key"=$apiKey}

# 6. Confirm auth is actually enforced - this must fail with 401
try { Invoke-RestMethod -Uri http://localhost:8000/api/v1/users/me } catch { Write-Host "Correctly rejected: $($_.Exception.Response.StatusCode)" }
```

### Task 15 Done When:
- [ ] `/docs` lists all endpoints
- [ ] Full flow works: register → authenticate → create org → create project → list evals
- [ ] Unauthenticated request correctly returns 401

---

## Task 16: End-to-End — Webhook Writes to the Database

This is the payoff: the same webhook flow verified in Phase 2, now persisting results.

### Step 16.1: Confirm your repo is registered
You registered it in Task 15.3, step 4. Confirm it's there:
```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/v1/projects -Headers @{"X-API-Key"=$apiKey}
```
The `github_repo_url` should read `basilbe/autoeval-ops` (normalized lowercase).

### Step 16.2: Start the tunnel

**Run in PowerShell (new tab):**
```powershell
cloudflared tunnel --url http://localhost:8000
```
Copy the fresh `*.trycloudflare.com` URL.

### Step 16.3: Update the GitHub App's webhook URL
GitHub App settings → General → Webhook URL:
```
https://your-new-url.trycloudflare.com/github/webhook
```
**Save changes.**

### Step 16.4: Trigger an evaluation
Push a change to `prompts/summarize.txt` on a branch with an open PR (or reopen/redeliver from the App's **Advanced → Recent Deliveries** tab).

### Step 16.5: Confirm it persisted

**Run in PowerShell:**
```powershell
$evals = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/projects/$($project.id)/evals" -Headers @{"X-API-Key"=$apiKey}
$evals
```
You should now see an evaluation row with a `commit_hash`, `prompt_version`, and `status`.

**Fetch full detail including per-metric rows:**
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/evals/$($evals[0].id)" -Headers @{"X-API-Key"=$apiKey}
```

**Cross-check directly in Postgres:**
```powershell
docker exec -it autoeval_postgres psql -U autoeval_user -d autoeval_dev -c "SELECT id, commit_hash, status, test_cases_count FROM evaluations ORDER BY created_at DESC LIMIT 5;"
docker exec -it autoeval_postgres psql -U autoeval_user -d autoeval_dev -c "SELECT metric_name, metric_value, status FROM eval_results ORDER BY created_at DESC LIMIT 10;"
```

### Task 16 Done When:
- [ ] A webhook-triggered evaluation appears via the API
- [ ] The same row is visible directly in Postgres
- [ ] `eval_results` has one row per metric
- [ ] The PR comment still posted (persistence didn't break Phase 2's behavior)

---

## Task 17: Final Commit and Verification

### Step 17.1: Verify no secrets are tracked

**Run in PowerShell (from the repo root):**
```powershell
git ls-files | Select-String -Pattern "secrets|\.pem|^\.env$"
```
Should return nothing.

### Step 17.2: Full verification pass

**Run in PowerShell:**
```powershell
Write-Host "=== Tests ===" -ForegroundColor Cyan
cd backend
.venv\Scripts\Activate.ps1
pytest -v --cov=autoeval_ops --cov-report=term-missing
deactivate
cd ..

Write-Host "=== Migrations ===" -ForegroundColor Cyan
cd backend
.venv\Scripts\Activate.ps1
alembic current
deactivate
cd ..

Write-Host "=== Git Status ===" -ForegroundColor Cyan
git status
```

### Step 17.3: Commit and push

**Run in PowerShell:**
```powershell
git add -A
git commit -m "[PHASE 3] Backend API + database persistence

- SQLAlchemy ORM models for all 6 Phase 0 tables
- Async session management with lazy engine, pooling, clean shutdown
- Alembic migrations adopted; schema.sql marked historical
- Repository layer centralizing all database access
- API key auth (bcrypt) + Clerk JWT verification (live check deferred to Phase 4)
- REST endpoints: users, organizations, projects, evaluations
- Orchestrator retrofitted to persist runs; PR commenting unchanged and
  never blocked by database failures
- server.py expanded (not replaced) with API routers, CORS, rate limiting
- Unregistered repos are logged and skipped, never auto-created
- Hybrid test suite: fast unit tests + docker-dependent integration tests
- Test coverage: see PHASE_3_STATUS.md
- Breaking changes: NO (Phase 2 webhook flow re-verified end-to-end)"
git push origin main
```

### Final Checklist:
- [ ] ORM models mirror the live schema
- [ ] Alembic manages migrations; `alembic current` shows a revision
- [ ] All four route groups working and auth-protected
- [ ] Orchestrator persists evaluations without ever blocking PR comments
- [ ] Both test suites pass; coverage ≥95%
- [ ] End-to-end verified: webhook → evaluation row in Postgres → visible via API
- [ ] Committed and pushed

---

## Next Step

Once every box is checked, write `PHASE_3_STATUS.md` (same audit pattern as Phases 0-2), then move to **Phase 4: Frontend Dashboard**.

**Worth revisiting at the start of Phase 4:** the roadmap specifies a hand-built Next.js dashboard, but a visual-first tool (e.g. Claude Design) may be a better fit for iterating on UI. Nothing in Phase 3 constrains this — the backend just exposes JSON over HTTP, so any frontend approach works. Decide it explicitly at the Phase 4 kickoff and document the choice, same as every other deviation.

Also note for Phase 4: Clerk's live login flow becomes verifiable for the first time once a dashboard exists. `CLERK_JWKS_URL` in `.env` is currently blank — fill it in then.

---

## Troubleshooting Log (Phase 3)

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'psycopg2'` from Alembic or the API | `DATABASE_URL` uses the plain `postgresql://` scheme, which routes SQLAlchemy to the sync `psycopg2` driver instead of `asyncpg`. Phase 0's `.env` template used this scheme, and nothing before Phase 3 actually connected to the database, so it stayed invisible | Change `DATABASE_URL` in both `.env` and `.env.example` to use `postgresql+asyncpg://`. Verify with `python -c "from autoeval_ops.config import settings; print(settings.database_url)"` |
| `ImportError: email-validator is not installed, run 'pip install pydantic[email]'` when collecting tests | `schemas.py`'s `UserCreate.email: EmailStr` requires the optional `email-validator` package, which isn't bundled with base `pydantic` | Add `email-validator==2.1.0` to `requirements.txt`, reinstall (already included above) |
| A test expecting `422` on a bad path parameter (e.g. an invalid UUID) instead gets `401` | A `Depends()` that raises `HTTPException` (like `get_current_user`) fires as a real exception during dependency resolution and propagates immediately - it short-circuits before FastAPI finishes assembling the automatic `422` for path/query validation. This is standard FastAPI behavior, not an app bug | Use a dependency override that bypasses auth (see `authenticated_client` in Task 12.5) to test path/query validation in isolation from auth |
| `UserWarning: Field "model_name" has conflict with protected namespace "model_"` | Pydantic v2 reserves the `model_` prefix for its own internals (`model_config`, `model_fields`, etc.); `EvaluationRead.model_name` collides with it | Add `protected_namespaces=()` to `ORMModel`'s `model_config` (Task 5, already included above) |
| `ModuleNotFoundError: No module named 'greenlet'` when running async DB code | SQLAlchemy's async engine needs `greenlet` on Windows and doesn't always pull it in automatically | It's in `requirements.txt` for this phase — re-run `pip install -r requirements.txt` |
| `alembic revision --autogenerate` produces an empty migration | `alembic/env.py` isn't importing your models, so `Base.metadata` is empty | Recheck Step 4.2 — `env.py` must import `Base` from `autoeval_ops.db.models` and set `target_metadata = Base.metadata` |
| `alembic check` fails with "Target database is not up to date" | Ran before `alembic stamp head` — `check` first verifies the DB's recorded migration version matches `head`; with nothing stamped yet, there's no recorded version at all, so it fails regardless of whether the models themselves are correct | Run `alembic stamp head` first, then `alembic check` — order matters here |
| `alembic upgrade head` fails with "relation already exists" | The tables were created by Phase 0's `schema.sql`, so the baseline migration is trying to re-create them | Use `alembic stamp head` (Step 4.3) to mark the baseline as applied without running it |
| Integration tests fail with connection refused | Postgres isn't running | `docker-compose up -d` from the repo root, confirm with `docker-compose ps` |
| Integration tests pass individually but fail together | Leftover rows from a previous test | The `db_session` fixture rolls back per test — confirm your test uses that fixture rather than creating its own session |
| Webhook fires, PR comment posts, but no evaluation row appears | The repo isn't registered as a project — this is intentional | Register it via `POST /api/v1/projects` (Task 15.3). Check the uvicorn terminal for the "not a registered project" log line |
| `sqlalchemy.exc.MissingGreenlet` in tests | An async DB call happened outside an async context, often from lazy-loading a relationship after the session closed | Use `selectinload` (as `get_evaluation_detail` does) to eager-load relationships you'll access later |

## PowerShell Notes
- All backend commands assume you're inside `backend/` with `.venv` activated, unless a step says otherwise.
- Docker must be running for integration tests and for Tasks 15-16; the fast unit suite (`pytest -m "not integration"`) doesn't need it.
- Keep the uvicorn and `cloudflared` terminals in separate tabs during Task 16.
- `notepad <file>` + paste remains the reliable way to get code into files.
