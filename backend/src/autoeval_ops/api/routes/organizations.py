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