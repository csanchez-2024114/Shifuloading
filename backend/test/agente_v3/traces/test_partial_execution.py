"""
Partial-execution tests using InMemorySaver + aupdate_state(as_node=...).

Pattern: inject pre-validated state as if bigtools_inspector just completed,
then let the graph continue from responder onward. This tests the tail of the
pipeline (responder → response_evaluator → memory_updater) without running the
first 7 nodes or touching real LLMs/DBs.

Why this matters: these tests fail fast if responder aggregation logic, mood
computation, or the evaluator's skip-path breaks — without needing mocks for
catalog_checker, auth_validator, semantic_intake, or Tavily.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from langgraph.checkpoint.memory import InMemorySaver

from app.agent.shifu_base_v1.graph.builder_standard import build_graph, _builder


# ── Minimal state representing bigtools_inspector output (pure-chat path) ─────
# Pure chat: apps_involved=[] so _aggregate returns (None, None) and
# response_evaluator ya no se salta el chat puro: aqui el stub no devuelve un veredicto valido y cae al camino "evaluador fallo -> se entrega".
# ranked_context=None so memory_updater skips the DB write.
# All bool fields set to False — ShifuState has non-optional booleans.
_STATE_AFTER_BIGTOOLS: dict = {
    "messages":                  [HumanMessage("¿Qué puedes hacer por mí?")],
    "user_id":                   "partial_user",
    "conversation_id":           "partial_conv_001",
    "user_email":                None,
    # Semantic intake outputs
    "structured_prompt":         None,
    "semantic_intake_debug":     None,
    "apps_involved":             [],        # pure-chat → evaluator skips LLM
    "needs_external_info":       False,
    "optimized_search_query":    None,
    # Multi-account
    "available_accounts":        None,
    "selected_accounts":         None,
    # Validation
    "validation_reports":        [],
    "retrieved_research":        None,
    "retrieved_sources":         None,
    "curated_research":          None,
    "missing_variables":         [],
    # Flags
    "is_closing":                False,
    "user_sentiment":            "neutral",
    "mood_state":                "HELPFUL",
    # Temporal
    "user_timezone":             "America/Guatemala",
    "user_location":             None,
    "user_country_code":         "GT",
    "location_aware":            False,
    "needs_fact_verification":   False,
    "catalog_query_mode":        None,
    "catalog_available_apps":    None,
    "catalog_apps_grouped":      None,
    "user_connected_apps":       None,
    "schedule_context":          None,
    "user_preferences_context":  None,
    # Pipeline
    "requirement_level":         None,
    "effort_level":              "low",
    "model_name":                "gpt-4o-mini",
    # Routing
    "account_selection_resolved": False,
    # Memory
    "goal_id":                   None,
    "raw_memories":              None,
    "ranked_context":            None,    # None → memory_updater skips DB write
    "decision_logged":           False,
    # Reliability
    "agent_error":               None,
    "eval_retry_count":          0,
    "eval_feedback":             None,
    "current_time_utc":          "2026-06-21T00:00:00Z",
}


# ── Responder helpers fixture (avoids DB calls inside responder_node) ─────────

@pytest.fixture(autouse=True)
def patch_responder_helpers(monkeypatch):
    """Mock the async DB helpers responder calls on every invocation."""
    monkeypatch.setattr(
        "app.agent.shared.nodes.responder.get_agent_identity",
        AsyncMock(return_value={"name": "Shifu", "role": "assistant"}),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.responder.get_agent_personality",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.responder.build_system_messages",
        MagicMock(return_value=[SystemMessage(content="You are Shifu.")]),
    )


# ── Test 1: responder runs and produces an AIMessage ─────────────────────────

async def test_responder_runs_from_injected_bigtools_state(monkeypatch):
    """
    Inject state at bigtools_inspector, verify the graph tail executes:
    responder produces an AIMessage and the graph reaches END without errors.
    """
    from langchain_openai import ChatOpenAI

    monkeypatch.setattr(
        ChatOpenAI,
        "ainvoke",
        AsyncMock(return_value=AIMessage(content="Puedo ayudarte con muchas cosas.")),
    )

    checkpointer = InMemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "partial_test_001"}}

    # Teleport the graph: inject state as if bigtools_inspector just wrote it
    await graph.aupdate_state(config, _STATE_AFTER_BIGTOOLS, as_node="fan_in")

    # Continue from the next node (responder) to END
    result = await graph.ainvoke(None, config)

    assert result is not None
    messages = result.get("messages") or []
    ai_msgs = [m for m in messages if isinstance(m, AIMessage)]
    assert len(ai_msgs) >= 1, "responder must have added at least one AIMessage"
    assert "Puedo" in ai_msgs[-1].content


# ── Test 2: graph pauses before response_evaluator ───────────────────────────

async def test_graph_pauses_before_response_evaluator(monkeypatch):
    """
    Compile with interrupt_before=["response_evaluator"] to verify the graph
    stops exactly there and the checkpoint records the pending node correctly.
    Useful for testing responder output in isolation without evaluator's LLM.
    """
    from langchain_openai import ChatOpenAI

    monkeypatch.setattr(
        ChatOpenAI,
        "ainvoke",
        AsyncMock(return_value=AIMessage(content="Aquí está mi respuesta.")),
    )

    checkpointer = InMemorySaver()
    graph_paused = _builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["response_evaluator"],
    )
    config = {"configurable": {"thread_id": "partial_test_002"}}

    await graph_paused.aupdate_state(config, _STATE_AFTER_BIGTOOLS, as_node="fan_in")

    # Graph stops before response_evaluator — ainvoke returns the current state
    result = await graph_paused.ainvoke(None, config)

    # Verify responder ran and produced its message
    messages = (result or {}).get("messages") or []
    ai_msgs = [m for m in messages if isinstance(m, AIMessage)]
    assert len(ai_msgs) >= 1, "responder must have run before the interrupt"

    # Verify the checkpoint records response_evaluator as the next pending node
    snapshot = await graph_paused.aget_state(config)
    assert "response_evaluator" in (snapshot.next or []), (
        f"Expected response_evaluator in snapshot.next, got: {snapshot.next}"
    )
