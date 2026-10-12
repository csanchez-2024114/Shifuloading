"""
WorkflowRun Service — CRUD for the `workflow_runs` MongoDB collection.
Each document tracks a single execution of a workflow with per-step status.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.constants import Collections
from app.billing.plans import get_plan_rules

logger = logging.getLogger(__name__)

WORKFLOW_RUNS = "workflow_runs"
_STREAM_KEY = "workflow:runs"
_redis = None  # set via set_stream_client() from main.py lifespan


class ConcurrentRunLimitExceededError(Exception):
    """User already has `limit` workflow(s) queued/running — plan doesn't allow more at once."""
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Limite de ejecuciones simultaneas del plan alcanzado ({limit}).")


def set_stream_client(client) -> None:
    """Call once from lifespan after Redis connects. Enables sub-second run dispatch."""
    global _redis
    _redis = client


async def _publish_to_stream(run_id: str) -> None:
    try:
        await _redis.xadd(_STREAM_KEY, {"run_id": run_id})
    except Exception as exc:
        logger.warning("[workflow_run_service] Redis XADD failed (non-fatal): %s", exc)


async def create_run(
    workflow_id: str,
    workflow_name: str,
    user_id: str,
    user_email: str,
    steps: List[Dict[str, Any]],
    db: AsyncIOMotorDatabase,
    priority: int = 2,
    simulate: bool = False,
    trigger: str = "manual",
    trigger_payload: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Creates a queued workflow run with all steps in 'pending' status.

    priority (DoD item 5 — Priority Queue):
      1 = urgent   — claimed before normal and low-priority runs
      2 = normal   — default
      3 = low      — claimed last; useful for background/batch workflows
    WorkflowWorker.claim_queued_run() sorts by (priority ASC, created_at ASC).
    """
    now = datetime.now(timezone.utc)
    # Se copia el paso completo (function_id, type, source, then_step, max_retries, compensation_action...):
    # el ejecutor lee esos campos del run, no del workflow, y antes se perdian aqui.
    run_steps = [
        {
            **{k: v for k, v in s.items() if k not in ("status", "result", "error", "started_at", "finished_at")},
            "order": s.get("order", i + 1),
            "name": s.get("name", f"Paso {i + 1}"),
            "app": s.get("app", ""),
            "action": s.get("action", ""),
            "account_id": s.get("account_id", ""),
            "config": s.get("config", {}),
            "status": "pending",
            "result": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        for i, s in enumerate(steps)
    ]

    # Check concurrent run limit before creating
    try:
        user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
        plan = (user_doc or {}).get("plan", "free")
        limit = get_plan_rules(plan).get("max_concurrent_runs", 1)
        if limit != -1:
            active_count = await db[WORKFLOW_RUNS].count_documents(
                {"user_id": user_id, "status": {"$in": ["queued", "running"]}}
            )
            if active_count >= limit:
                raise ConcurrentRunLimitExceededError(limit)
    except ConcurrentRunLimitExceededError:
        raise
    except Exception:
        pass  # Don't block run creation if the limit check itself fails

    doc = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "user_id": user_id,
        "user_email": user_email,
        "status": "queued",
        "priority": max(1, min(3, int(priority))),
        "steps": run_steps,
        # True: los pasos con function_id devuelven el ejemplo de su ficha y no llaman a la app externa.
        "simulate": bool(simulate),
        # Quien lo disparo (manual | schedule | webhook) y, si hubo, el JSON recibido: alimenta {{trigger.campo}}.
        "trigger": trigger,
        "trigger_payload": trigger_payload,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    # Denormalize workspace_id and board_id from the workflow document so analytics
    # can filter by board without an extra lookup per query.
    try:
        wf = await db["workflows"].find_one(
            {"_id": ObjectId(workflow_id)}, {"workspace_id": 1, "board_id": 1}
        )
        if wf:
            doc["workspace_id"] = wf.get("workspace_id")
            doc["board_id"] = wf.get("board_id")
    except Exception:
        pass
    result = await db[WORKFLOW_RUNS].insert_one(doc)
    run_id = str(result.inserted_id)
    if _redis:
        asyncio.create_task(_publish_to_stream(run_id))
    return run_id


async def get_run(run_id: str, db: AsyncIOMotorDatabase) -> Optional[dict]:
    """Loads a single workflow run by ID."""
    try:
        oid = ObjectId(run_id)
    except InvalidId:
        return None
    doc = await db[WORKFLOW_RUNS].find_one({"_id": oid})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def update_run_status(
    run_id: str,
    status: str,
    db: AsyncIOMotorDatabase,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Updates run status and optional extra fields."""
    try:
        oid = ObjectId(run_id)
    except InvalidId:
        return False
    fields: Dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc)}
    if extra:
        fields.update(extra)
    result = await db[WORKFLOW_RUNS].update_one({"_id": oid}, {"$set": fields})
    return result.modified_count > 0


async def update_step_status(
    run_id: str,
    step_order: int,
    status: str,
    db: AsyncIOMotorDatabase,
    result: Optional[str] = None,
    error: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> bool:
    """Updates a single step's status using MongoDB positional operator."""
    try:
        oid = ObjectId(run_id)
    except InvalidId:
        return False
    step_fields: Dict[str, Any] = {
        "steps.$.status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if result is not None:
        step_fields["steps.$.result"] = result
    if error is not None:
        step_fields["steps.$.error"] = error
    if started_at is not None:
        step_fields["steps.$.started_at"] = started_at
    if finished_at is not None:
        step_fields["steps.$.finished_at"] = finished_at

    db_result = await db[WORKFLOW_RUNS].update_one(
        {"_id": oid, "steps.order": step_order},
        {"$set": step_fields},
    )
    return db_result.modified_count > 0


async def claim_queued_run(db: AsyncIOMotorDatabase) -> Optional[dict]:
    """
    Atomically claims one queued run by setting it to 'running'.
    Prevents double-execution in concurrent environments.

    Sort order: (priority ASC, created_at ASC) — urgent runs (priority=1)
    are claimed before normal (2) and low-priority (3) ones. Within the same
    priority level, FIFO ordering applies.
    """
    now = datetime.now(timezone.utc)
    doc = await db[WORKFLOW_RUNS].find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "running", "started_at": now, "updated_at": now}},
        sort=[("priority", 1), ("created_at", 1)],
        return_document=True,
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def claim_run_by_id(run_id: str, db: AsyncIOMotorDatabase) -> Optional[dict]:
    """Como claim_queued_run pero para un run concreto (ejecucion inmediata): si un worker lo tomo antes, devuelve None."""
    try:
        oid = ObjectId(run_id)
    except InvalidId:
        return None
    now = datetime.now(timezone.utc)
    doc = await db[WORKFLOW_RUNS].find_one_and_update(
        {"_id": oid, "status": "queued"},
        {"$set": {"status": "running", "started_at": now, "updated_at": now}},
        return_document=True,
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def list_user_runs(
    user_id: str,
    db: AsyncIOMotorDatabase,
    limit: int = 20,
    workflow_id: Optional[str] = None,
) -> List[dict]:
    """Lists recent workflow runs for a user. Optionally filtered to a single workflow_id."""
    query: Dict[str, Any] = {"user_id": user_id}
    if workflow_id:
        query["workflow_id"] = workflow_id
    docs = await (
        db[WORKFLOW_RUNS]
        .find(query)
        .sort("created_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return [
        {
            "id": str(d["_id"]),
            "workflow_id": d.get("workflow_id", ""),
            "workflow_name": d.get("workflow_name", ""),
            "status": d.get("status", "queued"),
            "steps": [
                {
                    "order": s.get("order"),
                    "name": s.get("name"),
                    "app": s.get("app"),
                    "action": s.get("action"),
                    "status": s.get("status", "pending"),
                    "result": s.get("result"),
                    "error": s.get("error"),
                    "started_at": s["started_at"].isoformat() if s.get("started_at") else None,
                    "finished_at": s["finished_at"].isoformat() if s.get("finished_at") else None,
                }
                for s in sorted(d.get("steps", []), key=lambda x: x.get("order", 0))
            ],
            "error": d.get("error"),
            "created_at": d["created_at"].isoformat() if d.get("created_at") else "",
            "started_at": d["started_at"].isoformat() if d.get("started_at") else None,
            "finished_at": d["finished_at"].isoformat() if d.get("finished_at") else None,
        }
        for d in docs
    ]
