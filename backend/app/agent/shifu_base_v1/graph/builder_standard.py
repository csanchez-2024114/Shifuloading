"""
agente_v3 — Text-to-Workflow pipeline graph.

Flow (normal turn):
START → goal_resolver → memory_retriever → semantic_intake ─┬─ catalog_checker    ─┐
                                                             ├─ auth_validator     ─┤
                                                             ├─ tavily_subgraph    ─┼─ bigtools_inspector → workflow_planner → responder → response_evaluator → memory_updater → END
                                                             └─ document_analyzer ─┘   (4-way fan-in)                                ↑_____________(retry with feedback, max 2)

  tavily_subgraph (internal):
    tavily_searcher → research_curator
    (retrieval + semantic preservation — encapsulated as one unit)

Flow (closing turn — is_closing=True):
  START → goal_resolver → memory_retriever → semantic_intake → responder → response_evaluator → memory_updater → END
  (All validation nodes are bypassed — no wasted API calls)

Error flow (any wrapped node raises):
  semantic_intake / bigtools_inspector / responder → error_handler → END
  (_safe_node wrapper catches non-LangGraph exceptions and sets agent_error in state)

Node responsibilities:
  goal_resolver      — resolve active goal_id from user_active_goals (DB lookup)
  memory_retriever   — fetch+rank all 5 memory types into ranked_context
  semantic_intake    — normalize/decode input, detect apps + closing signals
  catalog_checker    — verify apps exist in the Shifu catalog (DB lookup)
  auth_validator     — verify user has active OAuth tokens (DB lookup)
  tavily_subgraph    — retrieval (TavilySearch + TavilyExtract) + semantic
                       preservation (research_curator) as one encapsulated unit
  document_analyzer  — ingest turn_resources (files attached this turn): extract
                       text (plan-gated OCR/vision), build turn_document_context
  bigtools_inspector — map validated apps to available tools via LLM (gpt-4o-mini)
  workflow_planner   — deliberative planning: generates private planning_trace before responder
  responder          — aggregation (pure Python) + Markdown response (LLM, streaming)
  response_evaluator — quality gate: evaluates responder output, retries up to 2×
  error_handler      — friendly error message + structured logging on node failure
  memory_updater     — persist decision to user_decision_memory if level_2 turn

Separation of concerns:
  goal_resolver / memory_retriever → cognitive context into ShifuState
  catalog / auth / tavily_subgraph / bigtools → validation JSON into ShifuState
  responder → single presenter: reads all state, streams Markdown to the user
  response_evaluator → self-correcting loop (gpt-4o-mini judge, max 2 retries)
  error_handler → resilience: logs + friendly fallback on unhandled exceptions
  memory_updater → post-turn persistence (fire-and-forget style)
"""

import asyncio
import logging
import traceback as _tb

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, default_retry_on

from app.agent.shared.nodes.action_runner import action_runner_node
from app.agent.shared.nodes.auth_validator import auth_validator_node
from app.agent.shared.nodes.catalog_checker import catalog_checker_node
from app.agent.shared.nodes.document_analyzer import document_analyzer_node
from app.agent.shared.nodes.error_handler import error_handler_node
from app.agent.shared.nodes.goal_resolver import goal_resolver_node
from app.agent.shared.nodes.memory_retriever import memory_retriever_node
from app.agent.shared.nodes.memory_updater import memory_updater_node
from app.agent.shared.nodes.responder import responder_node
from app.agent.shared.nodes.response_evaluator import response_evaluator_node
from app.agent.shared.nodes.semantic_intake import semantic_intake_node
from app.agent.shared.nodes.workflow_manager import workflow_manager_node
from app.agent.shifu_base_v1.graph.req_nodes import req_investigator_node
from app.agent.shifu_base_v1.graph.state import ShifuState, ShifuInputState, ShifuOutputState
from app.agent.shifu_base_v1.graph.tavily_subgraph import tavily_subgraph

logger = logging.getLogger(__name__)

_RESEARCH_TIMEOUT = 60.0  # el analista puede pedir una segunda busqueda

# ── LangGraph internal exceptions that must NOT be swallowed ─────────────────
try:
    from langgraph.errors import GraphInterrupt, NodeInterrupt
    _LG_SKIP = (GraphInterrupt, NodeInterrupt)
except ImportError:
    _LG_SKIP = ()


def _safe_node(fn, name: str):
    """Wrap a node so unhandled exceptions set agent_error instead of crashing.

    Re-raises LangGraph internal exceptions (GraphInterrupt, NodeInterrupt) so
    the framework's control flow (interrupt(), human-in-the-loop) is preserved.

    Re-raises transient exceptions (ConnectionError, HTTP 5xx, etc.) so the
    node-level RetryPolicy can intercept and retry them before escalating to
    agent_error. Uses default_retry_on to stay in sync with RetryPolicy's own
    decision function — no separate _TRANSIENT list that could drift.
    """
    async def wrapper(state):
        try:
            return await fn(state)
        except _LG_SKIP:
            raise
        except Exception as exc:
            if default_retry_on(exc):
                raise  # let RetryPolicy handle transient errors
            return {
                "agent_error": {
                    "node": name,
                    "exc": repr(exc),
                    "traceback": _tb.format_exc(),
                }
            }
    wrapper.__name__ = fn.__name__
    return wrapper


async def _tavily_with_timeout(state: ShifuState) -> dict:
    # ponytail: 45s hard cap; per-phase limits if tavily grows more complex
    _empty = {"retrieved_research": None, "retrieved_sources": None, "curated_research": None, "research_freshness": None}
    try:
        result = await asyncio.wait_for(tavily_subgraph.ainvoke(state), timeout=_RESEARCH_TIMEOUT)
        # tavily_subgraph is a compiled StateGraph(ShifuState) — ainvoke() returns the full
        # state snapshot, not just the diff. Selecting only the owned fields prevents
        # unintended concurrent writes to shared fields (e.g. user_connected_apps) when
        # auth_validator writes the same field in the same fan-in super-step.
        return {
            "retrieved_research": result.get("retrieved_research"),
            "retrieved_sources":  result.get("retrieved_sources"),
            "curated_research":   result.get("curated_research"),
            "research_freshness": result.get("research_freshness"),
        }
    except asyncio.TimeoutError:
        logger.warning("[tavily_subgraph] timeout after %.0fs — skipping research", _RESEARCH_TIMEOUT)
        return _empty


_req_investigator_safe = _safe_node(req_investigator_node, "req_investigator")


async def _req_with_research(state: ShifuState) -> dict:
    """El flujo de workflows no pasa por las ramas paralelas. Si en el MISMO mensaje el usuario pide crear algo y ademas
    pregunta un dato de internet ("...y de paso dime cuanto vale el bitcoin"), la busqueda corre aqui a la par: sin esto
    el agente respondia "no puedo buscar eso ahora" (prueba extrema del 2026-10-11). Los campos no se cruzan.
    ponytail: lo encontrado solo se usa cuando el turno lo redacta el responder (req_compose); un mensaje del flujo que
    se entrega tal cual (la confirmacion) no lo incluye. Si eso importa, pasar la confirmacion a req_compose."""
    if state.get("needs_external_info") and state.get("optimized_search_query"):
        flow, research = await asyncio.gather(_req_investigator_safe(state), _tavily_with_timeout(state))
        return {**research, **flow}
    return await _req_investigator_safe(state)


_builder = StateGraph(ShifuState, input=ShifuInputState, output=ShifuOutputState)

# Retry transient I/O errors (ConnectionError, HTTP 5xx) with exponential backoff.
# max_interval capped at 8s — 128s default is too long for a conversational agent.
_llm_retry = RetryPolicy(
    max_attempts=3,
    initial_interval=1.0,
    backoff_factor=2.0,
    max_interval=8.0,
)

# ── Nodes ──────────────────────────────────────────────────────────────────────
_builder.add_node("goal_resolver",     goal_resolver_node)
_builder.add_node("memory_retriever",  memory_retriever_node)
_builder.add_node("semantic_intake",   _safe_node(semantic_intake_node,    "semantic_intake"),
                  retry_policy=_llm_retry)
_builder.add_node("catalog_checker",   catalog_checker_node)
_builder.add_node("auth_validator",    auth_validator_node)
_builder.add_node("tavily_subgraph",   _tavily_with_timeout)
_builder.add_node("document_analyzer", _safe_node(document_analyzer_node, "document_analyzer"),
                  retry_policy=_llm_retry)
_builder.add_node("responder",         _safe_node(responder_node,          "responder"),
                  retry_policy=_llm_retry)
_builder.add_node("response_evaluator", response_evaluator_node)
_builder.add_node("req_investigator",  _req_with_research,
                  retry_policy=_llm_retry)
_builder.add_node("error_handler",     error_handler_node)
_builder.add_node("fan_in",            lambda state: {})  # junta las 4 ramas antes de decidir
_builder.add_node("action_runner",     _safe_node(action_runner_node, "action_runner"),
                  retry_policy=_llm_retry)
_builder.add_node("workflow_manager",  _safe_node(workflow_manager_node, "workflow_manager"),
                  retry_policy=_llm_retry)
_builder.add_node("memory_updater",    memory_updater_node)

# ── Edges ──────────────────────────────────────────────────────────────────────
# Memory preamble (always sequential, before any validation)
_builder.add_edge(START,              "goal_resolver")
_builder.add_edge("goal_resolver",    "memory_retriever")
_builder.add_edge("memory_retriever", "semantic_intake")


def _awaiting_answer(state: ShifuState) -> bool:
    """El ultimo mensaje del agente dejo una pregunta abierta: el turno es del usuario."""
    # ponytail: heuristica por signo de interrogacion; si da falsos, que lo decida un campo del responder
    last_ai = next((m for m in reversed(state.get("messages") or []) if getattr(m, "type", "") == "ai"), None)
    return last_ai is not None and "?" in str(last_ai.content)


def _route_from_intake(state: ShifuState):
    """
    Error short-circuit + fast-path shortcuts:

    0. agent_error: semantic_intake failed → error_handler.
    1. req_level set AND req_flow_action != "digress": mid-requirements flow,
       user is continuing it → req_investigator (skip fan-out).
       ("cancel" already cleared req_level in semantic_intake, so it naturally
       falls through here. "digress" deliberately does NOT — see
       semantic_intake_node's _classify_flow_action — so it falls through too,
       answering the actual question via the normal fan-out while the paused
       flow's req_level/req_pending_questions stay untouched for later resume.)
    2. is_closing / account_selection_resolved → responder (skip fan-out).
    3. Default: parallel fan-out to catalog + auth + tavily.
    """
    if state.get("agent_error"):
        return "error_handler"
    if state.get("system_event"):
        # Aviso de la interfaz (p. ej. "la cuenta de X quedo conectada"): no es un turno del usuario. Si el agente dejo
        # una pregunta abierta, no escribe nada (es un chat por turnos; la tarjeta ya confirma la conexion) y el aviso
        # queda en el historial para el proximo turno. Si no, el responder lo acusa y retoma. Nunca avanza el flujo.
        return "end" if _awaiting_answer(state) else "responder"
    # Modo act, fase 2: el usuario respondio a una escritura que esperaba su "si" (la decide semantic_intake).
    # confirm/change van directo a action_runner (ejecuta lo guardado / rehace con el cambio); cancel solo se acusa.
    if state.get("pending_decision") in ("confirm", "change"):
        return "action_runner"
    if state.get("pending_decision") == "cancel":
        return "responder"
    if state.get("req_level") is not None and state.get("req_flow_action") != "digress":
        return "req_investigator"
    if state.get("is_closing") or state.get("account_selection_resolved"):
        return "responder"
    return ["catalog_checker", "auth_validator", "tavily_subgraph", "document_analyzer"]


_builder.add_conditional_edges(
    "semantic_intake",
    _route_from_intake,
    {
        "error_handler":    "error_handler",
        "end":              END,
        "req_investigator": "req_investigator",
        "responder":        "responder",
        "action_runner":    "action_runner",
        "catalog_checker":  "catalog_checker",
        "auth_validator":   "auth_validator",
        "tavily_subgraph":  "tavily_subgraph",
        "document_analyzer": "document_analyzer",
    },
)

_builder.add_edge("req_investigator", "responder")

# 4-way fan-in: fan_in waits for catalog + auth + tavily_subgraph + document_analyzer
_builder.add_edge("catalog_checker", "fan_in")
_builder.add_edge("auth_validator", "fan_in")
_builder.add_edge("tavily_subgraph", "fan_in")
_builder.add_edge("document_analyzer", "fan_in")



def _route_after_fan_in(state: ShifuState):
    """Modo act (pedido puntual de datos de sus apps): action_runner ejecuta funciones en lugar de solo sugerirlas."""
    intent = (state.get("semantic_intake_debug") or {}).get("detected_intent")
    # v0.8.0: el resto va directo al responder. Antes pasaba por bigtools_inspector y workflow_planner (sistema viejo de
    # herramientas): gastaban una o dos llamadas al modelo por turno para sugerir acciones que ya no se ofrecen.
    # "command" = administrar sus workflows ya creados (listar, pausar, cambiar horario...): workflow_manager.
    return {"act": "action_runner", "command": "workflow_manager"}.get(intent, "responder")


_builder.add_conditional_edges("fan_in", _route_after_fan_in,
                               {"action_runner": "action_runner", "workflow_manager": "workflow_manager",
                                "responder": "responder"})


def _route_after_action(state: ShifuState):
    return "error_handler" if state.get("agent_error") else "responder"


_builder.add_conditional_edges("action_runner", _route_after_action,
                               {"error_handler": "error_handler", "responder": "responder"})
_builder.add_conditional_edges("workflow_manager", _route_after_action,
                               {"error_handler": "error_handler", "responder": "responder"})



def _route_after_responder(state: ShifuState):
    return "error_handler" if state.get("agent_error") else "response_evaluator"


_builder.add_conditional_edges(
    "responder",
    _route_after_responder,
    {"error_handler": "error_handler", "response_evaluator": "response_evaluator"},
)


def _route_after_evaluator(state: ShifuState):
    """Retry responder when evaluator injected feedback and retries remain."""
    return "responder" if state.get("eval_feedback") else "memory_updater"


_builder.add_conditional_edges(
    "response_evaluator",
    _route_after_evaluator,
    {"responder": "responder", "memory_updater": "memory_updater"},
)

_builder.add_edge("error_handler",  END)
_builder.add_edge("memory_updater", END)

v3_graph = _builder.compile()


def build_graph(checkpointer=None):
    """Return a compiled v3 graph. Pass checkpointer=InMemorySaver() in tests."""
    return _builder.compile(checkpointer=checkpointer) if checkpointer else _builder.compile()

