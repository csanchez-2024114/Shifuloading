"""
episodic_memory_helper — agente_v3

Lee user_daily_diary: un documento por conversacion con lo que se estaba haciendo y lo pendiente (lo escribe
memory_learner). Sin lógica de ranking — solo DB access.
"""

import logging
import math
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def search_older(db, user_id: str, query_embedding: list, exclude_conversations: set,
                       top_k: int = 2, min_score: float = 0.40) -> list[dict]:
    """Conversaciones viejas del usuario parecidas en significado a lo que pide ahora (las recientes ya entran por recencia).

    Devuelve las top_k con score >= min_score, sin el embedding. Nunca lanza.
    """
    if db is None or not query_embedding or top_k <= 0:
        return []
    try:
        # ponytail: coseno en Python = O(n) por usuario (n = conversaciones con diario). Pasar a Atlas $vectorSearch
        # (como decision_memory.py) cuando un usuario llegue a ~500+ entradas.
        rows = await db["user_daily_diary"].find(
            {"user_id": user_id, "embedding": {"$exists": True}},
            {"_id": 0, "date": 1, "activities": 1, "pending": 1, "conversation_id": 1, "embedding": 1},
        ).to_list(length=None)
        scored = []
        for r in rows:
            emb = r.pop("embedding", None)  # solo para puntuar; no sale de aqui
            if not emb or r.get("conversation_id") in exclude_conversations:
                continue
            score = _cosine(query_embedding, emb)
            if score >= min_score:
                scored.append({**r, "score": round(score, 4)})
        return sorted(scored, key=lambda r: r["score"], reverse=True)[:top_k]
    except Exception as exc:
        logger.error("[episodic_memory_helper] search_older failed: %s", exc)
        return []


async def search_older_messages(db, user_id: str, query_embedding: list, exclude_conversations: set,
                                top_k: int = 3, min_score: float = 0.45) -> list[dict]:
    """Mensajes ORIGINALES del usuario (user_message_index) parecidos en significado a lo que pide ahora.

    A diferencia del diario no pierde nombres propios. Devuelve las top_k con score >= min_score, sin el embedding.
    Nunca lanza.
    """
    if db is None or not query_embedding or top_k <= 0:
        return []
    try:
        # ponytail: mismo coseno en Python; aqui n = mensajes (mas que el diario). Pasar a Atlas $vectorSearch
        # cuando un usuario llegue a ~2000+ mensajes indexados.
        rows = await db["user_message_index"].find(
            {"user_id": user_id, "embedding": {"$exists": True}},
            {"_id": 0, "date": 1, "text": 1, "conversation_id": 1, "embedding": 1},
        ).to_list(length=None)
        scored = []
        for r in rows:
            emb = r.pop("embedding", None)  # solo para puntuar; no sale de aqui
            if not emb or r.get("conversation_id") in exclude_conversations:
                continue
            score = _cosine(query_embedding, emb)
            if score >= min_score:
                scored.append({**r, "score": round(score, 4)})
        return sorted(scored, key=lambda r: r["score"], reverse=True)[:top_k]
    except Exception as exc:
        logger.error("[episodic_memory_helper] search_older_messages failed: %s", exc)
        return []


COMMITMENTS_DEFAULTS = {"enabled": True, "horizon_days": 3}  # el dato real es memory_policy.commitments
_MAX_COMMITMENTS = 5


def parse_now(value) -> datetime:
    """'Hoy' de la memoria: el reloj del turno (state["current_time_utc"], que en desarrollo puede venir simulado).
    Sin valor o ilegible, el reloj real: asi un fallo de formato no rompe el turno."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


async def load_commitments(db, user_id: str, today: datetime, horizon_days: int = 3,
                           exclude_conversation: str | None = None) -> list[dict]:
    """Compromisos con fecha del usuario en OTRAS conversaciones: con due_date, pendiente sin cerrar (done_at) y vencidos
    o por vencer dentro de horizon_days. Ordenados por fecha, maximo 5. Cada fila lleva days_left (negativo = vencido)."""
    if db is None:
        return []
    try:
        # ponytail: el filtro fino va en Python (el FakeDB de pruebas ignora operadores y son pocas filas por usuario).
        rows = await db["user_daily_diary"].find(
            {"user_id": user_id, "due_date": {"$ne": None}},
            {"_id": 0, "date": 1, "activities": 1, "pending": 1, "due_date": 1, "done_at": 1, "conversation_id": 1},
        ).to_list(length=None)
        out = []
        for r in rows:
            try:
                days_left = (datetime.strptime(str(r.get("due_date")), "%Y-%m-%d").date() - today.date()).days
            except ValueError:
                continue
            if (not r.get("pending") or r.get("done_at") or days_left > horizon_days
                    or (exclude_conversation and r.get("conversation_id") == exclude_conversation)):
                continue
            out.append({k: v for k, v in r.items() if k != "done_at"} | {"days_left": days_left})
        return sorted(out, key=lambda r: r["due_date"])[:_MAX_COMMITMENTS]
    except Exception as exc:
        logger.error("[episodic_memory_helper] load_commitments failed: %s", exc)
        return []


async def load_episodic_memories(db, user_id: str, limit: int = 3, exclude_conversation: str | None = None) -> list:
    """Lo mas reciente que hizo el usuario en OTRAS conversaciones (la actual ya esta en el historial)."""
    if db is None:
        return []
    try:
        cursor = db["user_daily_diary"].find(
            {"user_id": user_id},
            {"_id": 0, "date": 1, "activities": 1, "pending": 1, "conversation_id": 1},
        ).sort("updated_at", -1).limit(limit + 1)
        rows = await cursor.to_list(length=limit + 1)
        return [r for r in rows if not exclude_conversation or r.get("conversation_id") != exclude_conversation][:limit]
    except Exception as exc:
        logger.error("[episodic_memory_helper] load_episodic_memories failed: %s", exc)
        return []
