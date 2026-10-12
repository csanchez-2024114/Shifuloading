"""
memory_updater — agente_v3

Last node before END. Persists a decision record only when the agent
completed a real workflow turn (requirement_level == "level_2") and
memory context was available.

Avoids noise: conversational turns, errors, and closing messages are NOT saved.
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.shifu_base_v1.graph.state import ShifuState
from app.agent.shared.helpers.identity_loader import get_agent_personality
from app.agent.shared.memory.conversation_compactor import DEFAULTS, chat_messages, compact
from app.agent.shared.memory.decision_memory import save_decision
from app.agent.shared.memory.episodic_memory_helper import parse_now
from app.agent.shared.memory.memory_learner import learn
from app.agent.shared.memory.message_index import index_message
from app.agent.shared.utils.log_utils import DEV_MODE, dev_print
from app.core.mongo import mongo_manager

logger = logging.getLogger(__name__)

_LINE = "─" * 63


async def memory_updater_node(state: ShifuState) -> dict:
    learned = await _learn(state)
    await _index(state)
    return {**await _log_decision(state), "memory_learned": learned, **await _compact(state)}


async def _compact(state: ShifuState) -> dict:
    """Compactacion: cuando hay mas de max_messages sin plegar, pliega en el resumen los que salen de la ventana y deja
    los ultimos keep_messages. Los numeros son dato (memory_policy.compaction). Nunca rompe el turno."""
    try:
        if state.get("system_event"):
            return {}
        policy = {**DEFAULTS, **(((await get_agent_personality()).get("memory_policy") or {}).get("compaction") or {})}
        msgs = chat_messages(state.get("messages") or [])
        upto = int(state.get("summary_upto") or 0)
        keep = max(int(policy["keep_messages"]), 0)
        if policy["enabled"] is False or len(msgs) - upto <= int(policy["max_messages"]) or len(msgs) - keep <= upto:
            return {}
        previous = state.get("conversation_summary") or ""
        summary = await compact(previous, msgs[upto:len(msgs) - keep], policy["model"])
        # Si el resumen no cambio, el compactor fallo: no se avanza, o esos mensajes saldrian del contexto sin quedar resumidos.
        if not summary or summary == previous:
            return {}
        return {"conversation_summary": summary, "summary_upto": len(msgs) - keep}
    except Exception as exc:
        logger.warning("[memory_updater] no se pudo compactar la conversacion: %s", exc)
        return {}


async def _index(state: ShifuState) -> bool:
    """Guarda el mensaje literal del usuario para recordarlo por significado en otras conversaciones. Los avisos de la
    interfaz (system_event, incluye los turnos silent) no los escribio el usuario; lo trivial y lo que parece credencial
    lo descarta index_message. Nunca rompe el turno."""
    try:
        policy = (await get_agent_personality()).get("memory_policy") or {}
        recall = policy.get("recall") or {}
        text = next((m.content for m in reversed(state.get("messages") or []) if isinstance(m, HumanMessage)), "")
        if (policy.get("enabled") is False or recall.get("enabled") is False or recall.get("index_messages") is False
                or state.get("system_event") or not state.get("user_id") or not isinstance(text, str)):
            return False
        return await index_message(mongo_manager.db, user_id=state["user_id"],
                                   conversation_id=state.get("conversation_id") or "", text=text)
    except Exception as exc:
        logger.warning("[memory_updater] no se pudo indexar el mensaje: %s", exc)
        return False


async def _learn(state: ShifuState) -> dict | None:
    """Mini agente que guarda hechos del usuario y en que va la conversacion. Corre dentro del grafo (queda en la traza
    y en el costo del turno); suma ~1 s antes del evento done, cuando el texto ya se mostro."""
    policy = (await get_agent_personality()).get("memory_policy") or {}
    messages = state.get("messages") or []
    user_text = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    reply = next((m.content for m in reversed(messages) if isinstance(m, AIMessage)), "")
    if policy.get("enabled") is False or state.get("system_event") or not state.get("user_id") or not user_text:
        return None
    return await learn(
        mongo_manager.db, user_id=state["user_id"], conversation_id=state.get("conversation_id") or "",
        user_text=str(user_text), reply=str(reply), policy=policy,
        allow_activity=(state.get("semantic_intake_debug") or {}).get("detected_intent") != "chat",
        now=parse_now(state.get("current_time_utc")),  # "hoy" del turno (puede ser simulado en desarrollo)
    )


async def _log_decision(state: ShifuState) -> dict:
    req_level     = state.get("requirement_level")
    ranked_context = state.get("ranked_context")
    user_id       = state.get("user_id")

    should_save = req_level == "level_2" and bool(ranked_context) and bool(user_id)

    if not should_save:
        if DEV_MODE:
            dev_print(
                f"\n┌─ Memory · Updater {_LINE[19:]}\n"
                f"│ condition: level_2={req_level == 'level_2'}  context={bool(ranked_context)}\n"
                f"│ action   : SKIP — condición no cumplida\n"
                f"│ goal_id  : {state.get('goal_id') or '—'}\n"
                f"└{_LINE}"
            )
        return {"decision_logged": False}

    # Extract last AI response as decision text
    last_ai = next(
        (m.content for m in reversed(state.get("messages") or [])
         if isinstance(m, AIMessage)),
        "",
    )

    db            = mongo_manager.db
    conversation_id = state.get("conversation_id") or ""
    goal_id       = state.get("goal_id")
    apps          = state.get("apps_involved") or []

    decision_id = await save_decision(
        db=db,
        user_id=user_id,
        conversation_id=conversation_id,
        goal_id=goal_id,
        context=f"Turno completado — apps: {', '.join(apps) or 'none'}",
        decision=last_ai[:150],
        alternatives=[],
        reason="Turno de workflow nivel-2 completado por el agente",
    )

    if DEV_MODE:
        action = f"SAVED decision_id={decision_id}" if decision_id else "SAVE FAILED"
        dev_print(
            f"\n┌─ Memory · Updater {_LINE[19:]}\n"
            f"│ condition: level_2=True  context=True\n"
            f"│ action   : {action}\n"
            f"│ goal_id  : {goal_id or '—'}\n"
            f"└{_LINE}"
        )

    logger.info(
        "[memory_updater] user=%s  goal=%s  decision_id=%s",
        user_id, goal_id, decision_id,
    )

    return {"decision_logged": bool(decision_id)}

