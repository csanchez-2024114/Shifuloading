"""
Unit tests for catalog_checker_node.

Mocks: mongo_manager.db → FakeDB, resolve_app_key → pass-through.
No network or LLM calls.
"""

import pytest
from unittest.mock import AsyncMock, patch

from test.agente_v3.conftest import FakeDB
from app.agent.shared.nodes.catalog_checker import catalog_checker_node


# resolve_app_key calls get_catalog_apps → DB. Patch it to a no-op pass-through.
_PASSTHROUGH = AsyncMock(side_effect=lambda x: x)


@pytest.fixture(autouse=True)
def patch_resolver():
    with patch("app.agent.shared.nodes.catalog_checker.resolve_app_key", _PASSTHROUGH):
        yield


@pytest.fixture
def with_db(monkeypatch):
    """Provide a DB factory: call with_db(catalog_apps=[...]) inside the test."""
    def _make(**kwargs):
        from app.core.mongo import mongo_manager
        db = FakeDB(**kwargs)
        monkeypatch.setattr(mongo_manager, "db", db)
        return db
    return _make


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_visible_app_is_ok(base_state, with_db):
    with_db(catalog_apps=[{"nameApi": "gmail", "active": True, "visible": True}])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await catalog_checker_node(state)

    reports = result["validation_reports"]
    assert len(reports) == 1
    assert reports[0]["status"] == "ok"
    assert reports[0]["app"] == "gmail"


@pytest.mark.asyncio
async def test_beta_app_is_ok(base_state, with_db):
    """active=True, visible=False (beta/internal) → still usable."""
    with_db(catalog_apps=[{"nameApi": "gmail", "active": True, "visible": False}])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await catalog_checker_node(state)

    assert result["validation_reports"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_maintenance_app_is_error(base_state, with_db):
    """active=False, visible=True → maintenance."""
    with_db(catalog_apps=[{"nameApi": "gmail", "active": False, "visible": True}])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await catalog_checker_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "error"
    assert r["reason"] == "maintenance"


@pytest.mark.asyncio
async def test_archived_app_is_error(base_state, with_db):
    """active=False, visible=False → archived."""
    with_db(catalog_apps=[{"nameApi": "gmail", "active": False, "visible": False}])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await catalog_checker_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "error"
    assert r["reason"] == "archived"


@pytest.mark.asyncio
async def test_unknown_app_is_not_found(base_state, with_db):
    with_db(catalog_apps=[{"nameApi": "sheets", "active": True, "visible": True}])
    state = {**base_state, "apps_involved": ["unknown_app"]}

    result = await catalog_checker_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "error"
    assert r["reason"] == "not_found"


@pytest.mark.asyncio
async def test_no_apps_returns_empty(base_state, with_db):
    with_db(catalog_apps=[])
    state = {**base_state, "apps_involved": []}

    result = await catalog_checker_node(state)

    assert result["validation_reports"] == []


@pytest.mark.asyncio
async def test_list_available_mode(base_state, with_db):
    with_db(catalog_apps=[
        {"nameApi": "gmail",  "name": "Gmail",  "active": True, "visible": True,  "category": "email"},
        {"nameApi": "sheets", "name": "Sheets", "active": True, "visible": True,  "category": "productivity"},
        {"nameApi": "legacy", "name": "Legacy", "active": False, "visible": True, "category": "productivity"},
    ])
    state = {**base_state, "apps_involved": [], "catalog_query_mode": "list_available"}

    result = await catalog_checker_node(state)

    available = result["catalog_available_apps"]
    assert "Gmail" in available
    assert "Sheets" in available
    assert "Legacy" not in available  # inactive → excluded
    assert result["validation_reports"] == []

