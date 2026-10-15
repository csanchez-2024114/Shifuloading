"""Memoria: checkpointer (corto plazo) y store (largo plazo) sobre MongoDB, más chequeos de arranque."""
from __future__ import annotations

import json
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
    client = None
    try:
        # dentro del try: con mongodb+srv, un host inexistente (DNS) o una URI mal formada fallan al construir el cliente
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
    except (PyMongoError, ValueError) as exc:
        if client is not None:
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


def save_memory(store, user_id: str, text: str, *, thread_id: str | None = None,
                evidence: str = "", confidence: str = "unverified") -> str:
    """Guarda un recuerdo con su procedencia y devuelve su key (uuid hex).
    confidence: "verified" (lo confirmó el verificador), "quoted" (la cita aparece literal en lo que dijo
    el usuario) o "unverified" (sin evidencia). Los recuerdos viejos solo tienen text y created_at."""
    key = uuid.uuid4().hex
    store.put(
        memory_namespace(user_id),
        key,
        {"text": text, "created_at": datetime.now(timezone.utc).isoformat(),
         "thread_id": thread_id, "evidence": evidence, "confidence": confidence},
    )
    return key


def list_memories(store, user_id: str) -> list[dict]:
    """Recuerdos de un usuario, más recientes primero, con los campos de procedencia (vacíos si son viejos)."""
    items = [i for i in store.search(memory_namespace(user_id), limit=_SEARCH_WINDOW)
             if (getattr(i, "value", None) or {}).get("text")]
    items.sort(key=_created_at, reverse=True)
    return [{"key": i.key, "text": i.value["text"], "created_at": _created_at(i),
             "thread_id": i.value.get("thread_id"), "evidence": i.value.get("evidence") or "",
             "confidence": i.value.get("confidence") or "unverified",
             "previous_text": i.value.get("previous_text"), "updated_at": i.value.get("updated_at")} for i in items]


NO_RELEVANT_MSG = "No relevant memories for this query."
KEYWORD_MARK = "(keyword match, less reliable)"
NO_MEMORIES_MSG = "No memories saved for this user."
SAVED_MSG = "Memory saved."
UPDATED_MSG = "Memory updated."


def recall(store, user_id: str, query: str, min_score: float = 0.0) -> str:
    """Texto que devuelve search_memories: cada recuerdo con su id, o un aviso explícito si nada es relevante.
    Con búsqueda semántica, los que solo coinciden por palabras clave van marcados como menos confiables."""
    items = search_memory_items(store, user_id, query, min_score=min_score)
    if getattr(store, "index_config", None) and query.strip():
        seen = {key for key, _ in items}
        extra = [(k, t) for k, t in keyword_matches(store, user_id, query) if k not in seen]
        lines = [f"- [id {key}] {text}" for key, text in items]
        lines += [f"- [id {key}] {KEYWORD_MARK} {text}" for key, text in extra]
        if lines:
            return "\n".join(lines)
    elif items:
        return "\n".join(f"- [id {key}] {text}" for key, text in items)
    if query.strip() and store.search(memory_namespace(user_id), limit=1):
        return NO_RELEVANT_MSG  # hay recuerdos, pero ninguno pasa el umbral: no se devuelve el menos malo
    return NO_MEMORIES_MSG


def update_memory(store, user_id: str, key: str, text: str, *, thread_id: str | None = None,
                  evidence: str = "", confidence: str = "unverified") -> bool:
    """Reemplaza el texto de un recuerdo del propio usuario. Guarda el anterior en previous_text (para auditar y
    deshacer) y la fecha en updated_at; created_at se conserva. False si no existe en el namespace de ese usuario."""
    item = store.get(memory_namespace(user_id), key)
    if item is None or not (item.value or {}).get("text"):
        return False
    store.put(memory_namespace(user_id), key, {
        **item.value, "text": text, "previous_text": item.value["text"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "thread_id": thread_id, "evidence": evidence, "confidence": confidence,
    })
    return True


def delete_memory(store, user_id: str, key: str) -> bool:
    """Borra un recuerdo solo dentro del namespace de ese usuario. False si no existe (o es de otro)."""
    if store.get(memory_namespace(user_id), key) is None:
        return False
    store.delete(memory_namespace(user_id), key)
    return True


# --------------------------------------------------------------------------- procedencia y verificación

SUMMARY_SOURCE = "summarization"  # additional_kwargs["lc_source"] del mensaje de SummarizationMiddleware

VERIFY_MEMORY_PROMPT = """You check whether a memory about the user is backed by what the user actually said.

USER MESSAGES (only things the user wrote, oldest first):
{messages}

CANDIDATE MEMORY:
{candidate}

The memory is SUPPORTED only if the user explicitly stated it (or asked to remember it) in the messages above.
Assumptions, inferences, guesses and things the assistant said are NOT supported.
Reply with JSON only: {{"supported": true or false, "quote": "<the user's exact words that state it, copied verbatim, or empty>"}}"""


def user_texts(messages) -> list[str]:
    """Textos que escribió el usuario. Excluye el resumen de SummarizationMiddleware: es texto del modelo."""
    out = []
    for m in messages or []:
        if getattr(m, "type", None) != "human":
            continue
        if (getattr(m, "additional_kwargs", None) or {}).get("lc_source") == SUMMARY_SOURCE:
            continue
        text = m.text if isinstance(getattr(m, "text", None), str) else str(m.content)
        if text.strip():
            out.append(text)
    return out


def find_quote(quote: str, texts: list[str]) -> str:
    """Devuelve `quote` si aparece literal (sin importar mayúsculas, acentos ni espacios) en algún texto."""
    def norm(t: str) -> str:
        return " ".join(_normalize(t).split()).strip(" .,;:!?¡¿\"'")

    q = norm(quote or "")
    if len(q) < 3:
        return ""
    return quote.strip() if any(q in norm(t) for t in texts) else ""


def make_memory_verifier(llm):
    """Verificador de una llamada: (candidato, textos_usuario) -> (respaldado, cita)."""

    def verify(candidate: str, texts: list[str]) -> tuple[bool, str]:
        if not texts:
            return False, ""
        recent = "\n".join(f"- {t[:1500]}" for t in texts[-20:])
        try:
            raw = llm.invoke(VERIFY_MEMORY_PROMPT.format(messages=recent, candidate=candidate)).text
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        except Exception as exc:  # noqa: BLE001 - si no se puede verificar, no se guarda
            logger.warning("No pude verificar el recuerdo (%s)", exc)
            return False, ""
        return bool(data.get("supported")), str(data.get("quote") or "")

    return verify


def _provenance(text: str, quote: str, texts: list[str], verifier) -> tuple[str, str] | None:
    """(evidence, confidence) para un texto nuevo; None si el verificador dice que el usuario no lo dijo."""
    if verifier is not None:
        ok, verifier_quote = verifier(text, texts)
        if not ok:
            return None
        return find_quote(verifier_quote, texts) or find_quote(quote, texts), "verified"
    evidence = find_quote(quote, texts)
    return evidence, ("quoted" if evidence else "unverified")


def remember(store, user_id: str, text: str, quote: str, texts: list[str], *,
             thread_id: str | None = None, verifier=None) -> str:
    """Lógica común de save_memory (agente normal y bigtool). Devuelve el mensaje para el agente."""
    prov = _provenance(text, quote, texts, verifier)
    if prov is None:
        return ("Not saved: the user never stated this in the conversation. Do not save assumptions; "
                "tell the user it was not saved and ask them to confirm if needed.")
    save_memory(store, user_id, text, thread_id=thread_id, evidence=prov[0], confidence=prov[1])
    return SAVED_MSG


# Mismo mensaje si el id no existe o es de otro usuario: no revela qué ids existen.
NOT_FOUND_MSG = "Not updated: there is no memory with that id. Use search_memories to get the ids."


def revise(store, user_id: str, key: str, text: str, quote: str, texts: list[str], *,
           thread_id: str | None = None, verifier=None) -> str:
    """Lógica común de update_memory: solo recuerdos del propio user_id y con la misma verificación."""
    if store.get(memory_namespace(user_id), key) is None:
        return NOT_FOUND_MSG
    prov = _provenance(text, quote, texts, verifier)
    if prov is None:
        return ("Not updated: the user never stated the new value in the conversation. Do not update with "
                "assumptions; tell the user it was not updated.")
    if not update_memory(store, user_id, key, text, thread_id=thread_id, evidence=prov[0], confidence=prov[1]):
        return NOT_FOUND_MSG
    return UPDATED_MSG


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", _normalize(text)) if len(w) >= 3]


# Palabras que no aportan tema (español e inglés, sin acentos). Incluye genéricas de los recuerdos y preguntas
# ("usuario", "nombre", "llama", "favorito"...): con ellas "nombre de mi gato" encontraría "su perro se llama Rex"
# y "color favorito" encontraría "su bebida favorita".
_STOPWORDS = set("""
a al algo como con cual cuales cuando cuanto de del donde e el ella ellos en entre es esa ese eso esta este esto
fue ha hay la las le les lo los mas me mi mis muy no nos o para pero por que quien se sea ser si sin sobre son su
sus tambien te ti tu tus un una uno unos y ya yo era soy estoy esta estan tiene tengo tener hace hago dime dame
sabes saber recuerdas recuerda recuerdo recuerdos dato datos informacion usuario usuaria nombre nombres llama llamo
llamas llamado llamada favorito favorita favoritos favoritas preferido preferida prefiero prefiere prefieres
preferencia preferencias gusta gustan gusto fecha cosa cosas actual ahora
the and or of to in on at for with my me your his her their is are was what which who where when how about do does
user name named called favorite favourite prefer prefers like likes know remember
""".split())


# Sinónimos de los datos personales más consultados: "ciudad" no comparte palabras con "vive en Querétaro".
# Raíz (tras _stem) -> tema. Pocos y concretos, para no traer recuerdos de otro tema.
_TOPICS = {**dict.fromkeys(("viv", "vivo", "ciuda", "resid", "domic", "mud", "radic", "live", "lives", "city"), "~vivir"),
           **dict.fromkeys(("traba", "emple", "profe", "ofici", "puest", "work", "works", "job"), "~trabajo")}


def _stem(word: str) -> str:
    """Raíz aproximada para comparar variantes ("trabajo"/"trabaja", "vivo"/"vive", "ciudades"/"ciudad")."""
    if len(word) > 4:
        word = re.sub(r"(es|s)$", "", word)
    if len(word) > 3:
        word = re.sub(r"[aeiou]$", "", word)
    return _TOPICS.get(word[:5], word[:5])


def content_stems(text: str, query: bool = False) -> set[str]:
    """Palabras con contenido como raíces. En un recuerdo, las palabras con mayúscula (nombres propios) solo valen
    completas ("=tomas"), para que "qué tomo" no encuentre a "Tomás"; la consulta aporta raíz y palabra completa."""
    out = set()
    for raw in re.findall(r"\w+", text):
        w = _normalize(raw)
        if len(w) < 3 or w in _STOPWORDS or w.isdigit():
            continue
        if query:
            out |= {_stem(w), "=" + w}
        else:
            out.add("=" + w if raw[0].isupper() else _stem(w))
    return out


def keyword_matches(store, user_id: str, query: str, limit: int = 5) -> list[tuple[str, str]]:
    """Respaldo de la búsqueda semántica: recuerdos que comparten al menos una palabra con contenido (sin palabras
    vacías) con la consulta, más coincidencias primero. Sirve para consultas con varios temas ("dónde trabajo y
    vivo"), cuya similitud con cada recuerdo queda bajo el umbral."""
    wanted = content_stems(query, query=True)
    if not wanted:
        return []
    items = [i for i in store.search(memory_namespace(user_id), limit=_SEARCH_WINDOW)
             if (getattr(i, "value", None) or {}).get("text")]
    scored = [(len(wanted & content_stems(i.value["text"])), i) for i in items]
    scored = [(n, i) for n, i in scored if n > 0]
    scored.sort(key=lambda p: p[0], reverse=True)
    return [(i.key, i.value["text"]) for _, i in scored[:limit]]


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
    return [text for _, text in search_memory_items(store, user_id, query, limit)]


def search_memory_items(store, user_id: str, query: str = "", limit: int = 10,
                        min_score: float = 0.0) -> list[tuple[str, str]]:
    """Como search_memories, pero devuelve (key, texto): el agente necesita la key para actualizar.
    `min_score` filtra la búsqueda semántica: la búsqueda vectorial siempre devuelve "el menos malo"."""
    if query.strip() and getattr(store, "index_config", None):
        # Búsqueda semántica. Los recuerdos sin embedding (guardados antes de activarla) no aparecen aquí:
        # scripts/migrate_memories.py los indexa.
        items = store.search(memory_namespace(user_id), query=query, limit=limit)
        return [(i.key, i.value["text"]) for i in items
                if (i.value or {}).get("text") and (i.score is None or i.score >= min_score)]
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
    return [(i.key, i.value["text"]) for i in items[:limit]]


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
