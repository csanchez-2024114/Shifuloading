"""
identity_loader — agente_v3

Loads agent_identity and agent_personality from MongoDB and builds the
dynamic system prompt for the chat node.

In-memory cache: TTL 10 minutes. Identity/personality changes in MongoDB
propagate automatically without restarting the server.

MongoDB collections (filtered by agent_id):
  agent_identity   — who Shifu is: self_identity, principles, restrictions
  agent_personality — how Shifu talks: tone, greeting, closing, auth_policy

System prompt ordering (for LLM provider prompt-cache efficiency):
  1. Static block   — self_identity + principles + restrictions + style
                      (never changes → provider caches it across turns)
  2. Greeting rule  — first_message (turn 1) or repeated_greeting (turn 2+)
  3. Auth policy    — injected only during level_1 validation, removed after
  4. Error context  — aggregator validation errors (level_1 only)
  5. Research       — tavily results (when available)

Closing behavior (deterministic — no LLM tokens):
  get_closing_signals() returns the list of phrases from closing_behavior.signals.
  semantic_intake checks these via Python str-in before the LLM call.
"""

import asyncio
import logging
import os

from cachetools import TTLCache
from langchain_core.messages import SystemMessage

from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)

_AGENT_ID = os.getenv("SHIFU_AGENT_ID", "shifu_v1")
_cache: TTLCache = TTLCache(maxsize=10, ttl=600)  # 10-min TTL — no restart needed to update identity
_lock = asyncio.Lock()


async def _load(collection: str) -> dict:
    """Load a single document from collection, cached for the process lifetime."""
    async with _lock:
        if collection in _cache:
            return _cache[collection]
        db = mongo_manager.db
        if db is None:
            logger.warning("[identity_loader] DB unavailable — %s not loaded", collection)
            _cache[collection] = {}
            return {}
        doc = await db[collection].find_one({"agent_id": _AGENT_ID})
        if doc:
            doc.pop("_id", None)
            _cache[collection] = doc
            logger.info("[identity_loader] cached %s (agent_id=%s)", collection, _AGENT_ID)
        else:
            logger.warning("[identity_loader] no doc in %s for agent_id=%s", collection, _AGENT_ID)
            _cache[collection] = {}
        return _cache[collection]


async def get_agent_identity() -> dict:
    return await _load("agent_identity")


async def get_agent_personality() -> dict:
    return await _load("agent_personality")


# ── Closing signals ────────────────────────────────────────────────────────────

def get_closing_signals(personality: dict) -> list[str]:
    """Return lowercase closing phrases from closing_behavior.signals."""
    closing = personality.get("closing_behavior") or {}
    return [s.lower().strip() for s in (closing.get("signals") or []) if s]


# ── System prompt builder ──────────────────────────────────────────────────────

def render_voice(personality: dict) -> str:
    """Voz y personalidad: cualquier clave que el admin ponga en personality.voice se muestra tal cual
    (texto -> parrafo, lista -> vinetas). Agregar o quitar rasgos no requiere tocar codigo.
    Lo usan el responder (para hablar) y el evaluador (para juzgar), asi ambos leen la misma fuente."""
    blocks = [
        f"### {k.replace('_', ' ').title()}\n"
        + ("\n".join(f"- {i}" for i in v) if isinstance(v, list) else str(v))
        for k, v in (personality.get("voice") or {}).items() if v
    ]
    return "## Voice & Personality\n" + "\n\n".join(blocks) if blocks else ""


def _build_static_block(identity: dict, personality: dict) -> str:
    """
    Static content — identical every turn for the same agent.
    Must come FIRST in the message list so the LLM provider can cache it.
    Contains: self_identity → principles → restrictions → communication style.
    """
    parts: list[str] = []

    self_identity = (identity.get("self_identity") or "").strip()
    if self_identity:
        parts.append(self_identity)

    purpose = (identity.get("purpose") or "").strip()
    mission = (identity.get("mission") or "").strip()
    vision  = (identity.get("vision") or "").strip()
    if purpose or mission or vision:
        lines = []
        if purpose:
            lines.append(f"- Purpose: {purpose}")
        if mission:
            lines.append(f"- Mission: {mission}")
        if vision:
            lines.append(f"- Vision: {vision}")
        parts.append("## Purpose, Mission & Vision\n" + "\n".join(lines))

    principles = identity.get("principles") or []
    if principles:
        bullets = "\n".join(f"- {p}" for p in principles)
        parts.append(f"## Principles\n{bullets}")

    restrictions = identity.get("restrictions") or []
    if restrictions:
        bullets = "\n".join(f"- {r}" for r in restrictions)
        parts.append(f"## Hard Restrictions\n{bullets}")

    comm              = personality.get("communication_style") or {}
    base_tone         = personality.get("base_tone") or "casual_professional"
    default_formality = personality.get("default_formality") or "semiformal"
    use_emojis        = comm.get("use_emojis", False)
    prefer_lists      = comm.get("prefer_lists", False)
    response_length   = comm.get("response_length") or "adaptive"
    max_questions     = comm.get("questions_per_turn", 1)

    style_lines = [
        f"- Tone: {base_tone}  |  Formality: {default_formality}",
        (
            "- Emojis: allowed when they enhance clarity or warmth"
            if use_emojis else
            "- Do not use emojis under any circumstances. Keep the text clean of icons or graphical symbols."
        ),
        (
            "- Always format lists, sequences, and multiple options using clean Markdown bullet lists (`- item`). Avoid dense blocks of text."
            if prefer_lists else
            "- Always answer using continuous, well-structured Markdown paragraphs. Do not use bullet points or lists unless the user explicitly requests a list layout."
        ),
        f"- Response length: {response_length}",
        f"- Ask at most {max_questions} question per turn",
    ]
    # prompt_mode "brief": sin reglas de estilo por defecto escritas en el codigo; solo las que el documento defina
    if not (personality.get("prompt_mode") == "brief" and not personality.get("communication_style")):
        parts.append("## Communication Style\n" + "\n".join(style_lines))

    parts.append(render_voice(personality))

    return "\n\n".join(filter(None, parts))


def build_system_messages(
    identity: dict,
    personality: dict,
    *,
    is_first_turn: bool,
    requirement_level: str | None,
    is_closing: bool,
    error_context: str | None = None,
    retrieved_research: str | None = None,
    user_preferences_context: str | None = None,  # Capa 3 — staleness-annotated prefs
    user_name: str | None = None,
    is_greeting: bool = True,  # True por defecto: quien no lo pase conserva el comportamiento anterior
    user_memory: str | None = None,  # hechos del usuario + en que iba (memory_retriever.format_user_memory)
) -> list[SystemMessage]:
    """
    Return the ordered SystemMessage list to prepend before conversation history.

    Closing shortcut: returns a single minimal farewell instruction — all
    planning/identity context is stripped to save tokens and reduce latency.
    """
    if is_closing:
        name = identity.get("name") or "Hyper Shifu"
        return [SystemMessage(content=(
            f"You are {name}. "
            "The user has indicated they want to end the conversation. "
            "Respond warmly in 1-2 sentences. "
            "Do not bring up pending tasks or list capabilities."
        ))]

    msgs: list[SystemMessage] = []

    # ── 1. Static block (cached by LLM provider across turns) ────────────────
    static = _build_static_block(identity, personality)
    if static:
        msgs.append(SystemMessage(content=static))

    # ── 1.5. User identity — grounds the LLM so it never confuses the user's
    # name with the agent's own name (e.g. answering "your name is Hyper Shifu").
    if user_name:
        msgs.append(SystemMessage(content=(
            f"## User\nThe user's name is {user_name}. Address them by this name "
            "when it feels natural. Never confuse it with your own identity."
        )))
    else:
        msgs.append(SystemMessage(content=(
            "## User\nThere is no name on file for this user. If asked, say you "
            "don't have their name yet and ask what to call them — never guess "
            "or reuse your own name as theirs."
        )))
    if user_memory:
        usage = (personality.get("memory_policy") or {}).get("usage") or (
            "Use it naturally when it helps; do not recite it. If asked what you know about them, say it and "
            "mention they can delete it. Never claim to remember anything not listed here."
        )
        msgs.append(SystemMessage(content=f"## What you remember about the user\n{user_memory}\n\n{usage}"))

    # ── 2. Greeting rule (short — changes only on turn 1 vs. subsequent) ─────
    # Solo si el mensaje ES un saludo: antes se aplicaba a todo primer turno, y "Respond warmly in 1-2 sentences.
    # Do not list capabilities" ahogaba cualquier peticion real que abriera la conversacion.
    greeting = personality.get("greeting_behavior") or {}
    rule = (greeting.get("first_message") if is_first_turn else greeting.get("repeated_greeting")) if is_greeting else None
    if rule:
        # La regla de saludo dice "si la lista X trae algo...". Cuando la lista no existe (usuario nuevo) el modelo la
        # inventaba: "tienes notificaciones sin ver", "un compromiso que vence hoy" (4 de 8 primeros turnos, 2026-10-11).
        # El codigo dice cuales NO existen; el texto de las secciones es el de memory_retriever.format_user_memory.
        # Solo cuando no existe NINGUNA: si se niega una parte ("no hay avisos ni compromisos") el modelo tambien callaba
        # la conversacion anterior que si estaba en la lista (memoria_entre_conversaciones bajo de 3/3 a 1/3, aun
        # diciendole cuales si existian).
        titles = ("Notices the user has NOT seen yet", "Commitments with a date:", "Earlier conversations, oldest first:")
        fact = "" if any(t in (user_memory or "") for t in titles) else (
            "\nFACT (checked by the system): for this user there are NO unseen notices, NO commitments with a date and "
            "NO earlier conversations. Do not mention, imply or ask about any of them.")
        msgs.append(SystemMessage(content=f"## This Turn\n{rule}{fact}"))

    # ── 3. Authentication policy — only while level_1 errors exist ────────────
    if requirement_level == "level_1":
        auth = personality.get("authentication_policy")
        if auth:
            if isinstance(auth, dict):
                policy_text = "\n".join(f"- {v}" for v in auth.values() if v)
            else:
                policy_text = str(auth)
            msgs.append(SystemMessage(content=f"## OAuth / Authentication Policy\n{policy_text}"))

    # ── 4. Validation error context (level_1) ─────────────────────────────────
    if requirement_level == "level_1" and error_context:
        msgs.append(SystemMessage(content=error_context))

    # ── 5. External research (when tavily found results) ──────────────────────
    if retrieved_research:
        msgs.append(SystemMessage(content=f"## Relevant External Research\n{retrieved_research}"))

    # ── 5.5. User preferences (Capa 3 — staleness-annotated) ─────────────────
    if user_preferences_context:
        msgs.append(SystemMessage(content=user_preferences_context))

    return msgs
