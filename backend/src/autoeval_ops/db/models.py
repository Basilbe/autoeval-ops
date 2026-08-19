"""SQLAlchemy ORM models mirroring the schema created in Phase 0.

Column types and defaults deliberately match backend/db/schema.sql so the
ORM and the live database stay in agreement.
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