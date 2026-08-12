"""GitHub webhook receiver: verifies signatures and enqueues evaluation jobs."""
from __future__ import annotations
import hashlib
import hmac

from fastapi import APIRouter, Request, HTTPException, Header

from autoeval_ops.github.queue import EvalJob, eval_queue
from autoeval_ops.config import settings

router = APIRouter()

RELEVANT_ACTIONS = {"opened", "synchronize", "reopened"}


def verify_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


@router.post("/github/webhook")
async def handle_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
) -> dict:
    body = await request.body()

    if not verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    payload = await request.json()
    action = payload.get("action")
    if action not in RELEVANT_ACTIONS:
        return {"status": "ignored", "reason": f"action={action}"}

    job = EvalJob(
        installation_id=payload["installation"]["id"],
        owner=payload["repository"]["owner"]["login"],
        repo=payload["repository"]["name"],
        pr_number=payload["pull_request"]["number"],
        head_sha=payload["pull_request"]["head"]["sha"],
    )
    await eval_queue.enqueue(job)

    return {"status": "queued", "pr": job.pr_number}