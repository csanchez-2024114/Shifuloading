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


# sujeto genérico al inicio de un recuerdo: "El usuario vive en…" -> "Vive en…". Con sujeto, la búsqueda por palabras
# casaba por "usuario" y perdía "La usuaria trabaja…" (prueba real). Solo recuerdos nuevos: los guardados no se tocan.
_SUBJECT = re.compile(r"^\s*(?:(?:el|la)\s+usuari[oa](?:/[oa])?|al\s+usuario|a\s+la\s+usuaria|the\s+user)\s+", re.I)


def neutral_fact(text: str) -> str:
    """"El usuario vive en X" -> "Vive en X"; "Al usuario le gusta X" -> "Le gusta X". Lo demás, igual."""
    rest = _SUBJECT.sub("", text, count=1)
    if rest == text or not rest.strip():
        return text
    return rest[0].upper() + rest[1:]


def save_memory(store, user_id: str, text: str, *, thread_id: str | None = None,
                evidence: str = "", confidence: str = "unverified") -> str:
    """Guarda un recuerdo con su procedencia y devuelve su key (uuid hex).
    confidence: "verified" (lo confirmó el verificador), "quoted" (la cita aparece literal en lo que dijo
    el usuario) o "unverified" (sin evidencia). Los recuerdos viejos solo tienen text y created_at."""
    key = uuid.uuid4().hex
    text = neutral_fact(text)
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
RECENT_FALLBACK = 5  # sin coincidencias por palabras: los más recientes, como mucho estos
NO_MATCH_HEADER = "No memory shares words with this query; these are the most recent memories (check if one answers it):"
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
        lines = [f"- [id {key}] {text}" for key, text in items]
        if query.strip() and not _keyword_search(store, user_id, query, 1)[1]:
            lines.insert(0, NO_MATCH_HEADER)
        return "\n".join(lines)
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


# Política de guardado en la memoria global (MEMORY_SAVE_POLICY). Va al final del prompt del sistema. Ningún recuerdo
# se inyecta en el prompt: el modelo solo los consulta con search_memories, así cada conversación sigue independiente.
MEMORY_POLICIES = {
    "strict": """## Saving to long-term memory
- Long-term memory is shared by all of this user's conversations, so it holds only a few precise facts. Call save_memory ONLY when:
  (a) the user explicitly asks you to remember something ("remember that…");
  (b) the user states a durable personal fact that will clearly be useful in other conversations: where they live, their job, their pets or family, a stable preference or a lasting technical constraint (e.g. "only Python 3.12");
  (c) the user wants a specific dated event remembered (a birthday, an appointment).
- Never save conversation content: what you explained, tasks, calculations and their results, tool or search results, the topics discussed, or details of the current request (file names, amounts, the dates or budget of a one-off plan, what they are working on today). The conversation itself keeps that.
- Only save what the user explicitly said about themselves, written in the user's language, and pass in evidence the user's exact words copied verbatim. Never save your own assumptions or inferences.
- Save at most {max_per_turn} memories per message.""",
    "broad": """## Saving to long-term memory
- When the user shares stable personal facts (name, likes, preferences, lasting decisions, job and role), save them with save_memory, written in the user's language, and pass in evidence the user's exact words copied verbatim.
- Also save the user's durable technical constraints when they state them explicitly: language or library versions (e.g. "only Python 3.12"), libraries they cannot use or install, their operating system or runtime environment. Pass their exact words as evidence.
- Stable facts the user mentions while asking for something else (where they live, their diet, what they like, their job) are still facts about them: save them.
- Do not save passing details of a single task: file names, row counts, data values, error messages, amounts, the dates or budget of a one-off plan, or what the user is working on today ("today I'm working on file X" is not a fact about the user).
- Only save what the user explicitly said about themselves. Never save your own assumptions, inferences or things you said.""",
}


# MEMORY_SEARCH_ECONOMY: prueba A/B anterior, la configuración B llamó a search_memories en 6 preguntas seguidas
# cuyas respuestas ya estaban en la conversación (~55k tokens extra).
SEARCH_ECONOMY_RULE = """## Looking up memories
- If the answer is already in the visible conversation or in its summary, answer directly; call search_memories only when the information is not available in this conversation. This takes precedence over checking memories at the start of a conversation."""


def memory_policy(name: str = "strict", max_per_turn: int = 3, search_economy: bool = False) -> str:
    text = MEMORY_POLICIES.get(name, MEMORY_POLICIES["strict"])
    if not max_per_turn:
        text = text.replace("\n- Save at most {max_per_turn} memories per message.", "")
    text = text.replace("{max_per_turn}", str(max_per_turn))
    return f"{text}\n\n{SEARCH_ECONOMY_RULE}" if search_economy else text


TURN_LIMIT_MSG = ("Not run: the limit of {limit} memories per message was reached, so this was not saved. Tell the "
                  "user which fact was not saved; they can ask again in another message.")


def turn_saves(messages, call_id: str | None = None) -> int:
    """Guardados previos en el mensaje en curso. Con `call_id` (agente normal): posición de esta llamada entre las
    save_memory del turno (incluye las paralelas del mismo paso). Sin él (bigtool): resultados ya guardados del turno."""
    messages = list(messages or [])
    start = max((i for i, m in enumerate(messages) if getattr(m, "type", None) == "human"
                 and (getattr(m, "additional_kwargs", None) or {}).get("lc_source") != SUMMARY_SOURCE), default=-1)
    turn = messages[start + 1:]
    if call_id:
        calls = [c.get("id") for m in turn for c in (getattr(m, "tool_calls", None) or [])
                 if c.get("name") in ("save_memory", "guardar_recuerdo")]
        return calls.index(call_id) if call_id in calls else len(calls)
    return sum(1 for m in turn if getattr(m, "type", None) == "tool"
               and getattr(m, "name", None) in ("save_memory", "guardar_recuerdo"))


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


DUPLICATE_MSG = ("Not run: an equivalent memory already exists (id: {key}): \"{text}\". Do not save it again. If "
                 "the fact changed, call update_memory with that id and the new value.")
DEDUP_MIN_STEMS = 2         # un recuerdo con menos palabras con contenido no se compara por palabras
DEDUP_CONTAINMENT = 0.8     # parte de las raíces del más corto que deben estar en el otro


def _fact_stems(text: str) -> set[str]:
    # modo consulta en los dos lados: así "toma té verde" y "Toma té verde; dejó el café" comparten la raíz de
    # "toma" aunque una vaya en mayúscula (en modo recuerdo, la mayúscula solo vale como palabra completa)
    return {s for s in content_stems(neutral_fact(text), query=True) if not s.startswith("=")}


def find_duplicate(store, user_id: str, text: str, min_score: float = 0.85) -> tuple[str, str] | None:
    """(key, texto) de un recuerdo del usuario con la misma información que `text`, o None. Por palabras: las raíces
    del más corto están casi todas en el otro. Con búsqueda semántica, también por puntuación (≥ `min_score`)."""
    new = _fact_stems(text)
    items = [i for i in store.search(memory_namespace(user_id), limit=_SEARCH_WINDOW)
             if (getattr(i, "value", None) or {}).get("text")]
    for i in items:
        old = _fact_stems(i.value["text"])
        small = min(new, old, key=len)
        if len(small) >= DEDUP_MIN_STEMS and len(new & old) / len(small) >= DEDUP_CONTAINMENT:
            return i.key, i.value["text"]
    if getattr(store, "index_config", None) and text.strip():
        for i in store.search(memory_namespace(user_id), query=text, limit=3):
            if (i.value or {}).get("text") and i.score is not None and i.score >= min_score:
                return i.key, i.value["text"]
    return None


def remember(store, user_id: str, text: str, quote: str, texts: list[str], *,
             thread_id: str | None = None, verifier=None, saved_this_turn: int = 0, max_per_turn: int = 0,
             dedup: bool = False, dedup_score: float = 0.85) -> str:
    """Lógica común de save_memory (agente normal y bigtool). Devuelve el mensaje para el agente.
    `max_per_turn` (MEMORY_MAX_PER_TURN): tope de recuerdos por mensaje; 0 = sin tope.
    `dedup` (MEMORY_DEDUP): no guarda un dato equivalente a uno existente; sugiere update_memory con su id."""
    if max_per_turn and saved_this_turn >= max_per_turn:
        return TURN_LIMIT_MSG.format(limit=max_per_turn)
    if dedup and (dup := find_duplicate(store, user_id, text, dedup_score)):
        return DUPLICATE_MSG.format(key=dup[0], text=dup[1])
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
           **dict.fromkeys(("traba", "emple", "profe", "ofici", "puest", "work", "works", "job"), "~trabajo"),
           # parche del modo por palabras: "qué me gusta comer" no comparte raíz con "comida favorita"
           **dict.fromkeys(("comer", "comid", "alime", "food", "eat", "eats"), "~comida")}


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
    for m in re.finditer(r"\w+", text):
        raw, w = m.group(0), _normalize(m.group(0))
        if len(w) < 3 or w in _STOPWORDS or w.isdigit():
            continue
        if query:
            out |= {_stem(w), "=" + w}
        elif not raw[0].isupper():
            out.add(_stem(w))
        else:
            out.add("=" + w)
            # la primera palabra de una frase va en mayúscula sin ser nombre propio ("Vive en…", "Trabaja como…"):
            # también cuenta por raíz, salvo raíces cortas y ambiguas ("Tomás" -> "tom" no debe casar con "tomo")
            starts = not text[:m.start()].strip() or text[:m.start()].rstrip()[-1] in ".!?:;\n"
            if starts and len(stem := _stem(w)) >= 4:
                out.add(stem)
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
    return _keyword_search(store, user_id, query, limit)[0]


def _keyword_search(store, user_id: str, query: str, limit: int = 10) -> tuple[list[tuple[str, str]], bool]:
    """Búsqueda por palabras (MEMORY_SEMANTIC=0): mismo puntaje que keyword_matches (sin palabras genéricas como
    "usuario", por raíces: "trabajo"/"trabaja"). Si nada coincide, los más recientes (máximo
    RECENT_FALLBACK): mejor que un falso "no sé". Devuelve (recuerdos, coincidió)."""
    items = [i for i in store.search(memory_namespace(user_id), limit=_SEARCH_WINDOW)
             if (getattr(i, "value", None) or {}).get("text")]
    items.sort(key=_created_at, reverse=True)  # más recientes primero: desempate estable
    wanted = content_stems(query, query=True) if query.strip() else set()
    if not wanted:
        return [(i.key, i.value["text"]) for i in items[:limit]], not query.strip()
    scored = [(len(wanted & content_stems(i.value["text"])), i) for i in items]
    scored = [(n, i) for n, i in scored if n > 0]
    if not scored:
        return [(i.key, i.value["text"]) for i in items[:min(limit, RECENT_FALLBACK)]], False
    scored.sort(key=lambda p: p[0], reverse=True)
    return [(i.key, i.value["text"]) for _, i in scored[:limit]], True


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
