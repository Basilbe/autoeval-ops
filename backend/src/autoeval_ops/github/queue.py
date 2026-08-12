"""In-process asyncio-based queue for evaluation jobs. Deferred to a proper
broker (Celery+Redis) in a later phase per TECH_STACK.md - sufficient for a
single backend instance."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class EvalJob:
    installation_id: int
    owner: str
    repo: str
    pr_number: int
    head_sha: str


class EvaluationQueue:
    def __init__(self, worker_count: int = 3):
        self.queue: asyncio.Queue[EvalJob] = asyncio.Queue()
        self.worker_count = worker_count
        self._workers: list[asyncio.Task] = []

    async def enqueue(self, job: EvalJob) -> None:
        await self.queue.put(job)

    def start(self, handler: Callable[[EvalJob], Awaitable[None]]) -> None:
        self._workers = [
            asyncio.create_task(self._worker(handler)) for _ in range(self.worker_count)
        ]

    async def _worker(self, handler: Callable[[EvalJob], Awaitable[None]]) -> None:
        while True:
            job = await self.queue.get()
            try:
                await handler(job)
            except Exception as exc:  # keep the worker alive on a single bad job
                print(f"AutoEvalOps job failed: {job} - {exc}")
            finally:
                self.queue.task_done()

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        self._workers = []


eval_queue = EvaluationQueue(worker_count=3)