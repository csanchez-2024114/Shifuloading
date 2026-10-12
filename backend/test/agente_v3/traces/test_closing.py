"""
Level 2 trace test — extended closing fast-path.

Verifies that various closing signals (beyond "bye") all trigger the
fast-path: semantic_intake → responder (catalog/auth/tavily bypassed).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.agent.shifu_base_v1.graph.builder_standard import v3_graph
from app.core.mongo import mongo_manager
from test.agente_v3.conftest import FakeDB


_PERSONALITY = {
    "closing_behavior": {
        "signals": ["adiós", "hasta luego", "bye", "chao", "nos vemos"]
    }
}


def _input(text):
    return {
        "messages":                [HumanMessage(text)],
        "user_id":                 "closing_user",
        "conversation_id":         "closing_conv",
        "apps_involved":           [],
        "validation_reports":      [],
        "selected_accounts":       None,
        "available_accounts":      None,
        "catalog_query_mode":      None,
        "is_closing":              False,
        "structured_prompt":       None,
        "effort_level":            "low",
        "model_name":              "gpt-4o-mini",
        "current_time_utc":        "2026-06-16T00:00:00Z",
        "user_timezone":           None,
        "user_location":           None,
        "user_country_code":       None,
        "user_preferences_context": None,
        "missing_variables":       [],
    }


@pytest.fixture(autouse=True)
def mock_helpers(monkeypatch):
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_catalog_apps",
        AsyncMock(return_value=["gmail", "google_sheets"]),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.log_stage_created",
        MagicMock(),
    )
    monkeypatch.setattr(mongo_manager, "db", FakeDB())
    monkeypatch.setattr(
        ChatOpenAI, "ainvoke",
        AsyncMock(return_value=AIMessage(content="¡Hasta luego! Aquí estaré cuando me necesites.")),
    )


@pytest.mark.parametrize("message", [
    "chao",
    "Chao!",
    "Hasta luego, gracias",
    "HASTA LUEGO",
    "nos vemos luego",
    "Nos Vemos",
    "adiós",
    "Adiós, fue un placer",
])
@pytest.mark.asyncio
async def test_closing_signal_sets_is_closing(message):
    """Any closing signal → mood_state=CLOSING and graph completes."""
    result = await v3_graph.ainvoke(_input(message))

    assert result is not None
    assert result.get("mood_state") == "CLOSING", f"Expected mood_state=CLOSING for '{message}'"
    assert "messages" in result


@pytest.mark.asyncio
async def test_closing_no_catalog_call(monkeypatch):
    """Closing fast-path must not invoke catalog_checker."""
    called = []
    monkeypatch.setattr(
        "app.agent.shared.nodes.catalog_checker.resolve_app_key",
        AsyncMock(side_effect=lambda x: called.append(x) or x),
    )

    await v3_graph.ainvoke(_input("bye"))

    assert called == [], "catalog_checker.resolve_app_key should not be called on closing"

