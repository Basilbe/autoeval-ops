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