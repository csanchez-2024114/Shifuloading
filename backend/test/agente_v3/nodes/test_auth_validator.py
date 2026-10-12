"""
Unit tests for auth_validator_node.

Covers scenarios A (0 usable), B (1 usable auto-select),
C (2+ usable with/without prior selection), expired, revoked.
Mocks: mongo_manager.db → FakeDB, resolve_app_key → pass-through.
"""

import pytest
from unittest.mock import AsyncMock, patch

from test.agente_v3.conftest import FakeDB
from app.agent.shared.nodes.auth_validator import auth_validator_node


_PASSTHROUGH = AsyncMock(side_effect=lambda x: x)


@pytest.fixture(autouse=True)
def patch_resolver():
    with patch("app.agent.shared.nodes.auth_validator.resolve_app_key", _PASSTHROUGH):
        yield


@pytest.fixture
def with_db(monkeypatch):
    def _make(**kwargs):
        from app.core.mongo import mongo_manager
        db = FakeDB(**kwargs)
        monkeypatch.setattr(mongo_manager, "db", db)
        return db
    return _make


def _account(email, status="active"):
    return {"user_id": "user_test_001", "provider": "gmail", "email": email,
            "account_id": email, "status": status}


# ── Scenario A — 0 usable accounts ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_a_not_connected(base_state, with_db):
    with_db(user_connected_accounts=[])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "error"
    assert r["reason"] == "not_connected"
    assert r["needs_auth"] is True


@pytest.mark.asyncio
async def test_scenario_a_expired(base_state, with_db):
    with_db(user_connected_accounts=[_account("alan@gmail.com", status="expired")])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "error"
    assert r["reason"] == "expired"
    assert r["needs_auth"] is True


@pytest.mark.asyncio
async def test_scenario_a_revoked(base_state, with_db):
    with_db(user_connected_accounts=[_account("alan@gmail.com", status="revoked")])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "error"
    assert r["reason"] == "revoked"


# ── Scenario B — exactly 1 usable account (auto-select) ──────────────────────

@pytest.mark.asyncio
async def test_scenario_b_auto_select(base_state, with_db):
    with_db(user_connected_accounts=[_account("alan@gmail.com")])
    state = {**base_state, "apps_involved": ["gmail"]}

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "ok"
    assert result["selected_accounts"].get("gmail") == "alan@gmail.com"


# ── Scenario C — 2+ usable accounts ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_c_pending_selection(base_state, with_db):
    with_db(user_connected_accounts=[
        _account("alan@gmail.com"),
        _account("work@gmail.com"),
    ])
    state = {**base_state, "apps_involved": ["gmail"], "selected_accounts": None}

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "pending_selection"
    assert len(r["accounts"]) == 2
    assert "gmail" in result["available_accounts"]


@pytest.mark.asyncio
async def test_scenario_c_valid_prior_selection(base_state, with_db):
    with_db(user_connected_accounts=[
        _account("alan@gmail.com"),
        _account("work@gmail.com"),
    ])
    state = {
        **base_state,
        "apps_involved":    ["gmail"],
        "selected_accounts": {"gmail": "alan@gmail.com"},
    }

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "ok"


@pytest.mark.asyncio
async def test_scenario_c_stale_selection(base_state, with_db):
    """Previously selected account no longer exists → re-pending."""
    with_db(user_connected_accounts=[
        _account("alan@gmail.com"),
        _account("work@gmail.com"),
    ])
    state = {
        **base_state,
        "apps_involved":    ["gmail"],
        "selected_accounts": {"gmail": "old@gmail.com"},  # stale
    }

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "pending_selection"


# ── Modes ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_apps_returns_empty(base_state, with_db):
    with_db(user_connected_accounts=[])
    state = {**base_state, "apps_involved": []}

    result = await auth_validator_node(state)

    assert result["validation_reports"] == []


@pytest.mark.asyncio
async def test_add_account_mode(base_state, with_db):
    with_db(user_connected_accounts=[])
    state = {**base_state, "apps_involved": ["gmail"], "catalog_query_mode": "add_account"}

    result = await auth_validator_node(state)

    r = result["validation_reports"][0]
    assert r["status"] == "add_account"
    assert r["needs_auth"] is True

