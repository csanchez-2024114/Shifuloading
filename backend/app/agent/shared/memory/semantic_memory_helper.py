"""
semantic_memory_helper — agente_v3

Lee user_semantic_memory: un documento por hecho ({user_id, key, value, status, ...}), el mismo esquema que /me/memories
y que escribe memory_learner. Sin lógica de ranking — solo DB access.
"""

import logging

logger = logging.getLogger(__name__)


async def load_semantic_memories(db, user_id: str, limit: int = 30) -> list:
    """Hechos activos del usuario, los mas recientes primero: [{key, value}]."""
    if db is None:
        return []
    try:
        cursor = db["user_semantic_memory"].find(
            {"user_id": user_id, "status": "active"},
            {"_id": 0, "key": 1, "value": 1, "last_seen_at": 1},
        ).sort("last_seen_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as exc:
        logger.error("[semantic_memory_helper] load_semantic_memories failed: %s", exc)
        return []
