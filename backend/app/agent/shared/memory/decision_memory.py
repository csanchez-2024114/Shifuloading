"""
decision_memory — agente_v3

CRUD para user_decision_memory (Decision Memory).
Saves embeddings on write; uses Atlas $vectorSearch on read when available,
falls back to recency-based load if index not yet created.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.agent.shared.memory.memory_embedder import embed_text

logger = logging.getLogger(__name__)

_COLLECTION = "user_decision_memory"
_VECTOR_INDEX = "v3_decisions_vector_index"


async def save_decision(
    db,
    user_id: str,
    conversation_id: str,
    goal_id: str | None,
    context: str,
    decision: str,
    alternatives: list,
    reason: str,
) -> str | None:
    """Insert a decision record with embedding. Returns decision_id or None on failure."""
    if db is None:
        return None
    decision_id = str(uuid4())
    doc = {
        "user_id":         user_id,
        "decision_id":     decision_id,
        "goal_id":         goal_id,
        "context":         context,
        "decision":        decision,
        "alternatives":    alternatives,
        "reason":          reason,
        "conversation_id": conversation_id,
        "created_at":      datetime.now(timezone.utc).isoformat(),
    }
    # Generate embedding for semantic retrieval — silently skipped if OpenAI unavailable
    embedding = await embed_text(f"{context} {decision}")
    if embedding:
        doc["embedding"] = embedding

    try:
        await db[_COLLECTION].insert_one(doc)
        return decision_id
    except Exception as exc:
        logger.error("[decision_memory] save_decision failed: %s", exc)
        return None


async def search_decisions_semantic(
    db,
    user_id: str,
    intent_embedding: list[float],
    goal_id: str | None = None,
    limit: int = 5,
) -> list:
    """Return decisions ranked by semantic similarity to intent_embedding.

    Uses Atlas $vectorSearch. Falls back to load_decisions() (recency) if the
    index does not exist or Atlas search is unavailable.
    """
    if db is None or not intent_embedding:
        return await load_decisions(db, user_id, goal_id, limit)

    pipeline = [
        {
            "$vectorSearch": {
                "index":       _VECTOR_INDEX,
                "path":        "embedding",
                "queryVector": intent_embedding,
                "numCandidates": limit * 10,
                "limit":       limit,
                "filter":      {"user_id": user_id},
            }
        },
        {"$project": {"_id": 0, "embedding": 0}},
    ]
    if goal_id:
        pipeline.insert(1, {"$match": {"goal_id": goal_id}})

    try:
        docs = await db[_COLLECTION].aggregate(pipeline).to_list(length=limit)
        if docs:
            return docs
        # Empty result — index exists but no embedded docs yet; fall through
    except Exception as exc:
        logger.debug("[decision_memory] vectorSearch unavailable (%s) — using recency fallback", exc)

    return await load_decisions(db, user_id, goal_id, limit)


async def load_decisions(db, user_id: str, goal_id: str | None, limit: int = 5) -> list:
    """Return recent decisions for the user (recency-based fallback)."""
    if db is None:
        return []
    try:
        query: dict = {"user_id": user_id}
        if goal_id:
            query["goal_id"] = goal_id
        cursor = db[_COLLECTION].find(query, {"_id": 0, "embedding": 0}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as exc:
        logger.error("[decision_memory] load_decisions failed: %s", exc)
        return []

