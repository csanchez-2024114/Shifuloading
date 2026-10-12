"""
document_cache — agente_v3

CRUD para document_extractions: evita reprocesar (descarga + OCR/parsing) el
mismo archivo en cada turno de la conversación. Mismo estilo que
decision_memory.py — upsert simple, sin embeddings (eso vive en
document_chunks.py, para documentos grandes).
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_COLLECTION = "document_extractions"


async def get_cached_extraction(db, file_id: str) -> dict | None:
    """Returns the cached extraction for file_id, or None on miss/error."""
    if db is None or not file_id:
        return None
    try:
        return await db[_COLLECTION].find_one({"file_id": file_id}, {"_id": 0})
    except Exception as exc:
        logger.error("[document_cache] get_cached_extraction failed file_id=%s: %s", file_id, exc)
        return None


async def save_extraction(
    db,
    file_id: str,
    *,
    url: str,
    filename: str,
    engine: str,
    text: str,
    page_count: int | None,
    ocr_used: bool,
    error: str | None,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> None:
    """Upserts the extraction result for file_id. Never raises — a cache
    write failure should not break the turn (just means next turn reprocesses)."""
    if db is None or not file_id:
        return
    now = datetime.now(timezone.utc)
    is_chunked = len(text or "") > 32_000
    doc = {
        "file_id": file_id,
        "url": url,
        "filename": filename,
        "engine": engine,
        "text": text or "",
        "char_count": len(text or ""),
        "page_count": page_count,
        "ocr_used": ocr_used,
        "extraction_error": error,
        "is_chunked": is_chunked,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "last_used_at": now,
    }
    try:
        await db[_COLLECTION].update_one(
            {"file_id": file_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except Exception as exc:
        logger.error("[document_cache] save_extraction failed file_id=%s: %s", file_id, exc)


async def touch_extraction(db, file_id: str) -> None:
    """Updates last_used_at on a cache hit — basis for a future TTL cleanup."""
    if db is None or not file_id:
        return
    try:
        await db[_COLLECTION].update_one(
            {"file_id": file_id},
            {"$set": {"last_used_at": datetime.now(timezone.utc)}},
        )
    except Exception as exc:
        logger.debug("[document_cache] touch_extraction failed file_id=%s: %s", file_id, exc)
