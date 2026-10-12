"""
document_chunks — agente_v3

Chunking + Atlas Vector Search for documents too large to inline directly
into the prompt (see _SHORT_DOC_CHAR_BUDGET in document_analyzer.py). Same
pattern as decision_memory.py's search_decisions_semantic: $vectorSearch on
read, with a recency-based fallback if the Atlas index isn't available.

Atlas Search index required on document_chunks (created manually in the
Atlas UI/API — cannot be created via pymongo.create_index):
  Name : v3_document_chunks_vector_index
  Definition:
    {
      "fields": [
        {"type": "vector", "path": "embedding",
         "numDimensions": 1536, "similarity": "cosine"},
        {"type": "filter", "path": "conversation_id"},
        {"type": "filter", "path": "file_id"}
      ]
    }
"""

import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.agent.shared.memory.memory_embedder import embed_text

logger = logging.getLogger(__name__)

_COLLECTION = "document_chunks"
_VECTOR_INDEX = "v3_document_chunks_vector_index"
_CHUNK_SIZE = 1200
_CHUNK_OVERLAP = 150


async def chunk_and_embed(
    db, file_id: str, conversation_id: str | None, user_id: str | None, filename: str, text: str,
) -> int:
    """Splits text, embeds each chunk, and (re)inserts them for file_id.
    Returns the number of chunks written (0 on failure)."""
    if db is None or not text:
        return 0

    try:
        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP,
        )
        pieces = splitter.split_text(text)
    except Exception as exc:
        logger.error("[document_chunks] split failed file_id=%s: %s", file_id, exc)
        return 0

    docs = []
    for i, piece in enumerate(pieces):
        embedding = await embed_text(piece, max_chars=_CHUNK_SIZE * 4)
        if not embedding:
            continue
        docs.append({
            "file_id": file_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "filename": filename,
            "chunk_index": i,
            "text": piece,
            "embedding": embedding,
        })

    if not docs:
        return 0

    try:
        # Re-chunking the same file (e.g. re-uploaded) replaces its old chunks
        # instead of accumulating duplicates.
        await db[_COLLECTION].delete_many({"file_id": file_id})
        await db[_COLLECTION].insert_many(docs)
        logger.info("[document_chunks] embedded file_id=%s chunks=%d", file_id, len(docs))
        return len(docs)
    except Exception as exc:
        logger.error("[document_chunks] insert failed file_id=%s: %s", file_id, exc)
        return 0


async def search_document_chunks(
    db, conversation_id: str | None, query_embedding: list[float],
    file_ids: list[str] | None = None, limit: int = 8,
) -> list[dict]:
    """Returns the top-K chunks most relevant to query_embedding, scoped to
    conversation_id (+ file_ids if given, to compare documents A vs B
    separately without mixing passages). Falls back to the most recent
    chunks per file if Atlas $vectorSearch is unavailable — never raises."""
    if db is None or not conversation_id:
        return []

    if not query_embedding:
        return await _recent_chunks_fallback(db, conversation_id, file_ids, limit)

    match_filter: dict = {"conversation_id": conversation_id}
    if file_ids:
        match_filter["file_id"] = {"$in": file_ids}

    pipeline = [
        {
            "$vectorSearch": {
                "index": _VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": limit * 10,
                "limit": limit,
                "filter": match_filter,
            }
        },
        {
            "$project": {
                "_id": 0, "embedding": 0,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    try:
        docs = await db[_COLLECTION].aggregate(pipeline).to_list(length=limit)
        if docs:
            return docs
        # Empty result — index exists but nothing matched; fall through
    except Exception as exc:
        logger.debug("[document_chunks] vectorSearch unavailable (%s) — using recency fallback", exc)

    return await _recent_chunks_fallback(db, conversation_id, file_ids, limit)


async def _recent_chunks_fallback(
    db, conversation_id: str, file_ids: list[str] | None, limit: int,
) -> list[dict]:
    query: dict = {"conversation_id": conversation_id}
    if file_ids:
        query["file_id"] = {"$in": file_ids}
    try:
        cursor = (
            db[_COLLECTION]
            .find(query, {"_id": 0, "embedding": 0})
            .sort("chunk_index", 1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        for d in docs:
            d["score"] = 0.0
        return docs
    except Exception as exc:
        logger.error("[document_chunks] recency fallback failed: %s", exc)
        return []
