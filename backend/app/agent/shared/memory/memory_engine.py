"""
memory_engine — agente_v3

Orchestrates parallel retrieval of all 5 memory types via asyncio.gather.
Returns a unified dict for context_ranker to score.

When intent is provided, decisions are retrieved via Atlas Vector Search
(semantic similarity to intent). Falls back to recency if index unavailable.
"""

import asyncio
import logging

from app.agent.shared.memory.decision_memory import search_decisions_semantic
from app.agent.shared.memory.episodic_memory_helper import load_episodic_memories
from app.agent.shared.memory.goal_memory_helper import load_active_goals
from app.agent.shared.memory.memory_embedder import embed_text
from app.agent.shared.memory.semantic_memory_helper import load_semantic_memories
from app.services.chat_memory import load_preferences

logger = logging.getLogger(__name__)


async def retrieve_memories(
    user_id: str,
    goal_id: str | None,
    db,
    intent: str = "",
    memory_depth: int = 10,
    conversation_id: str | None = None,
    recent_conversations: int = 3,
) -> dict:
    """Fetch all memory types concurrently. Never raises — each type falls back to empty.

    memory_depth: tope de items para decisions/semantic (no ligado a plan).
    conversation_id: la actual, que se excluye del diario (ya esta en el historial).
    """
    # Embed intent for semantic decision retrieval; None falls back to recency in search_decisions_semantic
    intent_embedding = await embed_text(intent) if intent else None
    decisions_limit = memory_depth if memory_depth else 5

    results = await asyncio.gather(
        load_active_goals(db, user_id),                                                     # results[0]
        load_semantic_memories(db, user_id),                                                # results[1]
        load_episodic_memories(db, user_id, limit=recent_conversations, exclude_conversation=conversation_id),  # results[2]
        search_decisions_semantic(db, user_id, intent_embedding, goal_id, limit=decisions_limit),  # results[3]
        load_preferences(user_id, db),                                                      # results[4]
        return_exceptions=True,
    )

    def _safe(val, fallback):
        return fallback if isinstance(val, Exception) else (val or fallback)

    memories = {
        "goals":      _safe(results[0], []),
        "semantic":   _safe(results[1], []),
        "episodic":   _safe(results[2], []),
        "decisions":  _safe(results[3], []),
        "structured": _safe(results[4], {}),
    }

    for key, exc in enumerate(results):
        if isinstance(exc, Exception):
            labels = ["goals", "semantic", "episodic", "decisions", "structured"]
            logger.error("[memory_engine] %s retrieval failed: %s", labels[key], exc)

    return memories

