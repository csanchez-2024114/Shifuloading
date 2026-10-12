"""
Workflow Analytics Service — persists per-run metrics and serves dashboard Card data.

Each workflow defines:
  metrics: [{key, source, field, label}]  — what to extract from step_results
  charts:  [{id, type, title, metric_key, icon, iconColor, w, h}]  — how to visualize

After every run the executor extracts metric values and stores one document here.
The frontend queries GET /workflows/{id}/analytics to receive Card[] ready for DynamicChartCard.
"""
import json
import re as _re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

WORKFLOW_ANALYTICS = "workflow_analytics"


# ── Write ─────────────────────────────────────────────────────────────────────

async def save_run_analytics(
    *,
    workflow_id: str,
    run_id: str,
    workflow_name: str,
    user_id: str,
    status: str,
    metrics: Dict[str, Any],
    duration_ms: int,
    db: AsyncIOMotorDatabase,
    workspace_id: Optional[str] = None,
    board_id: Optional[str] = None,
) -> str:
    """Inserts one analytics document per completed run. Returns the inserted _id."""
    doc = {
        "workflow_id": workflow_id,
        "run_id": run_id,
        "workflow_name": workflow_name,
        "user_id": user_id,
        "status": status,
        "metrics": metrics,
        "duration_ms": duration_ms,
        "timestamp": datetime.now(timezone.utc),
    }
    if workspace_id:
        doc["workspace_id"] = workspace_id
    if board_id:
        doc["board_id"] = board_id
    result = await db[WORKFLOW_ANALYTICS].insert_one(doc)
    return str(result.inserted_id)


# ── Read ──────────────────────────────────────────────────────────────────────

async def get_workflow_analytics(
    workflow_id: str,
    db: AsyncIOMotorDatabase,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Returns the last `limit` analytics records for a workflow, newest first."""
    docs = (
        await db[WORKFLOW_ANALYTICS]
        .find({"workflow_id": workflow_id})
        .sort("timestamp", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return [_serialize(d) for d in docs]


async def get_user_dashboard(
    user_id: str,
    db: AsyncIOMotorDatabase,
    limit_per_workflow: int = 30,
    workspace_id: Optional[str] = None,
    board_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Returns analytics grouped by workflow (for the all-workflows dashboard view)."""
    match_stage: Dict[str, Any] = {"user_id": user_id}
    if workspace_id:
        match_stage["workspace_id"] = workspace_id
    if board_id:
        match_stage["board_id"] = board_id
    pipeline = [
        {"$match": match_stage},
        {"$sort": {"timestamp": -1}},
        {
            "$group": {
                "_id": "$workflow_id",
                "workflow_name": {"$first": "$workflow_name"},
                "last_run": {"$first": "$timestamp"},
                "last_status": {"$first": "$status"},
                "runs": {
                    "$push": {
                        "run_id": "$run_id",
                        "timestamp": "$timestamp",
                        "status": "$status",
                        "metrics": "$metrics",
                        "duration_ms": "$duration_ms",
                    }
                },
            }
        },
        {"$addFields": {"runs": {"$slice": ["$runs", limit_per_workflow]}}},
    ]
    docs = await db[WORKFLOW_ANALYTICS].aggregate(pipeline).to_list(length=100)
    return [
        {
            "workflow_id": str(d["_id"]),
            "workflow_name": d.get("workflow_name", ""),
            "last_run": d["last_run"].isoformat() if d.get("last_run") else "",
            "last_status": d.get("last_status", ""),
            "runs": [_serialize_run(r) for r in d.get("runs", [])],
        }
        for d in docs
    ]


async def get_workflow_cards(
    workflow_id: str,
    db: AsyncIOMotorDatabase,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """
    Builds frontend-ready Card objects for a workflow's dashboard.
    Uses the workflow's `charts` config + analytics records to fill `data`.

    Card data format follows the DynamicChartCard / ChartRenderer spec:
      line  → [{name: str, ventas: number}]
      pie   → [{name: str, value: number}]
      bar   → [{categoria: str, stock: number, demanda: number}]
      area  → [{mes: str, web: number, app: number}]
    """
    try:
        wf = await db["workflows"].find_one({"_id": ObjectId(workflow_id)})
    except Exception:
        wf = None

    workflow_name = (wf or {}).get("name", "Workflow")
    workflow_status = (wf or {}).get("status", "active")
    charts_config: List[Dict] = (wf or {}).get("charts", [])

    records = await get_workflow_analytics(workflow_id, db, limit=limit)

    cards: List[Dict[str, Any]] = []

    if charts_config:
        for chart in charts_config:
            card = _build_card(chart, workflow_id, workflow_name, workflow_status, records)
            if card:
                cards.append(card)
    else:
        # Auto-generate a run-history line chart when no charts are configured yet
        cards.append(
            _auto_run_history_card(workflow_id, workflow_name, workflow_status, records)
        )

    return cards


# ── Card builders ─────────────────────────────────────────────────────────────

def _build_card(
    chart: Dict[str, Any],
    workflow_id: str,
    workflow_name: str,
    workflow_status: str,
    records: List[Dict],
) -> Optional[Dict[str, Any]]:
    chart_id = chart.get("id", "chart")
    chart_type = chart.get("type", "line")
    title = chart.get("title", chart_id)
    subtitle = chart.get("subtitle", "Historial de ejecuciones")
    metric_key = chart.get("metric_key", "")
    icon = chart.get("icon", "Activity")
    icon_color = chart.get("iconColor", "text-blue-600")
    w = chart.get("w", 3)
    h = chart.get("h", 3)

    data = _build_chart_data(chart_type, metric_key, records)
    info_html = _build_info_html(chart_type, metric_key, title, records)

    return {
        "id": f"{workflow_id}_{chart_id}",
        "type": chart_type,
        "title": title,
        "subtitle": subtitle,
        "icon": icon,
        "iconColor": icon_color,
        "status": workflow_status,
        "w": w,
        "h": h,
        "sources": [
            {
                "initial": (workflow_name[0].upper() if workflow_name else "W"),
                "color": "bg-blue-500",
                "name": workflow_name,
                "status": workflow_status,
            }
        ],
        "data": data,
        "info": {
            "type": "standard",
            "title": f"Análisis: {title}",
            "icon": "Info",
            "color": "text-blue-600",
            "bg": "bg-blue-50/60",
            "html": info_html,
        },
    }


def _build_chart_data(
    chart_type: str, metric_key: str, records: List[Dict]
) -> Any:
    """Build the chart-specific data array from analytics records."""
    if chart_type == "line":
        # Each run → one data point {name: date, ventas: numeric_metric}
        data = []
        for r in reversed(records):
            label = _ts_label(r.get("timestamp", ""))
            val = _numeric_metric(r.get("metrics", {}), metric_key)
            data.append({"name": label, "ventas": val})
        return data

    elif chart_type == "area":
        # Two metrics mapped to "web" and "app" keys
        # chart.metric_key expected to be "key1|key2"
        keys = metric_key.split("|")
        k1 = keys[0].strip() if len(keys) > 0 else metric_key
        k2 = keys[1].strip() if len(keys) > 1 else ""
        data = []
        for r in reversed(records):
            label = _ts_label(r.get("timestamp", ""))
            m = r.get("metrics", {})
            data.append({
                "mes": label,
                "web": _numeric_metric(m, k1),
                "app": _numeric_metric(m, k2) if k2 else 0,
            })
        return data

    elif chart_type == "bar":
        # Expect last run's metric to be a JSON dict {category: {stock, demanda}}
        # OR two metric keys "key1|key2" plotted per-run
        keys = metric_key.split("|")
        if len(keys) == 2:
            k1, k2 = keys[0].strip(), keys[1].strip()
            data = []
            for r in reversed(records[-10:]):  # last 10 runs
                label = _ts_label(r.get("timestamp", ""))
                m = r.get("metrics", {})
                data.append({
                    "categoria": label,
                    "stock": _numeric_metric(m, k1),
                    "demanda": _numeric_metric(m, k2),
                })
            return data
        # Single dict metric
        last_metrics = records[0].get("metrics", {}) if records else {}
        raw = last_metrics.get(metric_key, {})
        if isinstance(raw, (str, bytes)):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if isinstance(raw, dict):
            return [
                {"categoria": k, "stock": v.get("stock", v) if isinstance(v, dict) else v, "demanda": v.get("demanda", 0) if isinstance(v, dict) else 0}
                for k, v in raw.items()
            ]
        return []

    elif chart_type == "pie":
        # Aggregate last run's categorical metric OR distribution across all runs
        last_metrics = records[0].get("metrics", {}) if records else {}
        raw = last_metrics.get(metric_key, {})
        if isinstance(raw, (str, bytes)):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if isinstance(raw, dict):
            return [{"name": k, "value": v} for k, v in raw.items()]
        # Fall back: pie with completed vs failed counts
        completed = sum(1 for r in records if r.get("status") == "completed")
        failed = len(records) - completed
        return [{"name": "Completado", "value": completed}, {"name": "Fallido", "value": failed}]

    return []


def _auto_run_history_card(
    workflow_id: str, workflow_name: str, status: str, records: List[Dict]
) -> Dict[str, Any]:
    """Fallback card: line chart of successful runs over time."""
    data = []
    for r in reversed(records):
        label = _ts_label(r.get("timestamp", ""))
        data.append({"name": label, "ventas": 1 if r.get("status") == "completed" else 0})

    last_ts = records[0].get("timestamp", "")[:10] if records else "sin datos"
    total = len(records)
    ok = sum(1 for r in records if r.get("status") == "completed")

    return {
        "id": f"{workflow_id}_run_history",
        "type": "line",
        "title": "Ejecuciones",
        "subtitle": "Historial de runs",
        "icon": "Activity",
        "iconColor": "text-indigo-600",
        "status": status,
        "w": 3,
        "h": 3,
        "sources": [
            {
                "initial": (workflow_name[0].upper() if workflow_name else "W"),
                "color": "bg-indigo-500",
                "name": workflow_name,
                "status": status,
            }
        ],
        "data": data,
        "info": {
            "type": "standard",
            "title": "Resumen de ejecuciones",
            "icon": "Activity",
            "color": "text-indigo-600",
            "bg": "bg-indigo-50/60",
            "html": f"Último run: <strong>{last_ts}</strong>. Total: {total} ejecuciones, {ok} exitosas.",
        },
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts_label(ts: str) -> str:
    """Format ISO timestamp to 'DD/MM' label."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%d/%m")
    except Exception:
        return ts[:10] if ts else "?"


def _numeric_metric(metrics: dict, key: str) -> float:
    """Extract a numeric value from a metrics dict. Returns 0 if absent or not numeric."""
    val = metrics.get(key, 0)
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _build_info_html(chart_type: str, metric_key: str, title: str, records: List[Dict]) -> str:
    if not records:
        return "Sin datos de ejecuciones aún."
    values = []
    for r in records:
        v = _numeric_metric(r.get("metrics", {}), metric_key)
        if v:
            values.append(v)
    if not values:
        last_ts = records[0].get("timestamp", "")[:10]
        return f"Último run: <strong>{last_ts}</strong>. Configura métricas para ver tendencias."
    avg = sum(values) / len(values)
    max_v = max(values)
    return (
        f"<strong>{title}</strong>: promedio {avg:.1f}, máximo {max_v:.0f} en los últimos {len(records)} runs."
    )


def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "workflow_id": doc.get("workflow_id", ""),
        "run_id": doc.get("run_id", ""),
        "workflow_name": doc.get("workflow_name", ""),
        "status": doc.get("status", ""),
        "metrics": doc.get("metrics", {}),
        "duration_ms": doc.get("duration_ms", 0),
        "timestamp": doc["timestamp"].isoformat() if doc.get("timestamp") else "",
    }


def _serialize_run(r: dict) -> dict:
    return {
        "run_id": r.get("run_id", ""),
        "timestamp": r["timestamp"].isoformat() if r.get("timestamp") else "",
        "status": r.get("status", ""),
        "metrics": r.get("metrics", {}),
        "duration_ms": r.get("duration_ms", 0),
    }
