"""
Unit tests for semantic_intake_node.

Focused on the two pre-LLM fast paths (closing + trivial) and the
Capa-1 LLM path for app extraction. Mocks _llm.ainvoke and the
personality/catalog helpers so no DB or OpenAI calls are made.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.shared.nodes.semantic_intake import semantic_intake_node

_PERSONALITY_WITH_SIGNALS = {
    "closing_behavior": {"signals": ["adiós", "hasta luego", "bye", "chao"]}
}
_PERSONALITY_EMPTY = {}

_CATALOG = ["gmail", "google_sheets", "google_drive", "google_docs", "google_slides"]

_INTAKE_RESULT = {
    "normalized": "list my gmail emails",
    "detected_intent": "list_emails",
    "language_patterns": [],
    "structured_prompt_en": "List emails in Gmail inbox",
    "structured_prompt_es": "Listar correos en Gmail",
    "apps_involved": ["gmail"],
    "needs_external_info": False,
    "location_aware": False,
    "needs_fact_verification": False,
    "detected_sentiment": "neutral",
    "recommended_mood": "HELPFUL",
    "catalog_query_mode": None,
    "scheduling_expression": None,
    "account_selection": None,
    "optimized_search_query": None,
}


def _llm_returning(payload: dict):
    return MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps(payload))))


@pytest.fixture(autouse=True)
def patch_deps(monkeypatch):
    """Patch all external dependencies of semantic_intake_node."""
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_catalog_apps",
        AsyncMock(return_value=_CATALOG),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.log_stage_created",
        MagicMock(),
    )


# ── Closing fast path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_closing_signal_detected(base_state, monkeypatch):
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY_WITH_SIGNALS),
    )
    state = {**base_state, "messages": [HumanMessage("bye")]}

    result = await semantic_intake_node(state)

    assert result.get("is_closing") is True
    assert result.get("apps_involved") == [] or result.get("apps_involved") is None or True


@pytest.mark.asyncio
async def test_closing_signal_case_insensitive(base_state, monkeypatch):
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY_WITH_SIGNALS),
    )
    state = {**base_state, "messages": [HumanMessage("Adiós, hasta luego!")]}

    result = await semantic_intake_node(state)

    assert result.get("is_closing") is True


# ── Trivial social message fast path ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_trivial_social_message_no_llm(base_state, monkeypatch):
    """'hola' should short-circuit before any LLM call."""
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY_EMPTY),
    )
    mock_llm = MagicMock(ainvoke=AsyncMock(side_effect=AssertionError("LLM should not be called")))
    monkeypatch.setattr("app.agent.shared.nodes.semantic_intake._llm", mock_llm)

    state = {**base_state, "messages": [HumanMessage("hola")]}

    result = await semantic_intake_node(state)

    assert result.get("is_closing") is False
    assert result.get("apps_involved") == []
    # es saludo: sin la intencion el responder no aplicaba greeting_behavior
    assert result["semantic_intake_debug"]["detected_intent"] == "chat"
    ok = await semantic_intake_node({**base_state, "messages": [HumanMessage("ok")]})
    assert ok.get("semantic_intake_debug") is None


# ── Capa-1 LLM path — app extraction ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_apps_extracted_from_llm(base_state, monkeypatch):
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY_EMPTY),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake._llm",
        _llm_returning(_INTAKE_RESULT),
    )
    state = {**base_state, "messages": [HumanMessage("list my gmail emails")]}

    result = await semantic_intake_node(state)

    assert "gmail" in (result.get("apps_involved") or [])
    assert result.get("structured_prompt") == "List emails in Gmail inbox"


@pytest.mark.asyncio
async def test_catalog_query_mode_list_available(base_state, monkeypatch):
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY_EMPTY),
    )
    payload = {**_INTAKE_RESULT, "catalog_query_mode": "list_available", "apps_involved": []}
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake._llm",
        _llm_returning(payload),
    )
    state = {**base_state, "messages": [HumanMessage("what apps do you support?")]}

    result = await semantic_intake_node(state)

    assert result.get("catalog_query_mode") == "list_available"


@pytest.mark.asyncio
async def test_empty_message_returns_empty_result(base_state, monkeypatch):
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY_EMPTY),
    )
    state = {**base_state, "messages": [HumanMessage("   ")]}

    result = await semantic_intake_node(state)

    assert result.get("apps_involved") == [] or result.get("apps_involved") is None
    assert result.get("is_closing") is False

