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