"""
catalog_cache — agente_v3

Shared TTL cache for the active app catalog (nameApi keys).
Extracted from semantic_intake so that app_resolver can consume it
without importing from a sibling node.
"""

import asyncio
import logging
import time

from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)

_catalog_cache: dict = {"apps": None, "ts": 0.0}
_CATALOG_TTL = 60.0
_lock = asyncio.Lock()  # ponytail: global lock prevents duplicate refreshes under concurrency


async def get_catalog_apps() -> list[str]:
    """Return active app nameApi keys from the catalog (cached 60 s)."""
    now = time.monotonic()
    if _catalog_cache["apps"] is not None and now - _catalog_cache["ts"] < _CATALOG_TTL:
        return _catalog_cache["apps"]
    async with _lock:
        # Re-check after acquiring lock — another coroutine may have refreshed already
        now = time.monotonic()
        if _catalog_cache["apps"] is not None and now - _catalog_cache["ts"] < _CATALOG_TTL:
            return _catalog_cache["apps"]
        db = mongo_manager.db
        if db is None:
            return []
        cursor = db["catalog_apps"].find({"active": True}, {"nameApi": 1})
        docs   = await cursor.to_list(length=None)
        apps   = sorted(doc["nameApi"].lower().replace(" ", "_") for doc in docs if doc.get("nameApi"))
        _catalog_cache.update({"apps": apps, "ts": now})
        logger.info("[catalog_cache] refreshed — %d apps", len(apps))
    return apps
