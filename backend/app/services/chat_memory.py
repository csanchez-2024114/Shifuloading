"""
chat_memory — shared service for conversation and user preference storage.

Migrated from app.agents.multiAgent.old.memory.chat_memory.
Used by: agente_v2 nodes, active V3/V4 routes, workers.

Collections:
  chat_messages    : one doc per message
  chat_context     : one doc per conversation (summary + metadata)
  user_preferences : one doc per user (dynamic schema)
  user_connected_accounts: user OAuth integrations
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

MESSAGES = "chat_messages"
CONTEXT = "chat_context"
PREFERENCES = "user_preferences"
CATALOG = "catalog_apps"
CONNECTED = "user_connected_accounts"


# ── Read ───────────────────────────────────────────────────────────────────────

async def get_conversation_messages(
    user_id: str,
    conv_id: str,
    db: AsyncIOMotorDatabase,
    limit: int = 100,
) -> List[dict]:
    """Loads full message history for a conversation (frontend display)."""
    raw = await (
        db[MESSAGES]
        .find(
            {"user_id": user_id, "conversation_id": conv_id},
            {"_id": 0, "role": 1, "content": 1, "created_at": 1, "ui_actions": 1, "quality": 1, "usage": 1},
        )
        .sort("created_at", 1)
        .limit(limit)
        .to_list(length=limit)
    )
    return [
        {
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"].isoformat() if m.get("created_at") else "",
            **({"ui_actions": m["ui_actions"]} if m.get("ui_actions") else {}),
            **({"quality": m["quality"]} if m.get("quality") else {}),
            **({"usage": m["usage"]} if m.get("usage") else {}),
        }
        for m in raw
    ]


async def load_preferences(user_id: str, db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Returns enriched preferences: { key: {value, confidence, source, updated_at} }.
    Handles legacy flat values by wrapping them as explicit/1.0.
    """
    doc = await db[PREFERENCES].find_one({"user_id": user_id})
    raw: dict = doc.get("prefs", {}) if doc else {}

    enriched: Dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, dict) and "value" in v:
            enriched[k] = v
        else:
            enriched[k] = {"value": v, "confidence": 1.0, "source": "explicit", "updated_at": None}
    return enriched


async def load_user_integrations(user_id: str, db: AsyncIOMotorDatabase) -> List[dict]:
    """Returns active integrations connected by the user."""
    docs = await (
        db[CONNECTED]
        .find(
            {"user_id": user_id, "status": "active"},
            {"_id": 0, "provider": 1, "account_id": 1},
        )
        .to_list(length=100)
    )
    return docs


# ── Write ──────────────────────────────────────────────────────────────────────

async def save_message(
    user_id: str,
    conv_id: str,
    role: str,
    content: str,
    db: AsyncIOMotorDatabase,
    *,
    ui_actions: list | None = None,
    resources: list | None = None,
    quality: dict | None = None,
    usage: dict | None = None,
) -> None:
    """Inserts a message document and increments the conversation counter.
    quality: veredictos del evaluador de calidad de esa respuesta ({attempts, rejections, final, evals})."""
    now = datetime.now(timezone.utc)
    doc: dict = {
        "user_id": user_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "created_at": now,
    }
    if ui_actions:
        doc["ui_actions"] = ui_actions
    if resources:
        doc["resources"] = resources
    if quality:
        doc["quality"] = quality
    if usage:
        doc["usage"] = usage  # tokens y costo real de la peticion que produjo esta respuesta
    await asyncio.gather(
        db[MESSAGES].insert_one(doc),
        db[CONTEXT].update_one(
            {"user_id": user_id, "conversation_id": conv_id},
            {
                "$inc": {"message_count": 1},
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "created_at": now,
                    "summary": "",
                    "title": "",
                },
            },
            upsert=True,
        ),
    )


async def upsert_preference(
    user_id: str,
    key: str,
    value: Any,
    db: AsyncIOMotorDatabase,
    *,
    confidence: float = 1.0,
    source: str = "explicit",
) -> None:
    """
    Upserts a user preference with metadata.
    Stored shape per key: { value, confidence, source, updated_at }
    """
    _IDENTITY_ALIAS_MAP = {
        "pais_origen": "user_country", "pais": "user_country", "country": "user_country",
        "empresa":     "user_company",
        "profesion":   "user_role",
        "zona_horaria": "user_timezone",
        "idioma":      "user_language",
        "jefe":        "user_boss", "boss": "user_boss",
        "correo_trabajo": "user_email_work",
        "nombre_pref": "user_name_pref",
    }
    key = _IDENTITY_ALIAS_MAP.get(key, key)

    if confidence < 0.5:
        logger.debug(f"[ChatMemory] skipping low-confidence pref user={user_id} key={key} conf={confidence:.2f}")
        return
    now = datetime.now(timezone.utc)
    pref_doc = {
        "value": value,
        "confidence": round(confidence, 3),
        "source": source,
        "updated_at": now,
    }
    await db[PREFERENCES].update_one(
        {"user_id": user_id},
        {
            "$set": {f"prefs.{key}": pref_doc, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
