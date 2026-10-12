"""
agent_bus — inter-agent messaging service

MongoDB-backed message queue that lets any part of the system (workers,
external triggers, other agents) post messages to a specific conversation.
The agent_bus_loader context node drains these messages each turn and
injects them into ChatState as bus_messages.

Collection: agent_bus_messages
  {user_id, conversation_id, source, message_type, payload,
   status (pending|delivered), created_at, expires_at (TTL)}
"""

import logging
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_COL = "agent_bus_messages"
_DEFAULT_TTL_MINUTES = 60


async def post_message(
    db: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    message_type: str,
    payload: dict,
    source: str = "system",
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
) -> str:
    """
    Post a message to the agent bus for a specific conversation.
    Returns the inserted _id as string.

    message_type examples: "workflow_result", "research_complete",
    "agent_notification", "external_trigger"
    """
    now = datetime.now(timezone.utc)
    doc = {
        "user_id":         user_id,
        "conversation_id": conversation_id,
        "source":          source,
        "message_type":    message_type,
        "payload":         payload,
        "status":          "pending",
        "created_at":      now,
        "expires_at":      now + timedelta(minutes=ttl_minutes),
    }
    result = await db[_COL].insert_one(doc)
    logger.info(
        "[agent_bus] posted message_type=%s source=%s user=%s conversation=%s",
        message_type, source, user_id, conversation_id,
    )
    return str(result.inserted_id)


async def drain_messages(
    db: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 10,
) -> list[dict]:
    """
    Atomically fetch-and-mark-delivered all pending messages for this conversation.
    Messages are consumed exactly once — they won't appear on the next turn.

    Returns list of {source, message_type, payload, created_at}.
    """
    now = datetime.now(timezone.utc)

    cursor = db[_COL].find(
        {
            "user_id":         user_id,
            "conversation_id": conversation_id,
            "status":          "pending",
            "expires_at":      {"$gt": now},
        }
    ).sort("created_at", 1).limit(limit)

    docs = await cursor.to_list(limit)
    if not docs:
        return []

    ids = [d["_id"] for d in docs]
    await db[_COL].update_many(
        {"_id": {"$in": ids}},
        {"$set": {"status": "delivered", "delivered_at": now}},
    )

    messages = [
        {
            "source":       d.get("source", "system"),
            "message_type": d.get("message_type", "info"),
            "payload":      d.get("payload") or {},
            "created_at":   d["created_at"].isoformat() if isinstance(d.get("created_at"), datetime) else str(d.get("created_at", "")),
        }
        for d in docs
    ]

    logger.info(
        "[agent_bus] drained %d messages user=%s conversation=%s",
        len(messages), user_id, conversation_id,
    )
    return messages
