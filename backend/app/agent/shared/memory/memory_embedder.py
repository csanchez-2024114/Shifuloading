"""
memory_embedder — agente_v3

Shared async embedding utility for the memory system.
Uses text-embedding-3-small (1536 dims, $0.02/1M tokens).

Atlas Vector Search index required on user_decision_memory:
  Name : v3_decisions_vector_index
  Definition:
    {
      "fields": [
        {"type": "vector", "path": "embedding",
         "numDimensions": 1536, "similarity": "cosine"},
        {"type": "filter", "path": "user_id"}
      ]
    }
"""

import logging
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

# ponytail: one shared model instance — OpenAI client is thread-safe
_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


async def embed_text(text: str, max_chars: int = 2000) -> list[float] | None:
    """Return a 1536-dim embedding for text. Returns None on failure.

    max_chars defaults to 2000 (decision-memory callers pass short context
    strings); document_chunks.py passes a larger value sized to its own
    chunk_size so chunks aren't silently truncated before embedding.
    """
    if not text or not text.strip():
        return None
    try:
        return await _embeddings.aembed_query(text[:max_chars])
    except Exception as exc:
        logger.warning("[memory_embedder] embed_text failed: %s", exc)
        return None
