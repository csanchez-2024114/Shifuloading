"""
session_state — agente_v3

Persists the state fields that LangGraph does NOT carry across ainvoke() calls
because no checkpointer is configured on the graph.

Currently: selected_accounts, available_accounts.
Collection: agent_session_state  (user_id + conversation_id compound index)
"""

import logging

logger = logging.getLogger(__name__)
_COLLECTION = "agent_session_state"


async def load_session_state(user_id: str, conversation_id: str, db) -> dict:
    """Return persisted state for a conversation. Empty dict if none found."""
    try:
        doc = await db[_COLLECTION].find_one(
            {"user_id": user_id, "conversation_id": conversation_id},
            {"selected_accounts": 1, "available_accounts": 1, "_id": 0},
        )
        return doc or {}
    except Exception as exc:
        logger.warning("[session_state] load failed: %s", exc)
        return {}


async def save_session_state(
    user_id: str,
    conversation_id: str,
    db,
    *,
    selected_accounts: dict | None,
    available_accounts: dict | None,
) -> None:
    """Upsert persisted state for a conversation. Silently ignores DB errors."""
    try:
        await db[_COLLECTION].update_one(
            {"user_id": user_id, "conversation_id": conversation_id},
            {"$set": {
                "selected_accounts":  selected_accounts,
                "available_accounts": available_accounts,
            }},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("[session_state] save failed: %s", exc)
