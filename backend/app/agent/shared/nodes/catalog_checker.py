"""
catalog_checker — agente_v3 validation layer

Checks that every app in apps_involved is supported in the catalog DB.
Runs in parallel with auth_validator and tavily_searcher.

Catalog app states (active × visible):
  active=True,  visible=True  → Available   — usable by agent, listed in catalog
  active=True,  visible=False → Beta/Internal — usable by agent, hidden from catalog
  active=False, visible=True  → Maintenance  — NOT usable, visible as "unavailable"
  active=False, visible=False → Archived     — NOT usable, hidden from catalog

Writes to validation_reports (reducer — safe for parallel execution).
"""

import logging
import os
from collections import defaultdict

from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.utils.app_resolver import resolve_app_key
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print
from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)


def _dev_box(apps: list, catalog: dict, reports: list) -> None:
    lines = []
    for r in reports:
        app  = r["app"]
        doc  = catalog.get(app.lower(), {})
        flag = "✓" if r["status"] == "ok" else "✗"
        reason = r.get("reason", "not_found")
        state  = (
            "available"  if (doc.get("active") and doc.get("visible"))
            else "beta"       if (doc.get("active") and not doc.get("visible"))
            else "maintenance" if (not doc.get("active") and doc.get("visible"))
            else "archived"   if doc
            else "not_found"
        )
        lines.append(f"  {flag} {app:<12} state={state}  reason={reason}")
    dev_print(
        f"\n┌─ Catalog Checker ─────────────────────────────────────────\n"
        + "".join(f"│{l}\n" for l in lines)
        + f"└────────────────────────────────────────────────────────────"
    )


async def catalog_checker_node(state: ShifuState) -> dict:
    apps = state.get("apps_involved") or []
    mode = state.get("catalog_query_mode") or ("validate" if apps else None)

    logger.info("[catalog_checker] ▶ mode=%s  apps_to_check=%s", mode, apps)

    if not apps and mode != "list_available":
        logger.info("[catalog_checker] skip — no apps_involved and mode=%s", mode)
        return {"validation_reports": [], "catalog_available_apps": None, "catalog_apps_grouped": None}

    db = mongo_manager.db
    if db is None:
        logger.error("[catalog_checker] DB not available")
        return {
            "validation_reports": [
                {"source": "catalog", "app": a, "status": "error",
                 "message": "Catalog DB unavailable"} for a in apps
            ],
            "catalog_available_apps": None,
            "catalog_apps_grouped": None,
        }

    # ── list_available: active=True AND visible not explicitly False ────────────
    # "visible" field may be absent on legacy docs — treat absence as True.
    if mode == "list_available":
        cursor = db["catalog_apps"].find(
            {"active": True, "visible": {"$ne": False}},
            {"nameApi": 1, "name": 1, "category": 1},
        )
        docs = await cursor.to_list(length=None)

        grouped: dict[str, list] = defaultdict(list)
        available: list[str] = []
        for doc in docs:
            display = (doc.get("name") or doc.get("nameApi") or "").strip()
            if not display:
                continue
            available.append(display)
            cat = (doc.get("category") or "other").strip()
            grouped[cat].append(display)

        available_sorted = sorted(available)
        grouped_sorted   = {cat: sorted(apps) for cat, apps in sorted(grouped.items())}

        logger.info("[catalog_checker] ◀ list_available — %d public apps  %d categories",
                    len(available_sorted), len(grouped_sorted))
        if DEV_MODE:
            cats_summary = {c: len(a) for c, a in grouped_sorted.items()}
            dev_print(
                f"\n┌─ Catalog Checker ─────────────────────────────────────────\n"
                f"│ mode        : list_available\n"
                f"│ public apps : {len(available_sorted)}\n"
                f"│ categories  : {cats_summary}\n"
                f"└────────────────────────────────────────────────────────────"
            )
        return {
            "validation_reports":   [],
            "catalog_available_apps": available_sorted,
            "catalog_apps_grouped":   grouped_sorted,
        }

    # ── validate: load all catalog docs to check active + visible per app ────
    cursor   = db["catalog_apps"].find({}, {"nameApi": 1, "active": 1, "visible": 1})
    all_docs = await cursor.to_list(length=None)
    catalog  = {
        doc["nameApi"].lower().replace(" ", "_"): doc
        for doc in all_docs if doc.get("nameApi")
    }
    logger.info("[catalog_checker] catalog loaded — %d total apps in DB", len(catalog))

    reports = []
    for app in apps:
        app_key = await resolve_app_key(app.lower())
        doc = catalog.get(app_key)

        if doc is None:
            # Not in catalog at all
            reports.append({
                "source": "catalog", "app": app, "status": "error",
                "reason": "not_found",
                "message": f"'{app}' is not a supported integration.",
            })

        elif not doc.get("active") and doc.get("visible"):
            # active=False, visible=True → Maintenance
            reports.append({
                "source": "catalog", "app": app, "status": "error",
                "reason": "maintenance",
                "message": f"'{app}' is temporarily unavailable. Please try again later.",
            })

        elif not doc.get("active") and not doc.get("visible"):
            # active=False, visible=False → Archived
            reports.append({
                "source": "catalog", "app": app, "status": "error",
                "reason": "archived",
                "message": f"'{app}' is not a supported integration.",
            })

        else:
            # active=True (visible=True → Available; visible=False → Beta/Internal)
            # Both are usable by the agent
            reports.append({"source": "catalog", "app": app, "status": "ok"})

    ok_count  = sum(1 for r in reports if r["status"] == "ok")
    err_count = sum(1 for r in reports if r["status"] == "error")
    logger.info("[catalog_checker] ◀ result — ✓ %d ok  ✗ %d error  (apps=%s)",
                ok_count, err_count, [r["app"] for r in reports])

    if DEV_MODE:
        _dev_box(apps, catalog, reports)

    return {"validation_reports": reports, "catalog_available_apps": None, "catalog_apps_grouped": None}

