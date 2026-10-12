"""
Level 2 trace test — auth fails (not_connected).

Verifies the graph completes when the user has no connected accounts:
  catalog_checker → ok  |  auth_validator → error (not_connected)
  bigtools_inspector → skips  |  responder → level_1 response
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.agent.shifu_base_v1.graph.builder_standard import v3_graph
from app.core.mongo import mongo_manager
from test.agente_v3.conftest import FakeDB


_PERSONALITY  = {"closing_behavior": {"signals": ["bye", "adiós"]}}
_CATALOG_LIST = ["gmail", "google_sheets"]
_INTAKE_GMAIL = {
    "normalized":           "list my gmail emails",
    "detected_intent":      "list_emails",
    "language_patterns":    [],
    "structured_prompt_en": "List emails in Gmail inbox",
    "structured_prompt_es": "Listar correos en Gmail",
    "apps_involved":        ["gmail"],
    "needs_external_info":  False,
    "location_aware":       False,
    "needs_fact_verification": False,
    "detected_sentiment":   "neutral",
    "recommended_mood":     "HELPFUL",
    "catalog_query_mode":   None,
    "scheduling_expression": None,
    "account_selection":    None,
    "optimized_search_query": None,
}


def _input(text):
    return {
        "messages":                [HumanMessage(text)],
        "user_id":                 "auth_err_user",
        "conversation_id":         "auth_err_conv",
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
def mock_mongo(monkeypatch):
    db = FakeDB(
        catalog_apps=[
            {"nameApi": "gmail", "active": True, "visible": True, "category": "email"},
        ],
        user_connected_accounts=[],   # ← no accounts → auth error
    )
    monkeypatch.setattr(mongo_manager, "db", db)


@pytest.fixture(autouse=True)
def mock_helpers(monkeypatch):
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_catalog_apps",
        AsyncMock(return_value=_CATALOG_LIST),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.log_stage_created",
        MagicMock(),
    )


@pytest.mark.asyncio
async def test_auth_error_graph_completes(monkeypatch):
    """Graph must complete without crashing when no account is connected."""
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake._llm",
        MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps(_INTAKE_GMAIL)))),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.catalog_checker.resolve_app_key",
        AsyncMock(side_effect=lambda x: x),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.auth_validator.resolve_app_key",
        AsyncMock(side_effect=lambda x: x),
    )
    monkeypatch.setattr(
        "app.agent.shifu_base_v1.graph.tavily_subgraph",
        MagicMock(ainvoke=AsyncMock(return_value={
            "retrieved_research": None, "retrieved_sources": None, "curated_research": None,
        })),
    )
    monkeypatch.setattr(
        ChatOpenAI, "ainvoke",
        AsyncMock(return_value=AIMessage(content="Por favor conecta tu cuenta de Gmail.")),
    )

    result = await v3_graph.ainvoke(_input("list my gmail emails"))

    assert result is not None
    reports = result.get("validation_reports") or []
    auth_reports = [r for r in reports if r.get("source") == "auth"]
    assert any(r["status"] == "error" for r in auth_reports), "auth should fail (no accounts)"
    assert any(r.get("reason") == "not_connected" for r in auth_reports)


@pytest.mark.asyncio
async def test_auth_error_bigtools_skips(monkeypatch):
    """When auth fails, bigtools_inspector must not be invoked with LLM."""
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake._llm",
        MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps(_INTAKE_GMAIL)))),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.catalog_checker.resolve_app_key",
        AsyncMock(side_effect=lambda x: x),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.auth_validator.resolve_app_key",
        AsyncMock(side_effect=lambda x: x),
    )
    monkeypatch.setattr(
        "app.agent.shifu_base_v1.graph.tavily_subgraph",
        MagicMock(ainvoke=AsyncMock(return_value={
            "retrieved_research": None, "retrieved_sources": None, "curated_research": None,
        })),
    )
    bigtools_llm = AsyncMock(side_effect=AssertionError("bigtools LLM should not be called"))
    monkeypatch.setattr("app.agent.shared.nodes.bigtools_inspector._llm",
                        MagicMock(ainvoke=bigtools_llm))
    monkeypatch.setattr(
        ChatOpenAI, "ainvoke",
        AsyncMock(return_value=AIMessage(content="Conecta tu Gmail.")),
    )

    result = await v3_graph.ainvoke(_input("list my gmail emails"))
    assert result is not None   # graph completed; bigtools LLM was never called

