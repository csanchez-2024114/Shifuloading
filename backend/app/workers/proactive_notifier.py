"""
ProactiveNotifier — Autonomous Agent Loop (DoD item 4 + 7)

Checks world state signals every 30 minutes and pushes targeted notifications
to users via the existing Redis pub/sub channel (wf:{user_id}).
This is the foundation for Shifu-initiated conversations without user input.

Notification triggers:
  goal_reminder      — active goal with no workflow run in 7+ days
  deadline_alert     — pending task with deadline within 24h
  workflow_failure   — run with status "failed" not addressed in 24h

Notification payload (sent to Redis channel wf:{user_id}):
  {
    "type":       "proactive_notification",
    "category":   "goal_reminder" | "deadline_alert" | "workflow_failure",
    "title":      str,
    "body":       str,
    "user_id":    str,
    "timestamp":  ISO-8601
  }

Configuration via env vars:
  PROACTIVE_POLL_MINUTES        — how often to run (default: 30)
  GOAL_REMINDER_DAYS            — days of inactivity before goal reminder (default: 7)
  DEADLINE_ALERT_HOURS          — hours before deadline to alert (default: 24)
  WORKFLOW_FAILURE_ALERT_HOURS  — hours after failure before alert (default: 24)
  PROACTIVE_NOTIFICATIONS_ENABLED — set to "false" to disable (default: true)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import Config
from app.workers.heartbeat import worker_heartbeat
from app.services.world_state import upsert_world_state

logger = logging.getLogger(__name__)

_POLL_MINUTES             = int(os.getenv("PROACTIVE_POLL_MINUTES", "30"))
_GOAL_REMINDER_DAYS       = int(os.getenv("GOAL_REMINDER_DAYS", "7"))
_DEADLINE_ALERT_HOURS     = int(os.getenv("DEADLINE_ALERT_HOURS", "24"))
_FAILURE_ALERT_HOURS      = int(os.getenv("WORKFLOW_FAILURE_ALERT_HOURS", "24"))
_ENABLED                  = os.getenv("PROACTIVE_NOTIFICATIONS_ENABLED", "true").lower() != "false"

_COL_GOALS     = "user_active_goals"
_COL_TASKS     = "user_pending_tasks"
_COL_RUNS      = "workflow_runs"
_COL_NOTIFS    = "proactive_notifications_log"
_COL_PREFS     = "user_preferences"

_NOTIF_TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "goal_reminder": {
        "English": ("Goal reminder", "Don't forget your goal: {desc}. Want to make progress today?"),
        "Spanish": ("Recordatorio de objetivo", "No olvides tu objetivo: {desc}. ¿Quieres avanzar hoy?"),
    },
    "deadline_alert": {
        "English": ("Task deadline approaching", "Your task '{desc}' is due {dl}. Ready to get it done?"),
        "Spanish": ("Plazo próximo", "Tu tarea '{desc}' vence el {dl}. ¿Listo para completarla?"),
    },
    "workflow_failure": {
        "English": ("Workflow failed", "Your workflow '{name}' failed and hasn't been retried. Want to fix it?"),
        "Spanish": ("Flujo fallido", "Tu flujo '{name}' falló y no se ha reintentado. ¿Quieres arreglarlo?"),
    },
}


async def _get_user_language(user_id: str, db: AsyncIOMotorDatabase, cache: dict) -> str:
    """Returns 'Spanish' or 'English' for the user. Caches within a tick to avoid N+1 queries."""
    if user_id in cache:
        return cache[user_id]
    try:
        doc = await db[_COL_PREFS].find_one({"user_id": user_id}, {"prefs.user_language": 1})
        raw = (doc or {}).get("prefs", {}).get("user_language", "English")
        lang_val = (raw.get("value") if isinstance(raw, dict) else raw) or "English"
        lang = "Spanish" if "spanish" in lang_val.lower() else "English"
    except Exception:
        lang = "English"
    cache[user_id] = lang
    return lang


def _notif(category: str, lang: str, **kwargs) -> tuple[str, str]:
    """Returns (title, body) for the given category and language, formatted with kwargs."""
    tmpl = _NOTIF_TEMPLATES.get(category, {}).get(lang) or _NOTIF_TEMPLATES[category]["English"]
    return tmpl[0], tmpl[1].format(**kwargs)


async def _push(user_id: str, category: str, title: str, body: str, redis_url: str) -> None:
    """Publish a proactive notification to the user's Redis channel."""
    import redis.asyncio as aioredis
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        payload = json.dumps({
            "type":      "proactive_notification",
            "category":  category,
            "title":     title,
            "body":      body,
            "user_id":   user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await r.publish(f"wf:{user_id}", payload)
        await r.aclose()
        logger.info(
            "[ProactiveNotifier] pushed category=%r to user=%s title=%r",
            category, user_id, title[:60],
        )
    except Exception as exc:
        logger.debug("[ProactiveNotifier] push failed user=%s: %s", user_id, exc)


async def _log_notification(user_id: str, category: str, resource_id: str, db: AsyncIOMotorDatabase) -> None:
    """Record a sent notification to avoid re-sending within the cooldown window."""
    try:
        await db[_COL_NOTIFS].insert_one({
            "user_id":     user_id,
            "category":    category,
            "resource_id": resource_id,
            "sent_at":     datetime.now(timezone.utc),
        })
    except Exception:
        pass


async def _already_sent(user_id: str, category: str, resource_id: str, db: AsyncIOMotorDatabase) -> bool:
    """Returns True if we already sent this notification type for this resource in the last 24h."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        doc = await db[_COL_NOTIFS].find_one({
            "user_id":     user_id,
            "category":    category,
            "resource_id": resource_id,
            "sent_at":     {"$gte": since},
        })
        return doc is not None
    except Exception:
        return False


async def _check_goal_reminders(db: AsyncIOMotorDatabase, redis_url: str) -> None:
    _lang_cache: dict[str, str] = {}
    """
    For each active goal that has no associated workflow run in _GOAL_REMINDER_DAYS days,
    send a goal_reminder notification to the goal owner.
    Also writes a world state signal per user summarising stale goals found.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_GOAL_REMINDER_DAYS)
    # {user_id: [description, ...]} for world state aggregation
    stale_by_user: dict[str, list[str]] = {}
    try:
        cursor = db[_COL_GOALS].find(
            {"status": {"$in": ["active", "draft"]}},
            {"_id": 1, "user_id": 1, "description": 1, "created_at": 1},
        )
        async for goal in cursor:
            goal_id  = str(goal["_id"])
            user_id  = goal.get("user_id", "")
            desc     = goal.get("description", "")
            created  = goal.get("created_at")
            if not user_id or not desc:
                continue
            # Only remind about goals old enough that they had time to progress
            if created and created > cutoff:
                continue
            # Check if there's been any workflow run for this user in the reminder window
            recent_run = await db[_COL_RUNS].find_one(
                {"user_id": user_id, "created_at": {"$gte": cutoff}},
                {"_id": 1},
            )
            if recent_run:
                continue  # User has been active — no reminder needed

            stale_by_user.setdefault(user_id, []).append(desc[:100])

            if await _already_sent(user_id, "goal_reminder", goal_id, db):
                continue

            lang = await _get_user_language(user_id, db, _lang_cache)
            title, body = _notif("goal_reminder", lang, desc=desc[:120])
            await _push(user_id, "goal_reminder", title=title, body=body, redis_url=redis_url)
            await _log_notification(user_id, "goal_reminder", goal_id, db)

        # Write world state: one entry per user with stale goals
        for user_id, descs in stale_by_user.items():
            await upsert_world_state(db, user_id, [{
                "category": "goals",
                "key": "stale_goals",
                "value": {"count": len(descs), "descriptions": descs, "inactive_days": _GOAL_REMINDER_DAYS},
                "source_app": "shifu_goals",
            }])
    except Exception as exc:
        logger.warning("[ProactiveNotifier] goal_reminder check failed: %s", exc)


async def _check_deadline_alerts(db: AsyncIOMotorDatabase, redis_url: str) -> None:
    _lang_cache: dict[str, str] = {}
    """
    For each pending task with a deadline within the next _DEADLINE_ALERT_HOURS hours,
    send a deadline_alert notification.
    Also writes a world state signal per user with approaching deadlines.
    """
    now    = datetime.now(timezone.utc)
    window = now + timedelta(hours=_DEADLINE_ALERT_HOURS)
    # {user_id: [{desc, deadline}, ...]}
    deadlines_by_user: dict[str, list[dict]] = {}
    try:
        cursor = db[_COL_TASKS].find(
            {
                "status":   {"$in": ["pending", "in_progress"]},
                "deadline": {"$gte": now.isoformat(), "$lte": window.isoformat()},
            },
            {"_id": 1, "user_id": 1, "description": 1, "deadline": 1},
        )
        async for task in cursor:
            task_id = str(task["_id"])
            user_id = task.get("user_id", "")
            desc    = task.get("description", "")
            dl      = task.get("deadline", "")
            if not user_id:
                continue

            deadlines_by_user.setdefault(user_id, []).append(
                {"description": desc[:100], "deadline": dl}
            )

            if await _already_sent(user_id, "deadline_alert", task_id, db):
                continue

            lang = await _get_user_language(user_id, db, _lang_cache)
            title, body = _notif("deadline_alert", lang, desc=desc[:80], dl=dl)
            await _push(user_id, "deadline_alert", title=title, body=body, redis_url=redis_url)
            await _log_notification(user_id, "deadline_alert", task_id, db)

        # Write world state: one entry per user with approaching deadlines
        for user_id, tasks in deadlines_by_user.items():
            await upsert_world_state(db, user_id, [{
                "category": "tasks",
                "key": "deadline_approaching",
                "value": {"count": len(tasks), "tasks": tasks, "window_hours": _DEADLINE_ALERT_HOURS},
                "source_app": "shifu_tasks",
                "ttl_hours": 6,  # shorter TTL — deadline context expires faster
            }])
    except Exception as exc:
        logger.warning("[ProactiveNotifier] deadline_alert check failed: %s", exc)


async def _check_workflow_failures(db: AsyncIOMotorDatabase, redis_url: str) -> None:
    _lang_cache: dict[str, str] = {}
    """
    For each workflow run that failed more than _FAILURE_ALERT_HOURS hours ago and
    hasn't been retried, send a workflow_failure notification.
    Also writes a world state signal per user with unaddressed failed runs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_FAILURE_ALERT_HOURS)
    # {user_id: [workflow_name, ...]}
    failures_by_user: dict[str, list[str]] = {}
    try:
        cursor = db[_COL_RUNS].find(
            {
                "status":      "failed",
                "finished_at": {"$lte": cutoff},
            },
            {"_id": 1, "user_id": 1, "workflow_name": 1, "finished_at": 1},
        )
        async for run in cursor:
            run_id  = str(run["_id"])
            user_id = run.get("user_id", "")
            name    = run.get("workflow_name", "workflow")
            if not user_id:
                continue

            failures_by_user.setdefault(user_id, []).append(name)

            if await _already_sent(user_id, "workflow_failure", run_id, db):
                continue

            lang = await _get_user_language(user_id, db, _lang_cache)
            title, body = _notif("workflow_failure", lang, name=name)
            await _push(user_id, "workflow_failure", title=title, body=body, redis_url=redis_url)
            await _log_notification(user_id, "workflow_failure", run_id, db)

        # Write world state: one entry per user with unaddressed failures
        for user_id, names in failures_by_user.items():
            await upsert_world_state(db, user_id, [{
                "category": "workflows",
                "key": "failed_runs",
                "value": {"count": len(names), "workflow_names": names, "unaddressed_hours": _FAILURE_ALERT_HOURS},
                "source_app": "shifu_workflows",
            }])
    except Exception as exc:
        logger.warning("[ProactiveNotifier] workflow_failure check failed: %s", exc)


class ProactiveNotifier:
    """
    Background worker that checks world state signals every 30 minutes and
    pushes proactive notifications to users via Redis pub/sub → WebSocket.

    This is Shifu's autonomous agent loop: it acts on behalf of users without
    waiting for a user message to initiate.
    """

    def __init__(self, poll_minutes: int = _POLL_MINUTES):
        self.poll_seconds = poll_minutes * 60
        self._running = False

    async def start(self, db: AsyncIOMotorDatabase) -> None:
        if not _ENABLED:
            logger.info("[ProactiveNotifier] disabled (PROACTIVE_NOTIFICATIONS_ENABLED=false)")
            return
        if not Config.REDIS_URL:
            logger.info("[ProactiveNotifier] no Redis — proactive notifications disabled")
            return

        self._running = True
        logger.info(
            "[ProactiveNotifier] Started (poll every %dm, goal_reminder=%dd, "
            "deadline_alert=%dh, failure_alert=%dh)",
            self.poll_seconds // 60, _GOAL_REMINDER_DAYS,
            _DEADLINE_ALERT_HOURS, _FAILURE_ALERT_HOURS,
        )
        asyncio.create_task(
            worker_heartbeat("proactive_notifier", Config.REDIS_URL, lambda: self._running)
        )
        while self._running:
            try:
                await self._tick(db)
            except Exception as exc:
                logger.exception("[ProactiveNotifier] Unhandled error in tick: %s", exc)
            await asyncio.sleep(self.poll_seconds)
        logger.info("[ProactiveNotifier] Stopped.")

    def stop(self) -> None:
        self._running = False

    async def _tick(self, db: AsyncIOMotorDatabase) -> None:
        redis_url = Config.REDIS_URL
        await asyncio.gather(
            _check_goal_reminders(db, redis_url),
            _check_deadline_alerts(db, redis_url),
            _check_workflow_failures(db, redis_url),
            return_exceptions=True,
        )


# Module-level singleton — imported by main.py
proactive_notifier = ProactiveNotifier()
