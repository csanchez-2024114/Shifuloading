"""
Level 2 trace test — multiple connected accounts.

Two scenarios:
  1. 2 accounts → auth_validator returns pending_selection, graph completes.
  2. account_selection_resolved=True in state → graph bypasses fan-out entirely
     (semantic_intake routes directly to responder).
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
_TWO_ACCOUNTS = [
    {"user_id": "multi_user", "provider": "gmail",
     "email": "personal@gmail.com", "account_id": "personal@gmail.com", "status": "active"},
    {"user_id": "multi_user", "provider": "gmail",
     "email": "work@gmail.com",     "account_id": "work@gmail.com",     "status": "active"},
]


def _input(text, **overrides):
    base = {
        "messages":                [HumanMessage(text)],
        "user_id":                 "multi_user",
        "conversation_id":         "multi_conv",
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
    return {**base, **overrides}


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


def _patch_fan_out(monkeypatch):
    """Shared patches for tests that exercise the full fan-out path."""
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
        AsyncMock(return_value=AIMessage(content="¿Cuál cuenta quieres usar?")),
    )


@pytest.mark.asyncio
async def test_two_accounts_returns_pending_selection(monkeypatch):
    """2 connected accounts → auth_validator returns pending_selection."""
    monkeypatch.setattr(
        mongo_manager, "db",
        FakeDB(
            catalog_apps=[{"nameApi": "gmail", "active": True, "visible": True, "category": "email"}],
            user_connected_accounts=_TWO_ACCOUNTS,
        ),
    )
    _patch_fan_out(monkeypatch)

    result = await v3_graph.ainvoke(_input("list my gmail emails"))

    assert result is not None
    reports = result.get("validation_reports") or []
    auth_reports = [r for r in reports if r.get("source") == "auth"]
    assert any(r["status"] == "pending_selection" for r in auth_reports)
    # available_accounts is not in ShifuOutputState; verify pending via validation_reports
    pending = [r for r in auth_reports if r.get("status") == "pending_selection"]
    assert any(r.get("app") == "gmail" for r in pending)


@pytest.mark.asyncio
async def test_account_selection_resolved_bypasses_fan_out(monkeypatch):
    """account_selection_resolved=True in state → responder without catalog/auth/tavily."""
    # No mongo needed — fan-out is bypassed; responder builds response from state.
    monkeypatch.setattr(
        mongo_manager, "db",
        FakeDB(),
    )
    # Patch semantic_intake LLM to return account_selection as a dict (correct format)
    monkeypatch.setattr(
        "app.agent.shared.nodes.semantic_intake._llm",
        MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps({
            **_INTAKE_GMAIL,
            "account_selection": {"gmail": "personal@gmail.com"},
        })))),
    )
    catalog_llm_called = []
    monkeypatch.setattr(
        "app.agent.shared.nodes.catalog_checker.resolve_app_key",
        AsyncMock(side_effect=lambda x: catalog_llm_called.append(x) or x),
    )
    monkeypatch.setattr(
        ChatOpenAI, "ainvoke",
        AsyncMock(return_value=AIMessage(content="Usando personal@gmail.com.")),
    )

    # available_accounts must be in ShifuInputState so semantic_intake sees the pending selection
    result = await v3_graph.ainvoke(_input(
        "usa personal@gmail.com",
        selected_accounts={"gmail": "personal@gmail.com"},
        available_accounts={"gmail": [
            {"account_id": "personal@gmail.com", "email": "personal@gmail.com"},
            {"account_id": "work@gmail.com",     "email": "work@gmail.com"},
        ]},
    ))

    assert result is not None
    # catalog_checker should NOT have been called (fan-out bypassed)
    assert catalog_llm_called == [], "catalog_checker ran but should have been bypassed"

