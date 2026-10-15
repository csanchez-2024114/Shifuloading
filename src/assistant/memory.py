"""Memoria: checkpointer (corto plazo) y store (largo plazo) sobre MongoDB, más chequeos de arranque."""
from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone

import openai
import pymongo
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.store.mongodb import MongoDBStore
from pymongo.errors import PyMongoError

from assistant.config import ConfigError, Settings

logger = logging.getLogger(__name__)

STORE_COLLECTION = "memories"
_SEARCH_WINDOW = 200


def ping_mongo(uri: str, timeout_ms: int = 2000) -> pymongo.MongoClient:
    """Conecta a MongoDB y hace ping. Lanza ConfigError si no responde."""
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        client.close()
        safe_uri = re.sub(r"//[^@/]+@", "//***@", uri)  # oculta usuario:contraseña
        raise ConfigError(
            f"No pude conectar a MongoDB en {safe_uri}. Verifica que el servicio esté corriendo"
        ) from exc
    return client


def verify_model(api_key: str, model: str) -> str:
    """Comprueba que `model` exista para la cuenta de OpenAI; devuelve el id del modelo."""
    try:
        client = openai.OpenAI(api_key=api_key)
        ids = [m.id for m in client.models.list()]
    except openai.AuthenticationError as exc:
        raise ConfigError(
            "OPENAI_API_KEY inválida (OpenAI rechazó la autenticación). "
            "Revisa la clave en tu archivo .env"
        ) from exc
    except openai.APIConnectionError as exc:
        raise ConfigError(f"No pude contactar la API de OpenAI: {exc}") from exc
    except openai.APIError as exc:
        raise ConfigError(f"Error de la API de OpenAI al listar modelos: {exc}") from exc

    if model in ids:
        return model
    luna = sorted(i for i in ids if "luna" in i.lower())
    disponibles = ", ".join(luna) if luna else "ninguno"
    raise ConfigError(
        f"El modelo '{model}' no existe para tu cuenta. "
        f"Modelos 'luna' disponibles: {disponibles}. Ajusta LLM_MODEL en .env"
    )


def build_checkpointer(client: pymongo.MongoClient, db_name: str) -> MongoDBSaver:
    """Checkpointer síncrono (memoria de conversación por thread). No requiere setup()."""
    return MongoDBSaver(client, db_name=db_name)


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


def build_store(
    client: pymongo.MongoClient, db_name: str, semantic: bool = False, api_key: str | None = None
) -> MongoDBStore:
    """Store de memoria a largo plazo. Con `semantic` usa Atlas Vector Search (embeddings de OpenAI);
    si el índice vectorial no se puede crear (p. ej. MongoDB local), cae a búsqueda por palabras."""
    collection = client[db_name][STORE_COLLECTION]
    if semantic:
        from langchain_openai import OpenAIEmbeddings
        from langgraph.store.mongodb import create_vector_index_config

        index_config = create_vector_index_config(
            dims=EMBEDDING_DIMS,
            embed=OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=api_key),
            fields=["text"],
        )
        try:
            store = MongoDBStore(collection=collection, index_config=index_config, auto_index_timeout=60)
            logger.info("Memoria semántica activa (Atlas Vector Search, %s)", EMBEDDING_MODEL)
            return store
        except PyMongoError as exc:
            logger.warning(
                "No pude crear el índice vectorial (%s: %s). ¿Es MongoDB local sin Atlas Vector Search? "
                "Uso búsqueda por palabras.", type(exc).__name__, exc,
            )
    return MongoDBStore(collection=collection)


def memory_namespace(user_id: str) -> tuple[str, str, str]:
    return ("user", user_id, "memories")


def save_memory(store, user_id: str, text: str) -> str:
    """Guarda un recuerdo y devuelve su key (uuid hex)."""
    key = uuid.uuid4().hex
    store.put(
        memory_namespace(user_id),
        key,
        {"text": text, "created_at": datetime.now(timezone.utc).isoformat()},
    )
    return key


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", _normalize(text)) if len(w) >= 3]


def _created_at(item) -> str:
    value = getattr(item, "value", None) or {}
    created = value.get("created_at")
    if created:
        return str(created)
    fallback = getattr(item, "created_at", None)
    if isinstance(fallback, datetime):
        return fallback.isoformat()
    return str(fallback or "")


def search_memories(store, user_id: str, query: str = "", limit: int = 10) -> list[str]:
    """Devuelve textos de recuerdos: los que mejor coinciden con `query`, o los más recientes."""
    if query.strip() and getattr(store, "index_config", None):
        # Búsqueda semántica. ponytail: recuerdos guardados antes de activarla no tienen embedding y no aparecen aquí.
        items = store.search(memory_namespace(user_id), query=query, limit=limit)
        return [i.value["text"] for i in items if (i.value or {}).get("text")]
    items = store.search(memory_namespace(user_id), limit=_SEARCH_WINDOW)
    items = [i for i in items if (getattr(i, "value", None) or {}).get("text")]
    # más recientes primero (orden estable: sirve de desempate)
    items.sort(key=_created_at, reverse=True)

    words = set(_words(query))
    if words:
        scored = []
        for item in items:
            haystack = _normalize(item.value["text"])
            score = sum(1 for w in words if w in haystack)
            scored.append((score, item))
        if any(score > 0 for score, _ in scored):
            # sort estable: a igual puntaje se conserva el orden por recencia
            scored.sort(key=lambda p: p[0], reverse=True)
            items = [item for score, item in scored if score > 0]
    return [i.value["text"] for i in items[:limit]]


def startup_checks(settings: Settings) -> pymongo.MongoClient:
    """Valida API key, MongoDB y modelo (en ese orden). Devuelve el cliente de Mongo."""
    settings.require_api_key()
    client = ping_mongo(settings.mongodb_uri)
    try:
        verify_model(settings.openai_api_key, settings.llm_model)
    except Exception:
        client.close()
        raise
    return client
