"""
Inbound webhook endpoint — public receiver for external system events.

POST /api/v4/webhooks/{webhook_token}
  No auth required — the webhook_token IS the authentication secret.
  Finds the workflow by token, creates a run, and executes it asynchronously.
  Responds immediately with 202 Accepted + run_id.

The webhook_token is set when a workflow's trigger_type is configured to "webhook"
via POST /api/v3/agent/workflows/{id}/webhook.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.services.workflow_run_service import create_run, ConcurrentRunLimitExceededError

logger = logging.getLogger(__name__)
router = APIRouter()

_COL_WEBHOOK_EVENTS = "webhook_events"


@router.post("/webhooks/{webhook_token}", status_code=202)
async def inbound_webhook(webhook_token: str, request: Request):
    """
    Receives an external POST and fires the linked workflow.
    The request body (JSON) is persisted to webhook_events for audit.
    """
    db = request.app.state.db

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    wf = await db["workflows"].find_one(
        {"webhook_token": webhook_token, "status": "active"}
    )
    if not wf:
        raise HTTPException(
            status_code=404,
            detail="Webhook token not found or workflow is not active.",
        )

    wf_id = str(wf["_id"])
    user_id = wf.get("user_id", "")
    user_email = wf.get("user_email", "")

    await db[_COL_WEBHOOK_EVENTS].insert_one(
        {
            "workflow_id": wf_id,
            "user_id": user_id,
            "webhook_token": webhook_token,
            "payload": payload,
            "received_at": datetime.now(timezone.utc),
        }
    )

    try:
        run_id = await create_run(
            workflow_id=wf_id,
            workflow_name=wf.get("name", ""),
            user_id=user_id,
            user_email=user_email,
            steps=wf.get("steps", []),
            db=db,
        )
    except ConcurrentRunLimitExceededError:
        logger.info("[WebhookInbound] Skipping run for workflow %s — concurrent limit reached", wf_id)
        return JSONResponse(
            status_code=429,
            content=jsonable_encoder({"status": "skipped", "reason": "concurrent_run_limit", "workflow_id": wf_id}),
        )

    # create_run() queues the run for workflow_worker (Redis stream + polling
    # fallback), which claims it atomically via claim_queued_run() — executing it
    # here too would be a double-execution race (see workflow_worker.py docstring).
    logger.info(
        "[WebhookInbound] token=%s workflow=%s run=%s", webhook_token, wf_id, run_id
    )
    return JSONResponse(
        status_code=202,
        content=jsonable_encoder(
            {
                "status": "accepted",
                "run_id": run_id,
                "workflow_id": wf_id,
            }
        ),
    )
