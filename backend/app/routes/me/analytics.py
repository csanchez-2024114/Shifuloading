"""
/api/v1/me/analytics — Home/Insights dashboard: 9 chart endpoints backed by real data.

Router is mounted with prefix "/api/v1/me/analytics" in main.py; paths below are relative
to that. Each endpoint returns the raw `data` shape expected by the matching frontend hook
(`hyper-shifu-app/src/hooks/useFetchAnalytics*.ts` + `src/types/chart-card.types.ts`) — the
Card wrapper (title/subtitle/sources/info) is built client-side, not here.

Endpoints:
  GET /gauge    — daily token usage vs plan limit (quota.py + billing/plans.py)
  GET /files    — Cloudinary inventory (same source as GET /api/v1/uploads/)
  GET /pie      — intent_outcomes grouped by tool_used (workflow name)
  GET /line     — intent_outcomes count per day, last 30 days
  GET /bar      — intent_outcomes: successes vs total attempts per tool_used
  GET /area     — intent_outcomes per day: chat-triggered vs workflow-triggered
  GET /composed — intent_outcomes per day: attempts / successes / avg execution time
  GET /scatter  — workflow_runs: duration_ms vs step count vs success/failure
  GET /radar    — intent_outcomes success/failure distribution by catalog app category

`intent_outcomes` is written exclusively by WorkflowExecutor (app/workers/workflow_executor.py)
after a workflow run finishes — there is no code path today that writes an outcome without a
workflow_id, so /area's "chat" side will read as real zeros until a chat-triggered action gets
tracked into this collection too. That's an honest reflection of current instrumentation, not a
bug — see the "no fabriques" note in the Grupo G plan.

Four of these charts (bar/area/composed/scatter) repurpose an older mocked design (inventory
alerts, web-vs-app traffic, ecommerce metrics, investment ROI). None of those concepts exist in
the backend, so the field *names* in chart-card.types.ts are kept for type compatibility
(stock/demanda, web/app, visitas/conversiones/ticket, x/y/z) but are filled with the closest real
signal — and the corresponding frontend hook copy (title/subtitle/info.html) was updated to
describe what the number actually is instead of the original invented scenario.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.database import get_current_user
from app.core.constants import Collections
from app.core.quota import get_daily_tokens_used
from app.billing.plans import get_plan_rules
from app.services.cloudinary_service import cloudinary_service
from app.services.catalog_apps import get_all as get_all_catalog_apps
from app.services.workflow_analytics_service import get_user_dashboard

logger = logging.getLogger(__name__)
router = APIRouter()

_COL_OUTCOMES = "intent_outcomes"
_COL_RUNS = "workflow_runs"
_COL_WORKFLOWS = "workflows"

_LOOKBACK_DAYS = 30
_OUTCOMES_FETCH_LIMIT = 3000


# ── GET /dashboard ───────────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """Unified dashboard endpoint — returns Card[] from workflow analytics (used by useLoadDashboard)."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    cards = await get_user_dashboard(user_id, db, workspace_id=workspace_id, board_id=board_id)
    return JSONResponse(content=jsonable_encoder({"cards": cards}))


# ── Shared helpers ────────────────────────────────────────────────────────────


def _parse_ts(value: Any) -> Optional[datetime]:
    """intent_outcomes.timestamp is stored as an ISO string (WorkflowExecutor writes
    `finished_at.isoformat()`); workflow_runs.started_at/finished_at are real BSON dates.
    Normalize either shape to an aware datetime, or None if unparseable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


async def _get_user_plan(db, user_id: str) -> str:
    user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
    return (user_doc or {}).get("plan", "free")


async def _fetch_outcomes(
    db, user_id: str,
    workspace_id: Optional[str] = None,
    board_id: Optional[str] = None,
) -> List[dict]:
    """Bounded fetch — per-user analytics don't paginate yet; 3000 is generous headroom
    over the 30-day grouping windows used below."""
    query: Dict[str, Any] = {"user_id": user_id}
    if workspace_id:
        query["workspace_id"] = workspace_id
    if board_id:
        query["board_id"] = board_id
    return await (
        db[_COL_OUTCOMES]
        .find(
            query,
            {"_id": 0, "tool_used": 1, "success": 1, "execution_time_ms": 1,
             "workflow_id": 1, "timestamp": 1},
        )
        .sort("timestamp", -1)
        .limit(_OUTCOMES_FETCH_LIMIT)
        .to_list(length=_OUTCOMES_FETCH_LIMIT)
    )


def _day_buckets(n_days: int = _LOOKBACK_DAYS) -> List[str]:
    """Last n_days as 'YYYY-MM-DD' keys, oldest first, including today."""
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n_days - 1, -1, -1)]


def _day_label(day_key: str) -> str:
    return datetime.fromisoformat(day_key).strftime("%d/%m")


# ── GET /gauge ───────────────────────────────────────────────────────────────


@router.get("/gauge")
async def get_gauge_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Today's chat token usage against the plan's daily_token_limit."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    redis_client = getattr(request.app.state, "redis", None)

    plan = await _get_user_plan(db, user_id)
    limit = get_plan_rules(plan).get("daily_token_limit", -1)
    used = await get_daily_tokens_used(redis_client, user_id)

    if limit == -1:
        percentage = 0
        missing = "Plan sin límite diario de tokens"
    else:
        percentage = round(min(used / limit, 1.0) * 100) if limit > 0 else 0
        missing = f"{max(limit - used, 0)} tokens restantes hoy"

    return JSONResponse(content={"value": used, "percentage": percentage, "missing": missing})


# ── GET /files ───────────────────────────────────────────────────────────────

_FORMAT_TO_TYPE = {
    "pdf": "pdf", "csv": "csv",
    "jpg": "img", "jpeg": "img", "png": "img", "gif": "img", "webp": "img", "svg": "img",
    "xls": "xls", "xlsx": "xls",
}
_TYPE_STYLE = {
    "pdf": {"bg": "bg-red-50", "iconColor": "text-red-500"},
    "csv": {"bg": "bg-emerald-50", "iconColor": "text-emerald-500"},
    "img": {"bg": "bg-blue-50", "iconColor": "text-blue-500"},
    "xls": {"bg": "bg-green-50", "iconColor": "text-green-600"},
}


def _human_size(num_bytes: Any) -> str:
    size = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@router.get("/files")
async def get_files_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Recent files from Cloudinary — same source as GET /api/v1/uploads/."""
    user_email = current_user.get("email") or current_user.get("correo", "")
    inventory = cloudinary_service.get_user_inventory(user_email=user_email) if user_email else {}
    resources = (inventory or {}).get("resources", [])[:20]

    files = []
    for r in resources:
        fmt = (r.get("format") or "").lower()
        file_type = _FORMAT_TO_TYPE.get(fmt, "pdf")
        style = _TYPE_STYLE.get(file_type, _TYPE_STYLE["pdf"])
        name = (r.get("public_id") or "").rsplit("/", 1)[-1]
        files.append({
            "name": f"{name}.{fmt}" if fmt else (name or "archivo"),
            "size": _human_size(r.get("bytes")),
            "date": (r.get("created_at") or "")[:10],
            "type": file_type,
            "bg": style["bg"],
            "iconColor": style["iconColor"],
        })

    return JSONResponse(content=jsonable_encoder(files))


# ── GET /pie ─────────────────────────────────────────────────────────────────


@router.get("/pie")
async def get_pie_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """Distribution of executed actions by tool (workflow) used."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    outcomes = await _fetch_outcomes(db, user_id, workspace_id=workspace_id, board_id=board_id)

    counts: Dict[str, int] = defaultdict(int)
    for o in outcomes:
        name = o.get("tool_used") or "Sin nombre"
        counts[name] += 1

    data = [
        {"name": name, "value": value}
        for name, value in sorted(counts.items(), key=lambda kv: -kv[1])
    ][:10]
    return JSONResponse(content=jsonable_encoder(data))


# ── GET /line ────────────────────────────────────────────────────────────────


@router.get("/line")
async def get_line_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """Number of actions executed per day, last 30 days."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    outcomes = await _fetch_outcomes(db, user_id, workspace_id=workspace_id, board_id=board_id)

    buckets = {d: 0 for d in _day_buckets()}
    for o in outcomes:
        ts = _parse_ts(o.get("timestamp"))
        key = ts.date().isoformat() if ts else None
        if key in buckets:
            buckets[key] += 1

    data = [{"name": _day_label(k), "ventas": v} for k, v in buckets.items()]
    return JSONResponse(content=jsonable_encoder(data))


# ── GET /bar ─────────────────────────────────────────────────────────────────


@router.get("/bar")
async def get_bar_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """Successes vs total attempts per tool (workflow) used."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    outcomes = await _fetch_outcomes(db, user_id, workspace_id=workspace_id, board_id=board_id)

    totals: Dict[str, int] = defaultdict(int)
    successes: Dict[str, int] = defaultdict(int)
    for o in outcomes:
        name = o.get("tool_used") or "Sin nombre"
        totals[name] += 1
        if o.get("success"):
            successes[name] += 1

    data = [
        {"categoria": name, "stock": successes.get(name, 0), "demanda": total}
        for name, total in sorted(totals.items(), key=lambda kv: -kv[1])
    ][:10]
    return JSONResponse(content=jsonable_encoder(data))


# ── GET /area ────────────────────────────────────────────────────────────────


@router.get("/area")
async def get_area_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """Actions per day, split by trigger: chat (no workflow_id) vs workflow run."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    outcomes = await _fetch_outcomes(db, user_id, workspace_id=workspace_id, board_id=board_id)

    chat_buckets = {d: 0 for d in _day_buckets()}
    workflow_buckets = {d: 0 for d in _day_buckets()}
    for o in outcomes:
        ts = _parse_ts(o.get("timestamp"))
        key = ts.date().isoformat() if ts else None
        if key not in chat_buckets:
            continue
        if o.get("workflow_id"):
            workflow_buckets[key] += 1
        else:
            chat_buckets[key] += 1

    data = [
        {"mes": _day_label(k), "web": chat_buckets[k], "app": workflow_buckets[k]}
        for k in chat_buckets
    ]
    return JSONResponse(content=jsonable_encoder(data))


# ── GET /composed ────────────────────────────────────────────────────────────


@router.get("/composed")
async def get_composed_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """Per day: total attempts, successes, and average execution time (ms)."""
    user_id = current_user.get("id", "")
    db = request.app.state.db
    outcomes = await _fetch_outcomes(db, user_id, workspace_id=workspace_id, board_id=board_id)

    days = _day_buckets()
    attempts = {d: 0 for d in days}
    successes = {d: 0 for d in days}
    exec_times: Dict[str, List[float]] = defaultdict(list)
    for o in outcomes:
        ts = _parse_ts(o.get("timestamp"))
        key = ts.date().isoformat() if ts else None
        if key not in attempts:
            continue
        attempts[key] += 1
        if o.get("success"):
            successes[key] += 1
        exec_ms = o.get("execution_time_ms")
        if isinstance(exec_ms, (int, float)):
            exec_times[key].append(exec_ms)

    data = [
        {
            "name": _day_label(k),
            "visitas": attempts[k],
            "conversiones": successes[k],
            "ticket": round(sum(exec_times[k]) / len(exec_times[k]), 1) if exec_times.get(k) else 0,
        }
        for k in days
    ]
    return JSONResponse(content=jsonable_encoder(data))


# ── GET /scatter ─────────────────────────────────────────────────────────────


@router.get("/scatter")
async def get_scatter_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """Finished workflow runs: duration (x) vs step count (y) vs success/failure (z)."""
    user_id = current_user.get("id", "")
    db = request.app.state.db

    query: Dict[str, Any] = {"user_id": user_id, "started_at": {"$ne": None}, "finished_at": {"$ne": None}}
    if workspace_id:
        query["workspace_id"] = workspace_id
    if board_id:
        query["board_id"] = board_id

    runs = await (
        db[_COL_RUNS]
        .find(
            query,
            {"_id": 0, "started_at": 1, "finished_at": 1, "steps": 1, "status": 1},
        )
        .sort("finished_at", -1)
        .limit(200)
        .to_list(length=200)
    )

    data = []
    for r in runs:
        started = _parse_ts(r.get("started_at"))
        finished = _parse_ts(r.get("finished_at"))
        if not started or not finished:
            continue
        duration_ms = max(int((finished - started).total_seconds() * 1000), 0)
        step_count = len(r.get("steps") or [])
        data.append({
            "x": duration_ms,
            "y": step_count,
            "z": 1 if r.get("status") == "completed" else 0,
        })

    return JSONResponse(content=jsonable_encoder(data))


# ── GET /radar ───────────────────────────────────────────────────────────────


@router.get("/radar")
async def get_radar_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
    workspace_id: Optional[str] = Query(None),
    board_id: Optional[str] = Query(None),
):
    """
    Success vs failure count of executed actions, grouped by the catalog category of the
    app(s) each run touched. A run that uses apps from two categories counts toward both —
    this is a coarse distribution, not an exact partition, since intent_outcomes tracks one
    outcome per workflow run, not per step/app.
    """
    user_id = current_user.get("id", "")
    db = request.app.state.db

    query: Dict[str, Any] = {"user_id": user_id, "workflow_id": {"$ne": None}}
    if workspace_id:
        query["workspace_id"] = workspace_id
    if board_id:
        query["board_id"] = board_id

    outcomes = await (
        db[_COL_OUTCOMES]
        .find(
            query,
            {"_id": 0, "workflow_id": 1, "success": 1},
        )
        .limit(_OUTCOMES_FETCH_LIMIT)
        .to_list(length=_OUTCOMES_FETCH_LIMIT)
    )
    if not outcomes:
        return JSONResponse(content=[])

    workflow_ids = {o["workflow_id"] for o in outcomes if o.get("workflow_id")}
    valid_oids = []
    for wid in workflow_ids:
        try:
            valid_oids.append(ObjectId(wid))
        except Exception:
            continue

    workflows = (
        await db[_COL_WORKFLOWS]
        .find({"_id": {"$in": valid_oids}}, {"steps.app": 1})
        .to_list(length=len(valid_oids) or 1)
    ) if valid_oids else []
    apps_by_workflow: Dict[str, Set[str]] = {
        str(wf["_id"]): {
            (s.get("app") or "").strip().lower()
            for s in (wf.get("steps") or []) if s.get("app")
        }
        for wf in workflows
    }

    catalog = await get_all_catalog_apps(db)
    category_by_app: Dict[str, str] = {}
    for app in catalog:
        category = app.get("category") or "Otros"
        name_api = (app.get("nameApi") or "").lower().replace(" ", "_")
        name = (app.get("name") or "").lower()
        if name_api:
            category_by_app[name_api] = category
        if name:
            category_by_app[name] = category

    success_by_cat: Dict[str, int] = defaultdict(int)
    fail_by_cat: Dict[str, int] = defaultdict(int)
    for o in outcomes:
        apps = apps_by_workflow.get(o.get("workflow_id"), set())
        categories = {category_by_app.get(a, "Otros") for a in apps} or {"Otros"}
        for cat in categories:
            if o.get("success"):
                success_by_cat[cat] += 1
            else:
                fail_by_cat[cat] += 1

    all_cats = set(success_by_cat) | set(fail_by_cat)
    if not all_cats:
        return JSONResponse(content=[])
    full_mark = max((success_by_cat[c] + fail_by_cat[c] for c in all_cats), default=1) or 1

    data = [
        {
            "subject": cat,
            "A": success_by_cat.get(cat, 0),
            "B": fail_by_cat.get(cat, 0),
            "fullMark": full_mark,
        }
        for cat in sorted(all_cats)
    ][:8]

    return JSONResponse(content=jsonable_encoder(data))
