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