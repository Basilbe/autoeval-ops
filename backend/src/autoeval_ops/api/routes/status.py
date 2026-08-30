"""Public status endpoint - deliberately unauthenticated.

This is the only route in the API without an auth dependency. It exposes
aggregate operational metrics only: counts, percentiles, and costs. No
project names, repo URLs, prompt contents, user emails, or per-evaluation
detail - nothing that identifies a customer or leaks evaluation content.
"""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.db.session import get_db
from autoeval_ops.observability.metrics import collect_status_metrics

router = APIRouter(prefix="/api/v1", tags=["status"])

_STARTED_AT = datetime.now(timezone.utc)


@router.get("/status")
async def public_status(db: AsyncSession = Depends(get_db)) -> dict:
    metrics = await collect_status_metrics(db)
    uptime_seconds = (datetime.now(timezone.utc) - _STARTED_AT).total_seconds()
    return {
        "service": "AutoEvalOps",
        "status": "operational",
        "uptime_seconds": int(uptime_seconds),
        "metrics": metrics.as_dict(),
    }