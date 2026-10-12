"""
Level 2 trace tests — full graph invocations with mocked DB and LLMs.

Uses the closing fast-path (START → goal_resolver → memory_retriever →
semantic_intake → responder → memory_updater → END) to avoid needing
catalog/auth/tavily mocks for the most basic smoke test.

For the validate path, all three parallel branches (catalog_checker,
auth_validator, tavily_subgraph) are exercised with a FakeDB that
returns a connected, active gmail account.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.shifu_base_v1.graph.builder_standard import v3_graph
from app.core.mongo import mongo_manager
from test.agente_v3.conftest import FakeDB


_PERSONALITY_SIGNALS = {"closing_behavior": {"signals": ["bye", "adiós"]}}
_CATALOG = ["gmail", "google_sheets"]
_INTAKE_OK = {
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


def _base_input(text="bye"):
    return {
        "messages":                [HumanMessage(text)],
        "user_id":                 "trace_user",
        "conversation_id":         "trace_conv",
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
    """Patch mongo_manager.db with a FakeDB for all trace tests."""
    db = FakeDB(
        catalog_apps=[
            {"nameApi": "gmail", "active": True, "visible": True, "category": "email"},
        ],
        user_connected_accounts=[
            {"user_id": "trace_user", "provider": "gmail",
             "email": "trace@gmail.com", "account_id": "trace@gmail.com", "status": "active"},
        ],
    )
    monkeypatch.setattr(mongo_manager, "db", db)


@pytest.fixture(autouse=True)
def mock_helpers(monkeypatch):
    """Patch shared helpers used by goal_resolver, memory_retriever, etc."""
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake.get_agent_personality",
        AsyncMock(return_value=_PERSONALITY_SIGNALS),
    )
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
async def test_closing_path_completes(monkeypatch):
    """Graph completes without error on a closing message."""
    # responder creates its LLM inline — patch it via the class
    from langchain_openai import ChatOpenAI
    monkeypatch.setattr(
        ChatOpenAI,
        "ainvoke",
        AsyncMock(return_value=AIMessage(content="Goodbye! Let me know if you need anything.")),
    )

    result = await v3_graph.ainvoke(_base_input("bye"))

    assert result is not None
    assert "messages" in result
    assert result.get("mood_state") == "CLOSING"


# ── Validate path — happy path (gmail connected, active) ─────────────────────

@pytest.mark.asyncio
async def test_validate_path_gmail_connected(monkeypatch):
    """Full graph on 'list gmail emails' with connected account — no errors."""
    from langchain_openai import ChatOpenAI

    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake._llm",
        MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps(_INTAKE_OK)))),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.bigtools_inspector._llm",
        MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps({
            "can_proceed": True,
            "tool_mapping": [{"step": 1, "app": "gmail", "tool": "listar_correos", "purpose": "list"}],
            "missing_variables": [],
        })))),
    )
    monkeypatch.setattr(
        "app.agent.shared.nodes.bigtools_inspector.load_tools_context",
        AsyncMock(return_value="  gmail: listar_correos"),
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
        ChatOpenAI,
        "ainvoke",
        AsyncMock(return_value=AIMessage(content="Here are your emails.")),
    )
    # Patch tavily subgraph to return immediately
    monkeypatch.setattr(
        "app.agent.shifu_base_v1.graph.tavily_subgraph",
        MagicMock(ainvoke=AsyncMock(return_value={
            "retrieved_research": None, "retrieved_sources": None, "curated_research": None,
        })),
    )

    result = await v3_graph.ainvoke(_base_input("list my gmail emails"))

    assert result is not None
    reports = result.get("validation_reports") or []
    catalog_reports = [r for r in reports if r.get("source") == "catalog"]
    auth_reports    = [r for r in reports if r.get("source") == "auth"]

    assert any(r["status"] == "ok" for r in catalog_reports), "catalog should pass"
    assert any(r["status"] == "ok" for r in auth_reports),    "auth should pass (account connected)"

