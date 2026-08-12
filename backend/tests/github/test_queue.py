import asyncio

from autoeval_ops.github.queue import EvaluationQueue, EvalJob


def _job(n: int) -> EvalJob:
    return EvalJob(installation_id=1, owner="o", repo="r", pr_number=n, head_sha="abc")


async def test_queue_processes_enqueued_jobs():
    processed = []

    async def handler(job: EvalJob) -> None:
        processed.append(job.pr_number)

    queue = EvaluationQueue(worker_count=2)
    queue.start(handler)
    await queue.enqueue(_job(1))
    await queue.enqueue(_job(2))
    await queue.queue.join()
    await queue.stop()

    assert sorted(processed) == [1, 2]


async def test_queue_worker_survives_handler_exception():
    processed = []

    async def handler(job: EvalJob) -> None:
        if job.pr_number == 1:
            raise ValueError("boom")
        processed.append(job.pr_number)

    queue = EvaluationQueue(worker_count=1)
    queue.start(handler)
    await queue.enqueue(_job(1))  # this one raises
    await queue.enqueue(_job(2))  # worker must still process this one
    await queue.queue.join()
    await queue.stop()

    assert processed == [2]


async def test_stop_cancels_workers():
    async def handler(job: EvalJob) -> None:
        await asyncio.sleep(10)

    queue = EvaluationQueue(worker_count=2)
    queue.start(handler)
    await queue.stop()
    assert queue._workers == []