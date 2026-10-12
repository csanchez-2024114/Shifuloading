"""
Unit tests for bigtools_inspector_node.

Mocks: _llm.ainvoke → controlled JSON, load_tools_context → string.
No network calls.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage

from app.agent.shared.nodes.bigtools_inspector import bigtools_inspector_node


def _llm_returning(payload: dict):
    return MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=json.dumps(payload))))


TOOLS_TEXT = "  gmail: listar_correos, enviar_correo\n  sheets: read_sheet_range"


@pytest.mark.asyncio
async def test_no_validated_apps_returns_empty(base_state):
    """catalog or auth failed for all apps → bigtools skips."""
    state = {
        **base_state,
        "apps_involved":      ["gmail"],
        "validation_reports": [
            {"source": "catalog", "app": "gmail", "status": "error"},
            {"source": "auth",    "app": "gmail", "status": "error"},
        ],
        "structured_prompt": "list emails",
    }
    result = await bigtools_inspector_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_can_proceed_true(base_state):
    payload = {
        "can_proceed": True,
        "tool_mapping": [{"step": 1, "app": "gmail", "tool": "listar_correos", "purpose": "list emails"}],
        "missing_variables": [],
    }
    state = {
        **base_state,
        "apps_involved":      ["gmail"],
        "validation_reports": [
            {"source": "catalog", "app": "gmail", "status": "ok"},
            {"source": "auth",    "app": "gmail", "status": "ok"},
        ],
        "structured_prompt": "list emails in gmail",
    }
    with (
        patch("app.agent.shared.nodes.bigtools_inspector._llm", _llm_returning(payload)),
        patch("app.agent.shared.nodes.bigtools_inspector.load_tools_context",
              AsyncMock(return_value=TOOLS_TEXT)),
    ):
        result = await bigtools_inspector_node(state)

    reports = result["validation_reports"]
    assert len(reports) == 1
    assert reports[0]["status"] == "ok"
    assert reports[0]["source"] == "bigtools"
    assert len(reports[0]["tool_mapping"]) == 1
    assert result["missing_variables"] == []


@pytest.mark.asyncio
async def test_can_proceed_false_when_no_tools(base_state):
    payload = {
        "can_proceed": False,
        "tool_mapping": [],
        "missing_variables": [],
        "notes": "hubspot has no tools implemented",
    }
    state = {
        **base_state,
        "apps_involved":      ["hubspot"],
        "validation_reports": [
            {"source": "catalog", "app": "hubspot", "status": "ok"},
            {"source": "auth",    "app": "hubspot", "status": "ok"},
        ],
        "structured_prompt": "create deal in hubspot",
    }
    with (
        patch("app.agent.shared.nodes.bigtools_inspector._llm", _llm_returning(payload)),
        patch("app.agent.shared.nodes.bigtools_inspector.load_tools_context",
              AsyncMock(return_value="  hubspot: (tools not yet implemented)")),
    ):
        result = await bigtools_inspector_node(state)

    reports = result["validation_reports"]
    assert reports[0]["status"] == "error"
    assert "hubspot" in reports[0]["message"].lower() or reports[0].get("apps") == ["hubspot"]


@pytest.mark.asyncio
async def test_missing_variables_surfaced(base_state):
    payload = {
        "can_proceed": True,
        "tool_mapping": [{"step": 1, "app": "gmail", "tool": "enviar_correo", "purpose": "send email"}],
        "missing_variables": ["recipient_email", "subject"],
    }
    state = {
        **base_state,
        "apps_involved":      ["gmail"],
        "validation_reports": [
            {"source": "catalog", "app": "gmail", "status": "ok"},
            {"source": "auth",    "app": "gmail", "status": "ok"},
        ],
        "structured_prompt": "send an email",
    }
    with (
        patch("app.agent.shared.nodes.bigtools_inspector._llm", _llm_returning(payload)),
        patch("app.agent.shared.nodes.bigtools_inspector.load_tools_context",
              AsyncMock(return_value=TOOLS_TEXT)),
    ):
        result = await bigtools_inspector_node(state)

    assert "recipient_email" in result["missing_variables"]
    assert "subject" in result["missing_variables"]

