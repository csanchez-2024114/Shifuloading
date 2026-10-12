"""
Audit Service — immutable security audit log.

Writes to `audit_events` collection (append-only, never updated).
All writes are fire-and-forget (asyncio.create_task) — never block the request path.

Event structure:
  user_id    : str  — who performed or triggered the action
  action     : str  — machine-readable action name (see _ACTIONS below)
  resource   : str  — what was acted upon (workflow_id, fact_id, tool_name, provider, ...)
  ip         : str  — client IP (empty when action originated from a background worker)
  outcome    : str  — "success" | "failure" | "pending" | "blocked"
  extra      : dict — arbitrary context (run_id, error, count, ...)
  timestamp  : datetime (UTC)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_COL = "audit_events"

# Canonical action names — extend as needed
ACTIONS = {
    # Workflow lifecycle
    "workflow_run_started":   "workflow_run_started",
    "workflow_run_completed": "workflow_run_completed",
    "workflow_run_failed":    "workflow_run_failed",
    # Human-in-the-loop
    "action_confirmed":       "action_confirmed",
    "action_cancelled":       "action_cancelled",
    # Memory / profile
    "memory_deleted":         "memory_deleted",
    "memory_edited":          "memory_edited",
    "transparency_changed":   "transparency_changed",
    # Integrations
    "integration_revoked":    "integration_revoked",
    "integration_tested":     "integration_tested",
    "function_tested":        "function_tested",
    # Security / abuse
    "rate_limit_exceeded":    "rate_limit_exceeded",
    "suspicious_activity":    "suspicious_activity",
    "permission_denied":      "permission_denied",
    # Auth
    "login_success":          "login_success",
    "login_failure":          "login_failure",
}


async def _write(
    user_id: str,
    action: str,
    resource: str,
    outcome: str,
    ip: str,
    extra: dict,
    db: AsyncIOMotorDatabase,
) -> None:
    try:
        await db[_COL].insert_one(
            {
                "user_id": user_id,
                "action": action,
                "resource": resource,
                "ip": ip,
                "outcome": outcome,
                "extra": extra or {},
                "timestamp": datetime.now(timezone.utc),
            }
        )
    except Exception as exc:
        logger.warning("[audit] write failed action=%s user=%s: %s", action, user_id, exc)


def log_event(
    user_id: str,
    action: str,
    resource: str,
    db: AsyncIOMotorDatabase,
    *,
    outcome: str = "success",
    ip: str = "",
    extra: dict | None = None,
) -> None:
    """
    Fire-and-forget audit log write. Call from any async context.
    Never raises — failures are logged as warnings.
    """
    asyncio.create_task(
        _write(user_id, action, resource, outcome, ip, extra or {}, db)
    )


async def get_recent_events(
    user_id: str,
    db: AsyncIOMotorDatabase,
    limit: int = 100,
) -> list:
    """Loads recent audit events for a user (admin / self-service view)."""
    try:
        docs = await (
            db[_COL]
            .find({"user_id": user_id}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(limit)
            .to_list(length=limit)
        )
        for d in docs:
            ts = d.get("timestamp")
            if ts and hasattr(ts, "isoformat"):
                d["timestamp"] = ts.isoformat()
        return docs
    except Exception as exc:
        logger.warning("[audit] get_recent_events failed user=%s: %s", user_id, exc)
        return []
