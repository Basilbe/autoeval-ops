"""Aggregate metrics for the public status page.

Computed from Postgres on each request rather than held in memory, so
restarts don't zero the numbers. At current volume a live query is
cheap; revisit with a rollup table if evaluation counts grow large.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autoeval_ops.db.models import Evaluation, Trace


@dataclass
class StatusMetrics:
    total_evaluations: int = 0
    evaluations_24h: int = 0
    pass_rate: float = 0.0
    error_rate: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    avg_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    status_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total_evaluations": self.total_evaluations,
            "evaluations_24h": self.evaluations_24h,
            "pass_rate": round(self.pass_rate, 4),
            "error_rate": round(self.error_rate, 4),
            "latency": {
                "p50_ms": round(self.latency_p50_ms, 2),
                "p95_ms": round(self.latency_p95_ms, 2),
                "p99_ms": round(self.latency_p99_ms, 2),
            },
            "cost": {
                "avg_usd": round(self.avg_cost_usd, 6),
                "total_usd": round(self.total_cost_usd, 6),
            },
            "status_counts": self.status_counts,
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Deliberately simple - no numpy dependency
    for what is a handful of arithmetic operations."""
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, int(round(pct * len(sorted_values) + 0.5)) - 1))
    return sorted_values[index]


async def collect_status_metrics(db: AsyncSession) -> StatusMetrics:
    metrics = StatusMetrics()

    total = await db.execute(select(func.count()).select_from(Evaluation))
    metrics.total_evaluations = total.scalar_one()

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    recent = await db.execute(
        select(func.count()).select_from(Evaluation).where(Evaluation.created_at >= cutoff)
    )
    metrics.evaluations_24h = recent.scalar_one()

    status_rows = await db.execute(
        select(Evaluation.status, func.count()).group_by(Evaluation.status)
    )
    counts = {status: count for status, count in status_rows.all() if status}
    metrics.status_counts = counts

    completed = sum(counts.values())
    if completed:
        metrics.pass_rate = counts.get("pass", 0) / completed
        metrics.error_rate = counts.get("failed", 0) / completed

    latency_rows = await db.execute(
        select(Trace.latency_ms).where(Trace.latency_ms.is_not(None)).order_by(Trace.latency_ms)
    )
    latencies = [float(v) for v in latency_rows.scalars().all()]
    if latencies:
        metrics.latency_p50_ms = _percentile(latencies, 0.50)
        metrics.latency_p95_ms = _percentile(latencies, 0.95)
        metrics.latency_p99_ms = _percentile(latencies, 0.99)

    cost_rows = await db.execute(
        select(func.avg(Trace.cost_usd), func.sum(Trace.cost_usd)).where(
            Trace.cost_usd.is_not(None)
        )
    )
    avg_cost, total_cost = cost_rows.one()
    metrics.avg_cost_usd = float(avg_cost or 0.0)
    metrics.total_cost_usd = float(total_cost or 0.0)

    return metrics