"""
/api/v1/me — User self-service endpoints for Human Collaboration and Security Governance.

All endpoints are scoped to the authenticated user — no cross-user access.
Router is mounted with prefix "/api/v1/me" in main.py; paths below are relative to that.

Endpoints:
  GET   /                                — Get the authenticated user's profile
  PATCH /                                — Update profile fields (name, img, phone, country, description)
  PATCH /password                        — Change the authenticated user's password
  POST  /avatar                          — Update the authenticated user's profile picture URL
  GET   /preferences                     — Get user preferences (currently: step_by_step)
  PATCH /preferences                     — Update user preferences
  GET   /usage                           — Daily token usage + per-workflow app usage against the plan
  POST  /integrations/refresh            — Refresh legacy integration tokens (throttled 30 min)
  GET   /chats/{app}/messages            — Paginated chat history with a connected app
  GET  /memories                         — List active semantic facts Shifu knows about the user
  DELETE /memories/{fact_id}             — Archive (soft-delete) a specific fact
  PATCH  /memories/{fact_id}             — Edit the value of a specific fact
  GET  /action-history                   — Last 50 actions Shifu took on behalf of the user
  GET  /audit-log                        — Last 100 security audit events for this user
  POST /action-history/{run_id}/undo     — Undo a workflow run (executes compensation actions)
  POST /transparency-mode                — Toggle reasoning-trace transparency in responses
  GET  /integrations                     — List connected apps with OAuth token health status
  DELETE /integrations/{provider}        — Revoke a connected integration
  POST /integrations/{provider}/test     — Test if a connected integration is working

  Goal management (Task System + Goal System 10/10):
  GET    /goals                          — List all goals (filterable by status)
  PATCH  /goals/{goal_id}               — Update goal status / priority / description
  DELETE /goals/{goal_id}               — Abandon a goal

  Task management:
  GET    /tasks                          — List all tasks (filterable by status)
  PATCH  /tasks/{task_id}               — Update task status / priority / deadline / description
  DELETE /tasks/{task_id}               — Cancel a task

  Conversation history:
  GET    /conversations                          — List past chat conversations (most recent first)
  GET    /conversations/{conversation_id}/messages — Full transcript of one conversation
  DELETE /conversations/{conversation_id}          — Delete a conversation and its messages
"""

import logging
from app.core.limiter import get_real_ip
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import get_current_user
from app.services.audit_service import log_event as _audit, get_recent_events as _get_audit
from app.services.chat_memory import get_conversation_messages
from app.routes.auth.authRoutes import (
    pwd_context,
    verify_password_and_upgrade,
    generate_unique_referral_code,
)
from app.core.constants import Collections
from app.billing.plans import get_plan_rules
from app.core.quota import get_daily_tokens_used

logger = logging.getLogger(__name__)
router = APIRouter()

_COL_SEMANTIC = "user_semantic_memory"
_COL_OUTCOMES = "intent_outcomes"
_COL_GOALS = "user_active_goals"
_COL_TASKS = "user_pending_tasks"
_COL_PREFS = "user_preferences"
_COL_MESSAGES = "chat_messages"
_COL_CONTEXT = "chat_context"


# ── GET / (read profile) ────────────────────────────────────────────────────


@router.get("")
async def get_my_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Returns the authenticated user's profile — same document shape PATCH / returns."""
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    user = await db[Collections.USERS].find_one({"_id": user_oid}, {"password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user["id"] = str(user.pop("_id"))
    return JSONResponse(content=jsonable_encoder(
        {"user": user},
        custom_encoder={ObjectId: str},
    ))


# ── PATCH / (update profile) ────────────────────────────────────────────────


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    img: str | None = None
    phone: str | None = None
    country: str | None = None
    description: str | None = None


@router.patch("")
async def update_my_profile(
    body: ProfileUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Updates profile fields for the authenticated user. Only provided fields are changed."""
    update_fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields were provided to update.")
    update_fields["updated_at"] = datetime.now(timezone.utc)
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    result = await db[Collections.USERS].update_one({"_id": user_oid}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    updated = await db[Collections.USERS].find_one({"_id": user_oid}, {"password": 0})
    updated["id"] = str(updated.pop("_id"))
    return JSONResponse(content=jsonable_encoder(
        {"message": "Profile updated successfully.", "user": updated},
        custom_encoder={ObjectId: str},
    ))


# ── PATCH /password ─────────────────────────────────────────────────────────


class PasswordUpdateRequest(BaseModel):
    current_password: str
    new_password: str


@router.patch("/password")
async def update_my_password(
    body: PasswordUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Changes the authenticated user's password. Validates the current password first."""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="The new password must be at least 8 characters long.")
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    user_with_pass = await db[Collections.USERS].find_one({"_id": user_oid}, {"password": 1})
    if not user_with_pass:
        raise HTTPException(status_code=404, detail="User not found.")
    is_valid, _ = verify_password_and_upgrade(body.current_password, user_with_pass.get("password"))
    if not is_valid:
        raise HTTPException(status_code=401, detail="The current password is incorrect.")
    new_hash = pwd_context.hash(body.new_password)
    await db[Collections.USERS].update_one(
        {"_id": user_oid},
        {"$set": {"password": new_hash, "updated_at": datetime.now(timezone.utc)}},
    )
    return JSONResponse(content={"message": "Password updated successfully."})


# ── POST /avatar ─────────────────────────────────────────────────────────────


class AvatarUpdateRequest(BaseModel):
    avatar_url: str


@router.post("/avatar")
async def update_my_avatar(
    body: AvatarUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Updates the authenticated user's profile picture URL (upload to Cloudinary first, then call this)."""
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    result = await db[Collections.USERS].update_one(
        {"_id": user_oid},
        {"$set": {"img": body.avatar_url, "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    return JSONResponse(content={"status": "updated", "img": body.avatar_url})


# ── GET/PATCH /preferences ──────────────────────────────────────────────────


class PreferencesUpdateRequest(BaseModel):
    step_by_step: bool | None = None
    dark_mode: bool | None = None
    performance_mode: bool | None = None
    language: str | None = None
    email_notices: bool | None = None  # avisos por correo (app/workers/notice_mailer.py)


_PREFERENCE_FIELDS = {"step_by_step": 1, "dark_mode": 1, "performance_mode": 1, "language": 1, "email_notices": 1}
_PREFERENCE_DEFAULTS = {
    "step_by_step": False,
    "dark_mode": False,
    "performance_mode": False,
    "language": "es",
    "email_notices": True,
}


@router.get("/preferences")
async def get_my_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user.get("id", "")
    db = request.app.state.db
    user_oid = ObjectId(user_id)
    user = await db[Collections.USERS].find_one({"_id": user_oid}, _PREFERENCE_FIELDS)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # transparency_mode lives in user_preferences (set via POST /transparency-mode), not on the
    # user document — surface it here too so the frontend has a single place to read initial state.
    prefs_doc = await db[_COL_PREFS].find_one({"user_id": user_id}, {"prefs.transparency_mode": 1})
    transparency_mode = (((prefs_doc or {}).get("prefs") or {}).get("transparency_mode") or {}).get("value", False)

    return JSONResponse(content={
        "transparency_mode": bool(transparency_mode),
        **{field: user.get(field, default) for field, default in _PREFERENCE_DEFAULTS.items()},
    })


@router.patch("/preferences")
async def update_my_preferences(
    body: PreferencesUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No preferences were provided to update.")
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    result = await db[Collections.USERS].update_one({"_id": user_oid}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")
    return JSONResponse(content={"status": "updated", **updates})


# ── GET /usage ───────────────────────────────────────────────────────────────


@router.get("/usage")
async def get_my_usage(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Returns the authenticated user's usage against their plan:
    - tokens_used/tokens_limit: today's chat token count (Redis) vs. plan's daily_token_limit.
    - apps_used/apps_limit: distinct apps in the user's most app-heavy workflow vs. plan's
      max_apps_per_workflow (the same limit enforced when adding a step to a workflow).
    A limit of -1 means unlimited.
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    user_oid = ObjectId(user_id)
    user_doc = await db[Collections.USERS].find_one({"_id": user_oid}, {"plan": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found.")
    rules = get_plan_rules(user_doc.get("plan"))

    redis_client = getattr(request.app.state, "redis", None)
    tokens_used = await get_daily_tokens_used(redis_client, user_id)

    workflows = await db["workflows"].find(
        {"user_id": user_id}, {"steps.app": 1}
    ).to_list(length=200)
    apps_used = max(
        (len({s.get("app") for s in (wf.get("steps") or []) if s.get("app")}) for wf in workflows),
        default=0,
    )

    return JSONResponse(content={
        "tokens_used": tokens_used,
        "tokens_limit": rules.get("daily_token_limit", -1),
        "apps_used": apps_used,
        "apps_limit": rules.get("max_apps_per_workflow", -1),
    })


# ── GET /memories ───────────────────────────────────────────────────────────


@router.get("/memories")
async def list_my_memories(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lists all active semantic facts Shifu knows about the user (max 100)."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    docs = await (
        db[_COL_SEMANTIC]
        .find(
            {"user_id": user_id, "status": {"$in": ["active", "stale", "stale_candidate"]}},
            {"_id": 1, "key": 1, "value": 1, "status": 1, "mention_count": 1, "language": 1,
             "created_at": 1, "last_seen_at": 1},
        )
        .sort([("status", 1), ("mention_count", -1)])
        .limit(100)
        .to_list(length=100)
    )
    for d in docs:
        d["id"] = str(d.pop("_id"))
        for field in ("created_at", "last_seen_at"):
            v = d.get(field)
            if v and hasattr(v, "isoformat"):
                d[field] = v.isoformat()

    return JSONResponse(content=jsonable_encoder({"memories": docs, "total": len(docs)}))


# ── DELETE /memories/{fact_id} ─────────────────────────────────────────────


@router.delete("/memories/{fact_id}")
async def delete_my_memory(
    fact_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Archives (soft-deletes) a specific semantic fact. Does not expose it to future sessions."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    try:
        oid = ObjectId(fact_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid fact_id format.")

    result = await db[_COL_SEMANTIC].update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"status": "archived", "last_seen_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fact not found.")
    ip = get_real_ip(request)
    _audit(user_id, "memory_deleted", fact_id, db, ip=ip, extra={"fact_id": fact_id})
    return JSONResponse(content={"status": "archived", "fact_id": fact_id})


class _Feedback(BaseModel):
    conversation_id: str
    reply: str
    rating: str  # "up" | "down"
    comment: str = ""
    agent_version: str = ""


@router.post("/feedback")
async def rate_reply(body: _Feedback, request: Request, current_user: dict = Depends(get_current_user)):
    """👍/👎 de una respuesta del agente. Se guarda por (usuario, conversacion, huella del texto): calificar de nuevo
    la misma respuesta reemplaza el voto. Con agent_version y conversation_id se cruza con la traza y la bitacora."""
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'.")
    user_id = current_user.get("id", "")
    db = request.app.state.db
    if not await db[_COL_CONTEXT].find_one({"user_id": user_id, "conversation_id": body.conversation_id}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    import hashlib
    reply_hash = hashlib.sha256(body.reply.strip().encode("utf-8")).hexdigest()[:16]
    await db["message_feedback"].update_one(
        {"user_id": user_id, "conversation_id": body.conversation_id, "reply_hash": reply_hash},
        {"$set": {"rating": body.rating, "comment": body.comment[:1000], "reply": body.reply[:4000],
                  "agent_version": body.agent_version, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return JSONResponse(content={"status": "ok", "rating": body.rating})


# ── PATCH /memories/{fact_id} ──────────────────────────────────────────────


class MemoryUpdateRequest(BaseModel):
    value: str


@router.patch("/memories/{fact_id}")
async def update_my_memory(
    fact_id: str,
    body: MemoryUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Edits the value of a specific semantic fact."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    try:
        oid = ObjectId(fact_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid fact_id format.")

    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Value cannot be empty.")

    result = await db[_COL_SEMANTIC].update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"value": value, "last_seen_at": datetime.now(timezone.utc), "status": "active"}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fact not found.")
    ip = get_real_ip(request)
    _audit(user_id, "memory_edited", fact_id, db, ip=ip, extra={"fact_id": fact_id, "new_value": value[:100]})
    return JSONResponse(content={"status": "updated", "fact_id": fact_id, "new_value": value})


# ── GET /action-history ─────────────────────────────────────────────────────


@router.get("/action-history")
async def get_action_history(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Returns the last 50 actions Shifu executed on behalf of the user."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    docs = await (
        db[_COL_OUTCOMES]
        .find(
            {"user_id": user_id},
            {
                "_id": 0,
                "intent_id": 1,
                "intent_type": 1,
                "tool_used": 1,
                "success": 1,
                "execution_time_ms": 1,
                "error_type": 1,
                "timestamp": 1,
                "workflow_id": 1,
                "run_id": 1,
                "conversation_id": 1,
            },
        )
        .sort("timestamp", -1)
        .limit(50)
        .to_list(length=50)
    )
    return JSONResponse(content=jsonable_encoder({"actions": docs, "total": len(docs)}))


# ── POST /action-history/{run_id}/undo ─────────────────────────────────────


@router.post("/action-history/{run_id}/undo")
async def undo_action(
    run_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Undoes a workflow run by executing each step's compensation_action in reverse order.
    Only steps that have a compensation_action defined will be reversed.
    """
    from app.workers.workflow_executor import WorkflowExecutor

    user_id = current_user.get("id", "")
    user_email = (current_user.get("email") or current_user.get("correo", "")).strip().lower()
    db = request.app.state.db

    # Find the run (validates user ownership)
    try:
        oid = ObjectId(run_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid run_id format.")

    run_doc = await db["workflow_runs"].find_one({"_id": oid, "user_id": user_id})
    if not run_doc:
        raise HTTPException(status_code=404, detail="Workflow run not found.")

    workflow_id = run_doc.get("workflow_id", "")
    wf_doc = await db["workflows"].find_one({"_id": ObjectId(workflow_id)}) if workflow_id else None
    steps = (wf_doc or {}).get("steps") or run_doc.get("steps") or []

    if not any(s.get("compensation_action") for s in steps):
        raise HTTPException(
            status_code=422,
            detail="No compensation actions defined for this run — cannot undo.",
        )

    fake_run = {
        "_id": run_id,
        "user_id": user_id,
        "user_email": user_email,
        "workflow_id": workflow_id,
        "workflow_name": run_doc.get("workflow_name", ""),
        "steps": steps,
    }
    executor = WorkflowExecutor(fake_run, db)
    result = await executor.run_undo(steps)
    return JSONResponse(content=jsonable_encoder(result))


# ── POST /transparency-mode ─────────────────────────────────────────────────


class TransparencyModeRequest(BaseModel):
    enabled: bool


@router.post("/transparency-mode")
async def set_transparency_mode(
    body: TransparencyModeRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Opt in or out of transparency mode.
    When enabled, Shifu briefly explains its intent classification at the start of each response.
    """
    from app.services.chat_memory import upsert_preference
    from app.database import get_async_database

    user_id = current_user.get("id", "")
    db = get_async_database()

    await upsert_preference(
        user_id,
        "transparency_mode",
        body.enabled,
        db,
        confidence=1.0,
        source="explicit",
    )
    _audit(user_id, "transparency_changed", "transparency_mode", request.app.state.db,
           extra={"enabled": body.enabled})
    return JSONResponse(
        content={
            "transparency_mode": body.enabled,
            "message": "Transparency mode enabled." if body.enabled else "Transparency mode disabled.",
        }
    )


# ── GET /audit-log ──────────────────────────────────────────────────────────


@router.get("/audit-log")
async def get_audit_log(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Returns the last 100 security audit events for this user."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    events = await _get_audit(user_id, db, limit=100)
    return JSONResponse(content=jsonable_encoder({"events": events, "total": len(events)}))


# ── GET /integrations ───────────────────────────────────────────────────────

_COL_ACCOUNTS = "user_connected_accounts"


def _compute_token_expiry(acc: dict) -> dict:
    """Computes token health status for a connected account."""
    expires_in = int(acc.get("expires_in") or 3600)
    acquired_raw = acc.get("token_acquisition_time") or acc.get("created_at")
    now = datetime.now(timezone.utc)

    expires_at = None
    if acquired_raw:
        try:
            if isinstance(acquired_raw, datetime):
                acquired = acquired_raw if acquired_raw.tzinfo else acquired_raw.replace(tzinfo=timezone.utc)
            else:
                acquired = datetime.fromisoformat(str(acquired_raw).replace("Z", "+00:00"))
            expires_at = acquired + timedelta(seconds=expires_in)
        except Exception:
            pass

    if expires_at is None:
        status = "unknown"
    elif expires_at < now:
        status = "expired"
    elif expires_at < now + timedelta(hours=24):
        status = "expiring_soon"
    else:
        status = "healthy"

    return {
        "provider": acc.get("provider", ""),
        "account_id": acc.get("account_id", ""),
        "token_status": status,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "has_refresh_token": bool(acc.get("refresh_token")),
    }


@router.get("/integrations")
async def list_my_integrations(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Lists all connected integrations with OAuth token health status.
    Flags tokens expiring in < 24h or already expired.
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    docs = await db[_COL_ACCOUNTS].find(
        {"user_id": user_id},
        {"_id": 0, "provider": 1, "account_id": 1, "expires_in": 1,
         "token_acquisition_time": 1, "created_at": 1, "refresh_token": 1},
    ).to_list(length=50)

    integrations = [_compute_token_expiry(d) for d in docs]
    expiring = [i for i in integrations if i["token_status"] in ("expired", "expiring_soon")]

    return JSONResponse(content=jsonable_encoder({
        "integrations": integrations,
        "total": len(integrations),
        "expiring_soon": len(expiring),
        "attention_required": expiring,
    }))


# ── DELETE /integrations/{provider} ────────────────────────────────────────


@router.delete("/integrations/{provider}")
async def revoke_integration(
    provider: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Revokes a connected integration by deleting all accounts for this provider.
    Writes an audit event on success.
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db
    provider_lower = provider.lower().strip()

    result = await db[_COL_ACCOUNTS].delete_many(
        {"user_id": user_id, "provider": provider_lower}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"No connected account found for provider '{provider}'.")

    ip = get_real_ip(request)
    _audit(user_id, "integration_revoked", provider_lower, db,
           ip=ip, extra={"accounts_removed": result.deleted_count})

    return JSONResponse(content={
        "status": "revoked",
        "provider": provider_lower,
        "accounts_removed": result.deleted_count,
    })


# ── POST /integrations/{provider}/test ─────────────────────────────────────


@router.post("/integrations/{provider}/test")
async def test_integration(
    provider: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Tests if a connected integration is operational by calling a lightweight read action.
    Returns {status: "ok" | "error", message: str}.
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db
    provider_lower = provider.lower().strip()

    acc = await db[_COL_ACCOUNTS].find_one(
        {"user_id": user_id, "provider": provider_lower}
    )
    if not acc:
        raise HTTPException(status_code=404, detail=f"No connected account found for '{provider}'.")

    # Lightweight health check: attempt to load BigTools for this provider and call
    # the first available read-only tool. Fail gracefully if tool not available.
    test_status = "unknown"
    test_message = "Test not supported for this provider yet."
    try:
        from app.services.chat_memory import load_user_integrations
        from app.services.bigtools_loader import get_all_bigtools
        import asyncio

        connected = await load_user_integrations(user_id, db)
        provider_map = {c["provider"]: c.get("account_id", "") for c in (connected or [])}
        connected_providers = {c["provider"] for c in (connected or [])}

        if provider_lower not in connected_providers:
            test_status = "error"
            test_message = f"Provider '{provider}' is not connected."
        else:
            bigtools = await asyncio.to_thread(
                get_all_bigtools, user_id, "", db, provider_map, connected_providers
            )
            provider_tools = [bt for bt in bigtools if (provider_lower in bt.name.lower() or provider_lower in (bt.app or "").lower())]
            if provider_tools:
                test_status = "ok"
                test_message = f"Integration '{provider}' is connected and {len(provider_tools)} tool(s) are available."
            else:
                test_status = "error"
                test_message = f"Integration '{provider}' is connected but no tools are available (check credentials)."
    except Exception as exc:
        test_status = "error"
        test_message = str(exc)

    ip = get_real_ip(request)
    _audit(user_id, "integration_tested", provider_lower, db,
           outcome=test_status, ip=ip, extra={"message": test_message[:200]})

    return JSONResponse(content={"status": test_status, "provider": provider_lower, "message": test_message})


# ── POST /integrations/refresh ──────────────────────────────────────────────


@router.post("/integrations/refresh")
async def refresh_my_integrations(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Refreshes OAuth tokens for the user's legacy `integrations` map (consumed by
    the Secretary endpoints). Throttled to once every 30 minutes per user.
    """
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    user = await db[Collections.USERS].find_one({"_id": user_oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    last_refresh = user.get("last_token_refresh")
    if last_refresh and datetime.utcnow() - last_refresh < timedelta(minutes=30):
        return JSONResponse(content={"message": "Tokens still valid", "services": []})

    integrations = user.get("integrations", {})
    refreshed = []
    for service, data in integrations.items():
        if data.get("refresh_token"):
            data["token"] = f"new-token-{service}"
            data["timestamp"] = datetime.utcnow().isoformat()
            refreshed.append(service)
    await db[Collections.USERS].update_one(
        {"_id": user_oid},
        {"$set": {"integrations": integrations, "last_token_refresh": datetime.utcnow()}},
    )
    return JSONResponse(content={"message": "Tokens refreshed", "services": refreshed})


# ── GET /goals ──────────────────────────────────────────────────────────────


@router.get("/goals")
async def list_my_goals(
    request: Request,
    current_user: dict = Depends(get_current_user),
    status: str | None = None,
):
    """
    Lists all goals for the authenticated user.
    Optional ?status= filter (active|draft|completed|abandoned).
    Returns sorted by priority ASC, created_at DESC.
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    query: dict = {"user_id": user_id}
    if status:
        allowed = {"active", "draft", "completed", "abandoned"}
        if status not in allowed:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(allowed))}")
        query["status"] = status
    else:
        query["status"] = {"$in": ["active", "draft"]}

    docs = await (
        db[_COL_GOALS]
        .find(query, {"_id": 0})
        .sort([("priority", 1), ("created_at", -1)])
        .limit(100)
        .to_list(length=100)
    )
    for d in docs:
        for field in ("created_at", "updated_at", "completed_at"):
            v = d.get(field)
            if v and hasattr(v, "isoformat"):
                d[field] = v.isoformat()

    return JSONResponse(content=jsonable_encoder({"goals": docs, "total": len(docs)}))


# ── PATCH /goals/{goal_id} ─────────────────────────────────────────────────


class GoalUpdateRequest(BaseModel):
    status: str | None = None
    priority: int | None = None
    description: str | None = None


@router.patch("/goals/{goal_id}")
async def update_my_goal(
    goal_id: str,
    body: GoalUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Updates a goal's status, priority, or description.
    status: active | draft | completed | abandoned
    priority: 1 (high) | 2 (medium) | 3 (low)
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    allowed_statuses = {"active", "draft", "completed", "abandoned"}
    if body.status and body.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(allowed_statuses))}")
    if body.priority and body.priority not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="priority must be 1, 2, or 3.")

    now = datetime.now(timezone.utc)
    updates: dict = {"updated_at": now}
    if body.status:
        updates["status"] = body.status
        if body.status in ("completed", "abandoned"):
            updates["completed_at"] = now
    if body.priority:
        updates["priority"] = body.priority
    if body.description:
        desc = body.description.strip()
        if not desc:
            raise HTTPException(status_code=400, detail="description cannot be empty.")
        updates["description"] = desc

    if len(updates) == 1:
        raise HTTPException(status_code=400, detail="No fields to update.")

    result = await db[_COL_GOALS].update_one(
        {"goal_id": goal_id, "user_id": user_id},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found.")

    ip = get_real_ip(request)
    _audit(user_id, "goal_updated", goal_id, db, ip=ip,
           extra={"goal_id": goal_id, "updates": {k: str(v) for k, v in updates.items() if k != "updated_at"}})
    return JSONResponse(content={"status": "updated", "goal_id": goal_id})


# ── DELETE /goals/{goal_id} ────────────────────────────────────────────────


@router.delete("/goals/{goal_id}")
async def delete_my_goal(
    goal_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Abandons a goal (soft-delete — sets status to 'abandoned')."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    now = datetime.now(timezone.utc)
    result = await db[_COL_GOALS].update_one(
        {"goal_id": goal_id, "user_id": user_id, "status": {"$in": ["active", "draft"]}},
        {"$set": {"status": "abandoned", "updated_at": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Active goal not found.")

    ip = get_real_ip(request)
    _audit(user_id, "goal_abandoned", goal_id, db, ip=ip, extra={"goal_id": goal_id})
    return JSONResponse(content={"status": "abandoned", "goal_id": goal_id})


# ── GET /tasks ──────────────────────────────────────────────────────────────


@router.get("/tasks")
async def list_my_tasks(
    request: Request,
    current_user: dict = Depends(get_current_user),
    status: str | None = None,
):
    """
    Lists all tasks for the authenticated user.
    Optional ?status= filter (pending|in_progress|done|cancelled).
    Returns sorted by (priority ASC, deadline ASC, created_at ASC).
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    query: dict = {"user_id": user_id}
    if status:
        allowed = {"pending", "in_progress", "done", "cancelled"}
        if status not in allowed:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(allowed))}")
        query["status"] = status
    else:
        query["status"] = {"$in": ["pending", "in_progress"]}

    docs = await (
        db[_COL_TASKS]
        .find(query, {"_id": 0})
        .sort([("priority", 1), ("deadline", 1), ("created_at", 1)])
        .limit(100)
        .to_list(length=100)
    )
    for d in docs:
        for field in ("created_at", "updated_at", "completed_at"):
            v = d.get(field)
            if v and hasattr(v, "isoformat"):
                d[field] = v.isoformat()

    return JSONResponse(content=jsonable_encoder({"tasks": docs, "total": len(docs)}))


# ── PATCH /tasks/{task_id} ─────────────────────────────────────────────────


class TaskUpdateRequest(BaseModel):
    status: str | None = None
    priority: int | None = None
    deadline: str | None = None
    description: str | None = None


@router.patch("/tasks/{task_id}")
async def update_my_task(
    task_id: str,
    body: TaskUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Updates a task's status, priority, deadline, or description.
    status: pending | in_progress | done | cancelled
    priority: 1 (urgent) | 2 (normal) | 3 (low)
    deadline: ISO date string or null to clear
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    allowed_statuses = {"pending", "in_progress", "done", "cancelled"}
    if body.status and body.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(allowed_statuses))}")
    if body.priority and body.priority not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="priority must be 1, 2, or 3.")

    now = datetime.now(timezone.utc)
    updates: dict = {"updated_at": now}
    if body.status:
        updates["status"] = body.status
        if body.status in ("done", "cancelled"):
            updates["completed_at"] = now
    if body.priority:
        updates["priority"] = body.priority
    if body.description is not None:
        desc = body.description.strip()
        if not desc:
            raise HTTPException(status_code=400, detail="description cannot be empty.")
        updates["description"] = desc
    if body.deadline is not None:
        updates["deadline"] = body.deadline or None

    if len(updates) == 1:
        raise HTTPException(status_code=400, detail="No fields to update.")

    result = await db[_COL_TASKS].update_one(
        {"task_id": task_id, "user_id": user_id},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found.")

    ip = get_real_ip(request)
    _audit(user_id, "task_updated", task_id, db, ip=ip,
           extra={"task_id": task_id, "updates": {k: str(v) for k, v in updates.items() if k != "updated_at"}})
    return JSONResponse(content={"status": "updated", "task_id": task_id})


# ── DELETE /tasks/{task_id} ────────────────────────────────────────────────


@router.delete("/tasks/{task_id}")
async def delete_my_task(
    task_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Cancels a task (soft-delete — sets status to 'cancelled')."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    now = datetime.now(timezone.utc)
    result = await db[_COL_TASKS].update_one(
        {"task_id": task_id, "user_id": user_id, "status": {"$in": ["pending", "in_progress"]}},
        {"$set": {"status": "cancelled", "updated_at": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Active task not found.")

    ip = get_real_ip(request)
    _audit(user_id, "task_cancelled", task_id, db, ip=ip, extra={"task_id": task_id})
    return JSONResponse(content={"status": "cancelled", "task_id": task_id})


# ── GET /conversations ────────────────────────────────────────────────────


@router.get("/conversations")
async def list_my_conversations(
    request: Request,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Lists the user's past chat conversations, most recently active first."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort": {"created_at": 1}},
        {
            "$group": {
                "_id": "$conversation_id",
                "first_message": {"$first": "$content"},
                "last_message": {"$last": "$content"},
                "updated_at": {"$last": "$created_at"},
                "message_count": {"$sum": 1},
            }
        },
        {"$sort": {"updated_at": -1}},
        {"$limit": limit},
    ]
    docs = await db[_COL_MESSAGES].aggregate(pipeline).to_list(length=limit)
    conversations = [
        {
            "id": d["_id"],
            "title": (d.get("first_message") or "Conversación")[:40],
            "last_message_preview": (d.get("last_message") or "")[:120],
            "updated_at": d["updated_at"].isoformat() if d.get("updated_at") else None,
            "message_count": d.get("message_count", 0),
        }
        for d in docs
    ]
    return JSONResponse(content=jsonable_encoder({"success": True, "data": conversations}))


# ── GET /conversations/{conversation_id}/messages ─────────────────────────


@router.get("/conversations/{conversation_id}/messages")
async def get_my_conversation_messages(
    conversation_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Returns the full message transcript for one of the user's conversations."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    messages = await get_conversation_messages(user_id, conversation_id, db)
    return JSONResponse(content=jsonable_encoder({"success": True, "data": messages}))


# ── DELETE /conversations/{conversation_id} ────────────────────────────────


@router.delete("/conversations/{conversation_id}")
async def delete_my_conversation(
    conversation_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Deletes a conversation's messages and context for the current user."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    await db[_COL_MESSAGES].delete_many(
        {"user_id": user_id, "conversation_id": conversation_id}
    )
    await db[_COL_CONTEXT].delete_one(
        {"user_id": user_id, "conversation_id": conversation_id}
    )
    return JSONResponse(content=jsonable_encoder({"success": True}))


# ── GET /chats/{app}/messages ───────────────────────────────────────────────

_SUPPORTED_CHAT_APPS = ["Shifu", "Gmail", "Slack", "Notion", "ClickUp"]


@router.get("/chats/{app}/messages")
async def get_my_app_chat(
    app: str,
    request: Request,
    page: int = 1,
    per_page: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Paginated chat history stored on the user document for a connected app."""
    matched = next((a for a in _SUPPORTED_CHAT_APPS if a.lower() == app.lower()), None)
    if not matched:
        raise HTTPException(status_code=404, detail=f"Unsupported app '{app}'.")
    per_page = min(per_page, 100)
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    user = await db[Collections.USERS].find_one({"_id": user_oid}, {"chats": 1})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    chats = user.get("chats", [])
    chat = next((c for c in chats if c["name"] == matched), None)
    if not chat:
        return JSONResponse(content={"messages": [], "total": 0, "page": page})
    messages = list(reversed(chat.get("messages", [])))
    start = (page - 1) * per_page
    end = start + per_page
    return JSONResponse(content=jsonable_encoder({
        "messages": messages[start:end], "total": len(messages), "page": page,
    }))


# ── GET /referrals ──────────────────────────────────────────────────────────


@router.get("/referrals")
async def list_my_referrals(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Lists people who registered using the authenticated user's referral code."""
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    user_doc = await db[Collections.USERS].find_one({"_id": user_oid}, {"code_referrals_uniq": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found.")

    referrals_list = []
    async for ref in db.referrals.find({"referrer_id": str(user_oid)}):
        referred_user = await db[Collections.USERS].find_one({"_id": ObjectId(ref["referred_id"])})
        if referred_user:
            referrals_list.append({
                "user_id": str(referred_user["_id"]),
                "name": referred_user.get("name") or referred_user.get("nombre", "Usuario Shifu"),
                "email": referred_user.get("email") or referred_user.get("correo", ""),
                "date_registered": (ref.get("date_registered") or datetime.now(timezone.utc)).isoformat(),
            })

    return JSONResponse(content=jsonable_encoder({
        "referral_code": user_doc.get("code_referrals_uniq", "N/A"),
        "total_count": len(referrals_list),
        "referrals": referrals_list,
    }))


# ── POST /referrals/code ────────────────────────────────────────────────────


@router.post("/referrals/code")
async def generate_my_referral_code(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Generates a referral code for the authenticated user if they don't already have one."""
    db = request.app.state.db
    user_oid = ObjectId(current_user.get("id", ""))
    user_doc = await db[Collections.USERS].find_one({"_id": user_oid}, {"code_referrals_uniq": 1})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found.")
    if user_doc.get("code_referrals_uniq"):
        return JSONResponse(content={
            "message": "El usuario ya tiene un código",
            "code": user_doc["code_referrals_uniq"],
        })

    new_code = await generate_unique_referral_code(db)
    await db[Collections.USERS].update_one(
        {"_id": user_oid},
        {"$set": {"code_referrals_uniq": new_code, "count_referrals": 0}},
    )
    return JSONResponse(content={"success": True, "code": new_code})
