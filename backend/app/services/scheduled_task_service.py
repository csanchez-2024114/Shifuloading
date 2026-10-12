"""
ScheduledTask Service — CRUD for the `scheduled_tasks` MongoDB collection.

schedule_type:
  "once"     – run once at run_at datetime, then mark completed.
  "interval" – run every every_seconds; optional max_runs and start_at.
  "cron"     – run on a cron schedule; schedule_config must include cron_expression.
               Examples: "0 9 * * 1" (every Monday at 9am), "0 */6 * * *" (every 6h).
               schedule_config.timezone (IANA, optional): the cron is read in that zone; default UTC.

Each task links to a full workflow (workflow_id) whose steps the worker
loads at execution time.
"""
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "scheduled_tasks"
_FAR_FUTURE = datetime(9999, 12, 31, tzinfo=timezone.utc)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _zone(tz_name: str | None) -> tzinfo:
    """Zona IANA del usuario; si falta o es invalida se usa UTC (el comportamiento de siempre)."""
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return timezone.utc


def _next_cron_run(cron_expression: str, after: datetime | None = None, tz_name: str | None = None) -> datetime:
    """Next run of a cron expression, returned in UTC.

    The cron ("0 9 * * 1") is read in the user's zone, not in UTC: "lunes a las 9" means 9:00 local.
    croniter gets an aware datetime so it also handles DST changes; the result is stored in UTC.
    """
    from croniter import croniter
    base = after or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    next_dt = croniter(cron_expression, base.astimezone(_zone(tz_name))).get_next(datetime)
    return next_dt.astimezone(timezone.utc)


def _first_run_at(schedule_type: str, schedule_config: dict) -> datetime:
    now = datetime.now(timezone.utc)
    if schedule_type == "once":
        return _parse_dt(schedule_config.get("run_at")) or now
    if schedule_type == "cron":
        expr = schedule_config.get("cron_expression", "0 * * * *")
        try:
            return _next_cron_run(expr, tz_name=schedule_config.get("timezone"))
        except Exception:
            return now
    return _parse_dt(schedule_config.get("start_at")) or now


# ── Write ops ──────────────────────────────────────────────────────────────────

async def create_scheduled_task(
    user_id: str,
    user_email: str,
    workflow_id: str,
    name: str,
    schedule_type: str,
    schedule_config: Dict[str, Any],
    db: AsyncIOMotorDatabase,
) -> str:
    """
    Create a new scheduled task linked to a workflow.

    schedule_config examples:
      once:     {"run_at": "2024-06-15T09:00:00Z"}
      interval: {"every_seconds": 3600, "max_runs": None, "start_at": "2024-06-15T09:00:00Z"}
    """
    now = datetime.now(timezone.utc)
    doc = {
        "workflow_id": workflow_id,
        "user_id": user_id,
        "user_email": user_email,
        "name": name,
        "schedule_type": schedule_type,
        "schedule_config": schedule_config,
        "status": "active",
        "next_run_at": _first_run_at(schedule_type, schedule_config),
        "last_run_at": None,
        "run_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[COLLECTION].insert_one(doc)
    return str(result.inserted_id)


async def pause_task(task_id: str, db: AsyncIOMotorDatabase) -> bool:
    try:
        oid = ObjectId(task_id)
    except InvalidId:
        return False
    r = await db[COLLECTION].update_one(
        {"_id": oid},
        {"$set": {"status": "paused", "updated_at": datetime.now(timezone.utc)}},
    )
    return r.modified_count > 0


async def resume_task(task_id: str, db: AsyncIOMotorDatabase) -> bool:
    try:
        oid = ObjectId(task_id)
    except InvalidId:
        return False
    now = datetime.now(timezone.utc)
    r = await db[COLLECTION].update_one(
        {"_id": oid},
        {"$set": {"status": "active", "next_run_at": now, "updated_at": now}},
    )
    return r.modified_count > 0


async def delete_task(task_id: str, db: AsyncIOMotorDatabase) -> bool:
    try:
        oid = ObjectId(task_id)
    except InvalidId:
        return False
    r = await db[COLLECTION].delete_one({"_id": oid})
    return r.deleted_count > 0


# ── Worker ops ─────────────────────────────────────────────────────────────────

async def claim_due_task(db: AsyncIOMotorDatabase) -> Optional[dict]:
    """Atomically claims one due active task (prevents double-execution)."""
    now = datetime.now(timezone.utc)
    doc = await db[COLLECTION].find_one_and_update(
        {"status": "active", "next_run_at": {"$lte": now}},
        {
            "$set": {
                "last_run_at": now,
                "updated_at": now,
                "next_run_at": _FAR_FUTURE,
            },
            "$inc": {"run_count": 1},
        },
        sort=[("next_run_at", 1)],
        return_document=True,
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def advance_or_complete(task: dict, db: AsyncIOMotorDatabase) -> None:
    """After execution: advance next_run_at (interval) or mark completed (once/max_runs)."""
    task_id = task["_id"]
    schedule_type = task.get("schedule_type", "interval")
    schedule_config = task.get("schedule_config", {})
    run_count = task.get("run_count", 1)
    max_runs = schedule_config.get("max_runs")

    try:
        oid = ObjectId(task_id)
    except InvalidId:
        return

    now = datetime.now(timezone.utc)

    if schedule_type == "once":
        await db[COLLECTION].update_one(
            {"_id": oid}, {"$set": {"status": "completed", "updated_at": now}}
        )
        return

    if max_runs and run_count >= max_runs:
        await db[COLLECTION].update_one(
            {"_id": oid}, {"$set": {"status": "completed", "updated_at": now}}
        )
        return

    if schedule_type == "cron":
        expr = schedule_config.get("cron_expression", "0 * * * *")
        try:
            next_run = _next_cron_run(expr, after=now, tz_name=schedule_config.get("timezone"))
        except Exception:
            next_run = now + timedelta(hours=1)
        await db[COLLECTION].update_one(
            {"_id": oid},
            {"$set": {"next_run_at": next_run, "updated_at": now}},
        )
        return

    every_seconds = max(60, int(schedule_config.get("every_seconds", 3600)))
    await db[COLLECTION].update_one(
        {"_id": oid},
        {"$set": {"next_run_at": now + timedelta(seconds=every_seconds), "updated_at": now}},
    )


# ── Read ops ───────────────────────────────────────────────────────────────────

async def list_user_tasks(user_id: str, db: AsyncIOMotorDatabase) -> List[dict]:
    docs = (
        await db[COLLECTION]
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .to_list(length=100)
    )
    return [_serialize(d) for d in docs]


def _serialize(d: dict) -> dict:
    d["id"] = str(d.pop("_id"))
    for field in ("next_run_at", "last_run_at", "created_at", "updated_at"):
        v = d.get(field)
        if v and hasattr(v, "isoformat"):
            d[field] = None if v == _FAR_FUTURE else v.isoformat()
    return d
