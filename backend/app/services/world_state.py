"""
world_state — Platform utility for persisting structured environment snapshots.

Used by TriggerPoller and ProactiveNotifier to write to `user_world_state`.

Collection schema:
  {user_id, category, key, value, source_app, last_synced, ttl}

Upsert key: (user_id, category, key) — replaces value in-place.
TTL: default 24h from last_synced (configurable via WORLD_STATE_TTL_HOURS env var).
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_COL = "user_world_state"
_TTL_HOURS = int(os.getenv("WORLD_STATE_TTL_HOURS", "24"))

_TOOL_MAP: list[tuple[str, str, str]] = [
    ("listar_correos",       "email",    "gmail"),
    ("buscar_emails",        "email",    "gmail"),
    ("leer_correo",          "email",    "gmail"),
    ("enviar_correo",        "email",    "gmail"),
    ("listar_eventos",       "calendar", "google_calendar"),
    ("crear_evento",         "calendar", "google_calendar"),
    ("listar_tareas_asana",  "tasks",    "asana"),
    ("listar_tareas_clickup","tasks",    "clickup"),
    ("listar_issues_jira",   "tasks",    "jira"),
    ("listar_contactos",     "crm",      "hubspot"),
    ("listar_archivos",      "files",    "google_drive"),
    ("listar_dropbox",       "files",    "dropbox"),
    ("instagram",            "social",   "instagram"),
    ("facebook",             "social",   "facebook"),
]


def resolve_tool_category(tool_name: str) -> tuple[str, str]:
    """Return (category, source_app) for a trigger tool name."""
    tl = tool_name.lower()
    for prefix, category, source_app in _TOOL_MAP:
        if tl.startswith(prefix) or prefix in tl:
            return category, source_app
    return "custom", tool_name


async def upsert_world_state(
    db: AsyncIOMotorDatabase,
    user_id: str,
    entries: list[dict],
) -> None:
    """
    Upsert world state entries for a user.

    Each entry dict must have: {category, key, value, source_app}
    Optional: ttl_hours (overrides default _TTL_HOURS for this entry)

    Silently swallows errors — world state is best-effort, never fatal.
    """
    if not entries:
        return
    now = datetime.now(timezone.utc)
    try:
        for entry in entries:
            ttl_h = entry.get("ttl_hours", _TTL_HOURS)
            ttl_dt = now + timedelta(hours=ttl_h)
            await db[_COL].update_one(
                {
                    "user_id": user_id,
                    "category": entry["category"],
                    "key": entry["key"],
                },
                {
                    "$set": {
                        "value": entry["value"],
                        "source_app": entry.get("source_app", "unknown"),
                        "last_synced": now,
                        "ttl": ttl_dt,
                    }
                },
                upsert=True,
            )
        logger.debug(
            "[world_state] upserted %d entries for user=%s", len(entries), user_id
        )
    except Exception as exc:
        logger.warning("[world_state] upsert failed user=%s: %s", user_id, exc)


def extract_trigger_signal(
    trigger_tool_name: str,
    result: any,
    wf_name: str = "",
) -> list[dict]:
    """Convert a trigger tool result into world state entries."""
    category, source_app = resolve_tool_category(trigger_tool_name)
    now_iso = datetime.now(timezone.utc).isoformat()

    if isinstance(result, list):
        count = len(result)
        triggered = count > 0
        value = {
            "triggered": triggered,
            "count": count,
            "tool": trigger_tool_name,
            "workflow": wf_name,
            "checked_at": now_iso,
        }
    elif isinstance(result, dict):
        triggered = bool(result.get("triggered"))
        value = {
            "triggered": triggered,
            "tool": trigger_tool_name,
            "workflow": wf_name,
            "checked_at": now_iso,
            **{k: v for k, v in result.items() if k not in ("triggered",) and isinstance(v, (str, int, float, bool))},
        }
    else:
        value = {
            "triggered": False,
            "tool": trigger_tool_name,
            "workflow": wf_name,
            "checked_at": now_iso,
        }

    return [
        {
            "category": category,
            "key": f"trigger:{trigger_tool_name}",
            "value": value,
            "source_app": source_app,
        }
    ]
