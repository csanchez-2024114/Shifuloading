"""
Workflow Service — CRUD for the `workflows` MongoDB collection.
Manages workflow definitions with state machine transitions.

States: creating → active → paused → deactivated | requires_attention
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.constants import Collections
from app.billing.plans import get_plan_rules

WORKFLOWS = "workflows"
_ACTIVE_STATUSES = ("active", "paused", "requires_attention")


class WorkflowLimitExceededError(Exception):
    """Se alcanzó el máximo de workflows activos permitido por el plan del usuario."""

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Límite de workflows del plan alcanzado ({limit}).")


class WorkflowAppsLimitExceededError(Exception):
    """Se alcanzó el máximo de apps distintas permitido dentro de un mismo workflow."""

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Límite de apps por workflow alcanzado ({limit}).")


async def _build_workflow_metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
    steps = doc.get("steps", []) or []
    actions = [s.get("action") for s in steps if s.get("action")]
    return {
        "steps_count": len(steps),
        "has_steps": bool(steps),
        "last_step_order": max((s.get("order", 0) for s in steps), default=0),
        "step_names": [s.get("name") for s in steps if s.get("name")],
        "step_actions": actions,
        "status": doc.get("status"),
        "trigger_type": doc.get("trigger_type"),
        "frequency_type": doc.get("frequency_type"),
        "workflow_name": doc.get("name"),
    }


async def _bump_version(workflow_id: str, db: AsyncIOMotorDatabase) -> None:
    """Increments workflow_version and pushes a snapshot to version_history (capped at 10)."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return
    doc = await db[WORKFLOWS].find_one({"_id": oid}, {"steps": 1, "name": 1, "description": 1, "workflow_version": 1})
    if not doc:
        return
    current_version = doc.get("workflow_version", 1)
    snapshot = {
        "version": current_version,
        "archived_at": datetime.now(timezone.utc),
        "name": doc.get("name"),
        "description": doc.get("description"),
        "steps": doc.get("steps", []),
    }
    await db[WORKFLOWS].update_one(
        {"_id": oid},
        {
            "$inc": {"workflow_version": 1},
            "$push": {"version_history": {"$each": [snapshot], "$slice": -10}},
        },
    )


async def _sync_workflow_metadata(workflow_id: str, db: AsyncIOMotorDatabase) -> bool:
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    doc = await db[WORKFLOWS].find_one({"_id": oid})
    if not doc:
        return False
    generated_metadata = await _build_workflow_metadata(doc)
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {
            "$set": {
                "metadata": generated_metadata,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


async def update_workflow_metadata(
    workflow_id: str,
    metadata: Dict[str, Any],
    db: AsyncIOMotorDatabase,
    merge: bool = True,
) -> bool:
    """Adds or updates workflow metadata. If merge=True it updates nested fields."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    if merge:
        set_fields = {f"metadata.{k}": v for k, v in metadata.items()}
        set_fields["updated_at"] = datetime.now(timezone.utc)
        result = await db[WORKFLOWS].update_one({"_id": oid}, {"$set": set_fields})
    else:
        result = await db[WORKFLOWS].update_one(
            {"_id": oid},
            {"$set": {"metadata": metadata, "updated_at": datetime.now(timezone.utc)}},
        )
    return result.modified_count > 0


async def create_workflow(
    user_id: str,
    user_email: str,
    name: str,
    description: str,
    conversation_id: str,
    db: AsyncIOMotorDatabase,
) -> str:
    """
    Creates a workflow draft — or resets the existing one for this conversation.
    Upsert pattern: one 'creating' document per conversation at most.
    Returns the workflow ID as string.
    """
    now = datetime.now(timezone.utc)

    existing = await get_current_draft(user_id, conversation_id, db)
    if existing:
        fields: Dict[str, Any] = {
            "name": name,
            "description": description,
            "updated_at": now,
        }
        # Only wipe steps when the draft is truly empty (avoid clearing a workflow loaded for editing)
        if not existing.get("steps"):
            fields["steps"] = []
        await db[WORKFLOWS].update_one(
            {"_id": ObjectId(existing["_id"])}, {"$set": fields}
        )
        await _sync_workflow_metadata(existing["_id"], db)
        return existing["_id"]

    try:
        user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
    except InvalidId:
        user_doc = None
    plan = (user_doc or {}).get("plan", "free")
    limit = get_plan_rules(plan).get("max_workflows", 1)
    if limit != -1:
        active_count = await db[WORKFLOWS].count_documents(
            {"user_id": user_id, "status": {"$in": list(_ACTIVE_STATUSES)}}
        )
        if active_count >= limit:
            raise WorkflowLimitExceededError(limit)

    doc = {
        "user_id": user_id,
        "user_email": user_email,
        "name": name,
        "description": description,
        "metadata": {},
        "status": "creating",
        "trigger_type": "manual",
        "trigger_config": {},
        "steps": [],
        "conversation_id": conversation_id,
        # Frequency intent — set by Shifu during Phase 1 via set_workflow_frequency()
        "frequency_type": None,  # e.g. "daily", "hourly", "once", "weekly"
        "every_seconds": None,  # derived numeric value
        "frequency_label": None,  # human-readable, e.g. "Cada día"
        "workflow_version": 1,
        "version_history": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await db[WORKFLOWS].insert_one(doc)
    workflow_id = str(result.inserted_id)
    await _sync_workflow_metadata(workflow_id, db)
    return workflow_id


async def create_blank_workflow(
    user_id: str,
    user_email: str,
    name: str,
    description: str,
    db: AsyncIOMotorDatabase,
    workspace_id: Optional[str] = None,
    board_id: Optional[str] = None,
) -> str:
    """
    Creates a blank workflow from the REST surface (Flow Designer "new workflow"), without
    the conversation_id/dedup semantics of create_workflow() (that one is for the AI chat
    flow — always insert a new document here, never upsert onto an existing draft).

    workspace_id and board_id are persisted on the workflow document so analytics can
    be filtered by board.
    """
    now = datetime.now(timezone.utc)

    try:
        user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
    except InvalidId:
        user_doc = None
    plan = (user_doc or {}).get("plan", "free")
    limit = get_plan_rules(plan).get("max_workflows", 1)
    if limit != -1:
        active_count = await db[WORKFLOWS].count_documents(
            {"user_id": user_id, "status": {"$in": list(_ACTIVE_STATUSES)}}
        )
        if active_count >= limit:
            raise WorkflowLimitExceededError(limit)

    doc = {
        "user_id": user_id,
        "user_email": user_email,
        "name": name,
        "description": description,
        "workspace_id": workspace_id,
        "board_id": board_id,
        "metadata": {},
        "status": "creating",
        "trigger_type": "manual",
        "trigger_config": {},
        "steps": [],
        "conversation_id": None,
        "frequency_type": None,
        "every_seconds": None,
        "frequency_label": None,
        "workflow_version": 1,
        "version_history": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await db[WORKFLOWS].insert_one(doc)
    workflow_id = str(result.inserted_id)
    await _sync_workflow_metadata(workflow_id, db)
    return workflow_id


_UPDATABLE_WORKFLOW_FIELDS = {
    "name",
    "description",
    "status",
    "steps",
    "trigger_type",
    "trigger_config",
    "workspace_id",
    "board_id",
    "frequency_type",
    "every_seconds",
    "frequency_label",
    "webhook_url",
    "metrics",
}


async def update_workflow_fields(
    user_id: str,
    workflow_id: str,
    fields: Dict[str, Any],
    db: AsyncIOMotorDatabase,
) -> Optional[bool]:
    """
    Partial update of a workflow, scoped to user_id (same pattern as update_workflow_status).
    Only keys in _UPDATABLE_WORKFLOW_FIELDS are persisted, everything else is dropped silently.

    If `steps` is included, validates max_apps_per_workflow (same check as add_step_to_workflow)
    against the distinct set of apps across the new steps before persisting.

    Returns True if a document was modified, False if the workflow exists but nothing changed,
    None if the workflow was not found for this user.
    """
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return None

    existing = await db[WORKFLOWS].find_one({"_id": oid, "user_id": user_id}, {"_id": 1})
    if not existing:
        return None

    update_fields = {k: v for k, v in fields.items() if k in _UPDATABLE_WORKFLOW_FIELDS}
    if not update_fields:
        return False

    if "steps" in update_fields:
        new_steps = update_fields["steps"] or []
        distinct_apps = {s.get("app") for s in new_steps if s.get("app")}
        if distinct_apps:
            user_doc = None
            if ObjectId.is_valid(user_id):
                user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
            plan = (user_doc or {}).get("plan", "free")
            limit = get_plan_rules(plan).get("max_apps_per_workflow", 1)
            if limit != -1 and len(distinct_apps) > limit:
                raise WorkflowAppsLimitExceededError(limit)

    update_fields["updated_at"] = datetime.now(timezone.utc)
    result = await db[WORKFLOWS].update_one({"_id": oid, "user_id": user_id}, {"$set": update_fields})
    if "steps" in update_fields or "name" in update_fields or "description" in update_fields:
        await _sync_workflow_metadata(workflow_id, db)
    return result.modified_count > 0


async def get_current_draft(
    user_id: str,
    conversation_id: str,
    db: AsyncIOMotorDatabase,
) -> Optional[dict]:
    """Finds the workflow draft linked to the current conversation."""
    cursor = (
        db[WORKFLOWS]
        .find(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "status": "creating",
            }
        )
        .sort("updated_at", -1)
        .limit(1)
    )
    docs = await cursor.to_list(length=1)
    if not docs:
        return None
    doc = docs[0]
    doc["_id"] = str(doc["_id"])
    return doc


async def get_workflow_by_id(
    user_id: str,
    workflow_id: str,
    db: AsyncIOMotorDatabase,
) -> Optional[dict]:
    """Loads a workflow by ID, scoped to the user."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return None
    doc = await db[WORKFLOWS].find_one({"_id": oid, "user_id": user_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def add_step_to_workflow(
    workflow_id: str,
    step: Dict[str, Any],
    db: AsyncIOMotorDatabase,
) -> bool:
    """Upserts a step by order: replaces if order exists, otherwise appends. Returns True on success."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False

    wf_doc = await db[WORKFLOWS].find_one({"_id": oid}, {"user_id": 1, "steps": 1})
    if not wf_doc:
        return False
    existing_steps = wf_doc.get("steps", []) or []
    is_new_order = not any(s.get("order") == step.get("order") for s in existing_steps)
    step_app = step.get("app")
    if is_new_order and step_app:
        existing_apps = {s.get("app") for s in existing_steps if s.get("app")}
        if step_app not in existing_apps:
            user_id = wf_doc.get("user_id", "")
            user_doc = None
            if ObjectId.is_valid(user_id):
                user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
            plan = (user_doc or {}).get("plan", "free")
            limit = get_plan_rules(plan).get("max_apps_per_workflow", 1)
            if limit != -1 and len(existing_apps) + 1 > limit:
                raise WorkflowAppsLimitExceededError(limit)

    now = datetime.now(timezone.utc)
    # Replace existing step with the same order (idempotent)
    result = await db[WORKFLOWS].update_one(
        {"_id": oid, "steps.order": step["order"]},
        {"$set": {"steps.$": step, "updated_at": now}},
    )
    if result.modified_count > 0:
        await _sync_workflow_metadata(workflow_id, db)
        await _bump_version(workflow_id, db)
        return True
    # No step with this order yet — append it
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {"$push": {"steps": step}, "$set": {"updated_at": now}},
    )
    if result.modified_count > 0:
        await _sync_workflow_metadata(workflow_id, db)
        await _bump_version(workflow_id, db)
    return result.modified_count > 0


async def set_workflow_frequency(
    workflow_id: str,
    frequency_type: str,
    every_seconds: Optional[int],
    frequency_label: str,
    db: AsyncIOMotorDatabase,
) -> bool:
    """Store the inferred frequency intent on a workflow draft."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {
            "$set": {
                "frequency_type": frequency_type,
                "every_seconds": every_seconds,
                "frequency_label": frequency_label,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


async def update_workflow_status(
    workflow_id: str,
    status: str,
    db: AsyncIOMotorDatabase,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Updates workflow status + optional extra fields. Returns True on success."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    fields: Dict[str, Any] = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if extra:
        fields.update(extra)
    result = await db[WORKFLOWS].update_one({"_id": oid}, {"$set": fields})
    if result.modified_count > 0 and status == "active":
        await _bump_version(workflow_id, db)
    return result.modified_count > 0


async def set_draft_conversation(
    workflow_id: str,
    conversation_id: str,
    db: AsyncIOMotorDatabase,
) -> bool:
    """Links an existing workflow to a conversation for editing (sets status → creating)."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {
            "$set": {
                "conversation_id": conversation_id,
                "status": "creating",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


async def set_webhook_trigger(
    workflow_id: str,
    db: AsyncIOMotorDatabase,
) -> Optional[str]:
    """
    Sets trigger_type='webhook' on a workflow and generates a unique webhook_token.
    Returns the token on success, None on failure.
    """
    from uuid import uuid4
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return None
    token = str(uuid4()).replace("-", "")
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {
            "$set": {
                "trigger_type": "webhook",
                "webhook_token": token,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return token if result.modified_count > 0 else None


async def list_user_workflows(
    user_id: str,
    db: AsyncIOMotorDatabase,
    limit: int = 20,
    board_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> List[dict]:
    """Lists all workflows for a user, sorted by most recently updated. Optionally filtered by board_id or workspace_id."""
    query: Dict[str, Any] = {"user_id": user_id}
    if board_id:
        query["board_id"] = board_id
    if workspace_id:
        query["workspace_id"] = workspace_id
    docs = await (
        db[WORKFLOWS]
        .find(query)
        .sort("updated_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return [
        {
            "id": str(d["_id"]),
            "name": d.get("name", "Sin nombre"),
            "description": d.get("description", ""),
            "status": d.get("status", "creating"),
            "steps_count": len(d.get("steps", [])),
            "trigger_type": d.get("trigger_type", "manual"),
            "frequency_type": d.get("frequency_type"),
            "every_seconds": d.get("every_seconds"),
            "frequency_label": d.get("frequency_label"),
            "workspace_id": d.get("workspace_id"),
            "board_id": d.get("board_id"),
            "created_at": d["created_at"].isoformat() if d.get("created_at") else "",
            "updated_at": d["updated_at"].isoformat() if d.get("updated_at") else "",
        }
        for d in docs
    ]


async def replace_step_in_workflow(
    workflow_id: str,
    step_order: int,
    new_step: Dict[str, Any],
    db: AsyncIOMotorDatabase,
) -> bool:
    """Replaces the step at step_order with new_step data. Uses positional operator."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    new_step["order"] = step_order
    result = await db[WORKFLOWS].update_one(
        {"_id": oid, "steps.order": step_order},
        {"$set": {"steps.$": new_step, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count > 0:
        await _sync_workflow_metadata(workflow_id, db)
    return result.modified_count > 0


async def delete_workflow(
    user_id: str,
    workflow_id: str,
    db: AsyncIOMotorDatabase,
) -> bool:
    """Permanently deletes a workflow owned by the given user."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    result = await db[WORKFLOWS].delete_one({"_id": oid, "user_id": user_id})
    return result.deleted_count > 0


async def remove_step_from_workflow(
    workflow_id: str,
    step_order: int,
    db: AsyncIOMotorDatabase,
) -> bool:
    """Removes the step with the given order number from a workflow."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {
            "$pull": {"steps": {"order": step_order}},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    if result.modified_count > 0:
        await _sync_workflow_metadata(workflow_id, db)
    return result.modified_count > 0


async def update_workflow_metrics(
    workflow_id: str,
    metrics: List[Dict[str, Any]],
    db: AsyncIOMotorDatabase,
) -> bool:
    """Sets the metrics extraction schema on a workflow (used by the executor for dashboard data)."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {"$set": {"metrics": metrics, "updated_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0


async def update_workflow_webhook(
    workflow_id: str,
    webhook_url: str,
    db: AsyncIOMotorDatabase,
) -> bool:
    """Sets the HTTP webhook URL called after each run completes."""
    try:
        oid = ObjectId(workflow_id)
    except InvalidId:
        return False
    result = await db[WORKFLOWS].update_one(
        {"_id": oid},
        {
            "$set": {
                "webhook_url": webhook_url,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.modified_count > 0


WORKFLOW_STATE = "workflow_state"


async def get_workflow_state(
    workflow_id: str, db: AsyncIOMotorDatabase
) -> Dict[str, Any]:
    """Returns the persisted state dict for a workflow (e.g. last_run_at). Empty dict if none."""
    doc = await db[WORKFLOW_STATE].find_one({"workflow_id": workflow_id})
    if not doc:
        return {}
    return {k: v for k, v in doc.items() if k not in ("_id", "workflow_id")}


async def save_workflow_state(
    workflow_id: str, state: Dict[str, Any], db: AsyncIOMotorDatabase
) -> None:
    """Upserts the state dict for a workflow. Merges with existing keys."""
    await db[WORKFLOW_STATE].update_one(
        {"workflow_id": workflow_id},
        {"$set": state},
        upsert=True,
    )
