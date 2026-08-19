"""Pydantic request/response models. Deliberately separate from the ORM
models - these are the API's public contract and shouldn't leak internal
columns (e.g. github_token_encrypted, api_key_hash)."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
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