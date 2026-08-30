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
    Trace,
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

async def create_user(db: AsyncSession, email: str, api_key_hash: str | None = None) -> User:
    user = User(email=email, api_key_hash=api_key_hash)
    db.add(user)
    await db.flush()
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_or_create_user_by_email(db: AsyncSession, email: str) -> User:
    """Look up a user by email, provisioning one with no API key if none
    exists yet. Used for Clerk-authenticated logins, which never go through
    the manual POST /api/v1/users registration flow."""
    user = await get_user_by_email(db, email)
    if user is not None:
        return user
    return await create_user(db, email=email)


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

async def create_trace(
    db: AsyncSession,
    eval_id: uuid.UUID,
    trace_data: dict[str, Any],
    latency_ms: int,
    cost_usd: float,
) -> Trace:
    trace = Trace(
        eval_id=eval_id,
        trace_data=trace_data,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
    db.add(trace)
    await db.flush()
    return trace