"""
/api/v1/me/notifications — Persisted notification history + read-state.

The live "something just happened" signal is the WS event on `wf:{user_id}`
(app/routes/ws/workflow_ws.py, WS /api/v1/ws/runs). This router is the REST-backed
history/read-state layer for the same events, persisted in `user_notifications`
(app/services/notification_service.py) from app/core/quota.py (usage_warning) and
app/workers/workflow_executor.py (run_completed/run_failed).

All endpoints are scoped to the authenticated user — no cross-user access.
Router is mounted with prefix "/api/v1/me/notifications" in main.py; paths below are
relative to that.

Endpoints:
  GET   /?page=&limit=&unread_only=  — Paginated list of notifications, newest first.
  PATCH /{id}/read                   — Marks a single notification as read.
  PATCH /mark-all-read               — Marks all of the user's notifications as read.
"""
import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.database import get_current_user
from app.core.constants import Collections

logger = logging.getLogger(__name__)
router = APIRouter()


# ── GET / (list, paginated) ─────────────────────────────────────────────────


@router.get("")
async def list_my_notifications(
    request: Request,
    page: int = 1,
    limit: int = 20,
    unread_only: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Paginated notification history, newest first. `unread_only=true` filters to read=False."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    skip = (page - 1) * limit

    query: dict = {"user_id": user_id}
    if unread_only:
        query["read"] = False

    col = db[Collections.USER_NOTIFICATIONS]
    total = await col.count_documents(query)
    unread_count = await col.count_documents({"user_id": user_id, "read": False})
    docs = await (
        col.find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )
    for d in docs:
        d["id"] = str(d.pop("_id"))
        created = d.get("created_at")
        if created and hasattr(created, "isoformat"):
            d["created_at"] = created.isoformat()

    return JSONResponse(content=jsonable_encoder({
        "notifications": docs,
        "total": total,
        "unread_count": unread_count,
        "page": page,
        "limit": limit,
    }))


# ── PATCH /{id}/read ─────────────────────────────────────────────────────────


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Marks a single notification as read."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    try:
        oid = ObjectId(notification_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid notification id format.")

    result = await db[Collections.USER_NOTIFICATIONS].update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found.")

    return JSONResponse(content={"status": "read", "id": notification_id})


# ── PATCH /mark-all-read ─────────────────────────────────────────────────────


@router.patch("/mark-all-read")
async def mark_all_notifications_read(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Marks all of the authenticated user's unread notifications as read."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    result = await db[Collections.USER_NOTIFICATIONS].update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc)}},
    )
    return JSONResponse(content={"status": "read", "updated_count": result.modified_count})
