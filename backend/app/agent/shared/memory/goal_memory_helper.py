"""
goal_memory_helper — agente_v3

CRUD para user_active_goals (Goal Memory).
Sin lógica de ranking — solo DB access.
"""

import logging

logger = logging.getLogger(__name__)


async def load_active_goals(db, user_id: str) -> list:
    """Return all active goals for the user, sorted newest first."""
    if db is None:
        return []
    try:
        cursor = db["user_active_goals"].find(
            {"user_id": user_id, "status": "active"},
            {"_id": 0},
        ).sort("created_at", -1)
        return await cursor.to_list(length=20)
    except Exception as exc:
        logger.error("[goal_memory_helper] load_active_goals failed: %s", exc)
        return []
