"""
memory_retriever — agente_v3

Second node in the graph. Runs after goal_resolver.

Fetches all 5 memory types concurrently, then scores and ranks them
into a single ranked_context string ready for the responder prompt.
"""

import asyncio
import logging

from langchain_core.messages import HumanMessage

from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.memory.episodic_memory_helper import (
    COMMITMENTS_DEFAULTS, load_commitments, parse_now, search_older, search_older_messages,
)
from app.agent.shared.memory.memory_embedder import embed_text
from app.agent.shared.memory.message_index import is_trivial
from app.agent.shared.memory.memory_engine import retrieve_memories
from app.agent.shared.helpers.context_ranker import rank_memories
from app.agent.shared.helpers.identity_loader import get_agent_personality
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print
from app.core.mongo import mongo_manager
from app.services.notification_service import take_untold

logger = logging.getLogger(__name__)

_LINE = "─" * 63


async def memory_retriever_node(state: ShifuState) -> dict:
    user_id = state.get("user_id")
    if not user_id:
        return {"raw_memories": None, "ranked_context": None}

    goal_id = state.get("goal_id")
    db      = mongo_manager.db

    # Extract intent before retrieve_memories — used for semantic decision search
    intent = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, HumanMessage)),
        "",
    )
    apps_involved = state.get("apps_involved") or []

    # ponytail: memory depth is NOT plan-gated — restored to the original,
    # pre-billing call (relies on retrieve_memories' own default of 10).
    # Revisit if/when memory cost needs tiering again.
    # Cuantas conversaciones anteriores ve el agente (dato). Con 3, la tarea de la 1.a de 6 sesiones ya no existia (base_v032).
    policy = (await get_agent_personality()).get("memory_policy") or {}
    memories = await retrieve_memories(user_id, goal_id, db, intent=intent, conversation_id=state.get("conversation_id"),
                                       recent_conversations=int(policy.get("recent_conversations") or 3))
    # Hechos y diario van aparte (bloque "## User"): son cortos y siempre aplican; en el ranker el corte >0.5 los tiraba.
    ranked = rank_memories({**memories, "semantic": [], "episodic": []}, intent, apps_involved)
    recall = await _recall(db, user_id, intent, state.get("conversation_id"), memories, policy)
    memories["recalled"], memories["recalled_messages"] = recall["diary"], recall["messages"]
    memories["commitments"] = await _commitments(db, user_id, state, policy)
    memories["notices"] = await _notices(db, user_id, state, policy)
    user_memory = format_user_memory(memories)

    if DEV_MODE:
        dev_print(
            f"\n┌─ Memory · Retriever {_LINE[20:]}\n"
            f"│ goal_id   : {goal_id or '—'}\n"
            f"│ goals     : {len(memories['goals'])}\n"
            f"│ semantic  : {len(memories['semantic'])}\n"
            f"│ episodic  : {len(memories['episodic'])}\n"
            f"│ recalled  : {len(memories['recalled'])} diary, {len(memories['recalled_messages'])} messages\n"
            f"│ decisions : {len(memories['decisions'])}\n"
            f"│ structured: {len(memories['structured'])} keys\n"
            f"└{_LINE}"
        )
        if ranked:
            preview = ranked[:200].replace("\n", "\n│   ")
            dev_print(
                f"\n┌─ Memory · Context Ranker {_LINE[25:]}\n"
                f"│ intent  : {intent[:60]}\n"
                f"│ apps    : {apps_involved}\n"
                f"│ ranked  :\n│   {preview}\n"
                f"└{_LINE}"
            )

    logger.info(
        "[memory_retriever] user=%s  goal=%s  ranked_len=%d",
        user_id, goal_id, len(ranked),
    )

    return {
        "raw_memories":        memories,
        "ranked_context":      ranked or None,
        "user_memory_context": user_memory or None,
    }


# Politica por defecto del recuerdo por significado; el dato real es agent_personality.memory_policy.recall.
# Los min_score son hipotesis calibradas con text-embedding-3-small (relevante ~0.45-0.65, ajeno ~0.24-0.37).
# index_messages: si se guardan los mensajes originales del usuario (lo lee memory_updater).
_RECALL_DEFAULTS = {"enabled": True, "top_k": 2, "min_score": 0.40, "messages_top_k": 3, "messages_min_score": 0.45,
                    "index_messages": True}
_EMPTY_RECALL = {"diary": [], "messages": []}
_is_trivial = is_trivial  # alias: el filtro vive en message_index (lo comparte memory_updater)


async def _recall(db, user_id: str, text: str, conversation_id: str | None, memories: dict, policy: dict) -> dict:
    """Recuerda por significado con UN embedding de la consulta: {"diary": resumenes viejos, "messages": mensajes originales
    viejos}. Cualquier falla se registra y se ignora: nunca rompe el turno."""
    try:
        cfg = {**_RECALL_DEFAULTS, **(policy.get("recall") or {})}
        if not cfg["enabled"] or db is None or _is_trivial(text):
            return dict(_EMPTY_RECALL)
        embedding = await embed_text(text)
        if not embedding:
            return dict(_EMPTY_RECALL)
        # Diario: las recientes ya van por recencia y la actual ya esta en el historial.
        seen = {c for c in [conversation_id, *(e.get("conversation_id") for e in memories.get("episodic") or [])] if c}
        # Mensajes: solo se excluye la actual; el diario de las recientes es un resumen y pierde los nombres propios.
        diary, messages = await asyncio.gather(
            search_older(db, user_id, embedding, seen, int(cfg["top_k"]), float(cfg["min_score"])),
            search_older_messages(db, user_id, embedding, {conversation_id} - {None},
                                  int(cfg["messages_top_k"]), float(cfg["messages_min_score"])),
            return_exceptions=True,  # que una busqueda falle no tira la otra
        )
        for r in (diary, messages):
            if isinstance(r, Exception):
                logger.warning("[memory_retriever] recall search failed: %s", r)
        return {"diary": [] if isinstance(diary, Exception) else diary,
                "messages": [] if isinstance(messages, Exception) else messages}
    except Exception as exc:
        logger.warning("[memory_retriever] recall failed: %s", exc)
        return dict(_EMPTY_RECALL)


async def _commitments(db, user_id: str, state: dict, policy: dict) -> list[dict]:
    """Compromisos con fecha vencidos o por vencer (memory_policy.commitments). 'Hoy' sale del reloj del turno."""
    cfg = {**COMMITMENTS_DEFAULTS, **(policy.get("commitments") or {})}
    if not cfg["enabled"]:
        return []
    return await load_commitments(db, user_id, parse_now(state.get("current_time_utc")), int(cfg["horizon_days"]),
                                  state.get("conversation_id"))


NOTICES_DEFAULTS = {"enabled": True, "max": 3, "types": ["run_failed", "trigger_disabled"]}


async def _notices(db, user_id: str, state: dict, policy: dict) -> list[dict]:
    """Avisos que el usuario no ha visto (memory_policy.notices), solo en el PRIMER mensaje de la conversacion: es cuando
    el agente saluda y puede contarlos. Se marcan como dichos para no repetirlos en la siguiente conversacion."""
    cfg = {**NOTICES_DEFAULTS, **(policy.get("notices") or {})}
    humans = sum(1 for m in state.get("messages") or [] if isinstance(m, HumanMessage))
    if not cfg["enabled"] or humans != 1:
        return []
    return await take_untold(db, user_id, list(cfg["types"]), int(cfg["max"]))


def _due_label(days_left: int) -> str:
    if days_left == 0:
        return "today"
    n = abs(days_left)
    return f"{'in' if days_left > 0 else 'overdue'} {n} day{'s' if n != 1 else ''}"


def format_user_memory(memories: dict) -> str:
    def _date(f):
        d = f.get("last_seen_at")
        return f" (as of {d:%Y-%m-%d})" if hasattr(d, "strftime") else ""
    facts = "; ".join(f"{f.get('key')}: {f.get('value')}{_date(f)}" for f in memories.get("semantic") or [] if f.get("key"))
    # Del mas viejo al mas nuevo y numeradas: con solo la fecha (todas el mismo dia) no se podia responder "que pedi primero".
    episodes = [e for e in reversed(memories.get("episodic") or []) if e.get("activities")]
    work = [
        f"{i}. {e.get('date', '')}{' (oldest)' if i == 1 and len(episodes) > 1 else ''}: {', '.join(map(str, e['activities']))}"
        + (f" (pending: {e['pending']})" if e.get("pending") else "")
        for i, e in enumerate(episodes, 1)
    ]
    recalled = [
        f"- {r.get('date', '')}: {', '.join(map(str, r['activities']))}" + (f" (pending: {r['pending']})" if r.get("pending") else "")
        for r in memories.get("recalled") or [] if r.get("activities")
    ]
    # Texto literal del usuario (recortado): lo que el diario resumido pierde, como el nombre exacto de una hoja.
    said = [
        f'- {m.get("date", "")}: "{str(m["text"])[:300]}"' for m in memories.get("recalled_messages") or [] if m.get("text")
    ]
    # El compromiso primero y el paso despues: con el paso primero ("conectar Gmail (...)") el saludo preguntaba por el
    # paso y no por la entrega (fecha_v054e).
    due = [
        f"- {', '.join(map(str, c['activities'])) if c.get('activities') else c['pending']}"
        f" — due {c.get('due_date')} ({_due_label(c['days_left'])}); next step was: {c['pending']}"
        for c in memories.get("commitments") or [] if c.get("pending") and c.get("days_left") is not None
    ]
    notices = [
        f"- {n.get('date') or ''}: {n.get('message')}".replace("- : ", "- ") for n in memories.get("notices") or [] if n.get("message")
    ]
    parts = ([f"Facts the user told you: {facts}"] if facts else []) + (
        ["Notices the user has NOT seen yet (things that happened while they were away; tell them once, briefly, at the start of your reply):", *notices]
        if notices else []
    ) + (
        ["Commitments with a date:", *due] if due else []
    ) + (
        ["Earlier conversations, oldest first:", *work] if work else []
    ) + (
        ["Older conversations that may be related (found by meaning; use only if relevant):", *recalled] if recalled else []
    ) + (
        ["What the user said in older conversations (found by meaning; use only if relevant):", *said] if said else []
    )
    return "\n".join(parts)

