"""
/api/v1/workflows — REST surface for workflow CRUD + manual run trigger.

The execution pipeline (worker, executor, Redis pub/sub, WS /api/v1/ws/runs) already exists
and runs in production, driven today only by webhook/scheduler triggers (see
app/routes/webhooks/webhook_inbound.py). This router is the missing HTTP surface for the
Flow Designer / Tasks dashboard: list/create/edit/delete workflows and list/trigger runs.

All endpoints are scoped to the authenticated user — no cross-user access.
Router is mounted with prefix "/api/v1/workflows" in main.py; paths below are relative to that.

Endpoints:
  GET    /            — List the authenticated user's workflows
  POST   /            — Create a blank workflow
  GET    /{id}        — Get a single workflow by id
  PATCH  /{id}        — Partial update (name/description/status/steps/trigger/...)
  DELETE /{id}        — Delete a workflow
  GET    /{id}/runs   — List runs for a workflow
  POST   /{id}/runs   — Trigger a manual run
"""

import logging

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import get_current_user
from app.services import workflow_service
from app.services.workflow_analytics_service import get_workflow_cards
from app.services.workflow_run_service import create_run, list_user_runs, ConcurrentRunLimitExceededError

logger = logging.getLogger(__name__)
router = APIRouter()


# ── GET / ────────────────────────────────────────────────────────────────────


@router.get("")
async def list_workflows(
    request: Request,
    current_user: dict = Depends(get_current_user),
    board_id: str | None = Query(None),
    workspace_id: str | None = Query(None),
):
    """Lists all workflows for the authenticated user, most recently updated first. Optionally filtered by board_id or workspace_id."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    workflows = await workflow_service.list_user_workflows(
        user_id, db, board_id=board_id, workspace_id=workspace_id,
    )
    return JSONResponse(content=jsonable_encoder({"workflows": workflows, "total": len(workflows)}))


# ── POST / ───────────────────────────────────────────────────────────────────


class WorkflowCreateRequest(BaseModel):
    name: str = "Nuevo workflow"
    description: str = ""
    workspace_id: str | None = None
    board_id: str | None = None


@router.post("", status_code=201)
async def create_workflow_endpoint(
    body: WorkflowCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Creates a blank workflow (Flow Designer 'new workflow'). Enforces the plan's max_workflows."""
    user_id = current_user.get("id", "")
    user_email = current_user.get("email") or current_user.get("correo", "")
    db = request.app.state.db

    try:
        workflow_id = await workflow_service.create_blank_workflow(
            user_id=user_id,
            user_email=user_email,
            name=body.name,
            description=body.description,
            db=db,
            workspace_id=body.workspace_id,
            board_id=body.board_id,
        )
    except workflow_service.WorkflowLimitExceededError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    workflow = await workflow_service.get_workflow_by_id(user_id, workflow_id, db)
    return JSONResponse(status_code=201, content=jsonable_encoder({"workflow": workflow}))


# ── GET /{id} ────────────────────────────────────────────────────────────────


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Gets a single workflow by id, scoped to the authenticated user."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    workflow = await workflow_service.get_workflow_by_id(user_id, workflow_id, db)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return JSONResponse(content=jsonable_encoder({"workflow": workflow}))


# ── PATCH /{id} ──────────────────────────────────────────────────────────────


class WorkflowUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    steps: list[dict] | None = None
    trigger_type: str | None = None
    trigger_config: dict | None = None
    workspace_id: str | None = None
    board_id: str | None = None
    frequency_type: str | None = None
    every_seconds: int | None = None
    frequency_label: str | None = None
    webhook_url: str | None = None
    metrics: list[dict] | None = None


@router.patch("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    body: WorkflowUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Partial update of a workflow. If `steps` is included, enforces max_apps_per_workflow."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    update_fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields were provided to update.")

    try:
        result = await workflow_service.update_workflow_fields(user_id, workflow_id, update_fields, db)
    except workflow_service.WorkflowAppsLimitExceededError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    workflow = await workflow_service.get_workflow_by_id(user_id, workflow_id, db)
    return JSONResponse(content=jsonable_encoder({"workflow": workflow}))


# ── DELETE /{id} ─────────────────────────────────────────────────────────────


@router.delete("/{workflow_id}")
async def delete_workflow_endpoint(
    workflow_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Deletes a workflow owned by the authenticated user."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    deleted = await workflow_service.delete_workflow(user_id, workflow_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return JSONResponse(content={"status": "deleted", "workflow_id": workflow_id})


# ── GET /{id}/runs ───────────────────────────────────────────────────────────


@router.get("/{workflow_id}/runs")
async def list_workflow_runs(
    workflow_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lists runs for a single workflow, scoped to the authenticated user."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    runs = await list_user_runs(user_id, db, workflow_id=workflow_id)
    return JSONResponse(content=jsonable_encoder({"runs": runs, "total": len(runs)}))


# ── POST /{id}/runs ──────────────────────────────────────────────────────────


@router.post("/{workflow_id}/runs", status_code=202)
async def trigger_workflow_run(
    workflow_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Triggers a manual run of a workflow. Unlike the webhook trigger, this does NOT require
    status == "active" — clicking "Ejecutar" is explicit user intent.

    create_run() is the only dispatcher (pushes to the Redis stream); the worker picks it up
    via claim_queued_run(). Do NOT also asyncio.create_task a WorkflowExecutor here — that
    pattern in webhook_inbound.py is a known double-execution bug, not something to copy.
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    wf = await db["workflows"].find_one({"_id": oid, "user_id": user_id})
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    steps = wf.get("steps") or []
    if not steps:
        raise HTTPException(status_code=400, detail="Workflow has no steps to run.")

    user_email = current_user.get("email") or current_user.get("correo", "") or wf.get("user_email", "")

    try:
        run_id = await create_run(
            workflow_id=workflow_id,
            workflow_name=wf.get("name", ""),
            user_id=user_id,
            user_email=user_email,
            steps=steps,
            db=db,
        )
    except ConcurrentRunLimitExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    logger.info("[Workflows] manual run triggered workflow=%s run=%s", workflow_id, run_id)
    return JSONResponse(
        status_code=202,
        content=jsonable_encoder({"status": "accepted", "run_id": run_id, "workflow_id": workflow_id}),
    )


# ── GET /{id}/analytics ──────────────────────────────────────────────────────


@router.get("/{workflow_id}/analytics")
async def get_workflow_analytics_cards(
    workflow_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Returns frontend-ready Card[] for a workflow's analytics (used by the grafica node)."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    wf = await db["workflows"].find_one({"_id": oid, "user_id": user_id})
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    cards = await get_workflow_cards(workflow_id, db)
    return JSONResponse(content=jsonable_encoder({"cards": cards}))
