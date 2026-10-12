"""ui_actions: el boton de conectar sale del estado del turno, dice como conectar y se guarda en el historial."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.shared.helpers import platform_context
from app.routes.chat.chat import _build_ui_actions
from app.services.chat_memory import save_message


@pytest.fixture(autouse=True)
def _actions(monkeypatch):
    # Que apps tienen acciones es dato de la plataforma; aqui se fija para no depender del registro real
    monkeypatch.setattr(platform_context, "app_has_actions", lambda app: app.lower() not in {"notion"})


def _auth(app, reason="not_connected"):
    return {"source": "auth", "app": app, "status": "error", "reason": reason, "needs_auth": True, "auth_url": f"/auth/{app}/login"}


def test_connect_app_carries_reason_url_and_auth_type():
    [a] = _build_ui_actions({"validation_reports": [_auth("slack", "expired")]})
    assert a == {"type": "connect_app", "app": "slack", "reason": "expired", "auth_url": "/auth/slack/login", "auth_type": "oauth2"}


def test_apikey_app_is_told_apart_from_oauth():
    [a] = _build_ui_actions({"validation_reports": [_auth("openai")]})
    assert a["auth_type"] == "apikey"


def test_no_button_for_an_app_the_catalog_does_not_have():
    reports = [{"source": "catalog", "app": "shopify", "status": "error"}, _auth("shopify")]
    assert _build_ui_actions({"validation_reports": reports}) == []


def test_button_uses_the_canonical_catalog_key_not_the_alias_the_user_typed():
    r = {**_auth("sheets"), "app_key": "google_sheets", "auth_url": "/auth/google/sheets/login"}
    [a] = _build_ui_actions({"validation_reports": [r]})
    assert (a["app"], a["auth_type"]) == ("google_sheets", "oauth2")


def test_one_button_per_missing_app():
    reports = [_auth("gmail"), {**_auth("sheets"), "app_key": "google_sheets"}, {"source": "auth", "app": "slack", "status": "ok"}]
    assert [a["app"] for a in _build_ui_actions({"validation_reports": reports})] == ["gmail", "google_sheets"]


def test_no_reports_no_actions():
    assert _build_ui_actions({}) == []


async def test_actions_are_stored_with_the_message():
    col = MagicMock(insert_one=AsyncMock(), update_one=AsyncMock(), find_one=AsyncMock(return_value=None))
    db = MagicMock()
    db.__getitem__.return_value = col
    actions = [{"type": "connect_app", "app": "gmail"}]
    await save_message("u", "c", "ai", "hola", db, ui_actions=actions)
    stored = col.insert_one.await_args_list[0].args[0]
    assert stored["ui_actions"] == actions


def test_no_button_for_an_app_the_platform_cannot_do_anything_with():
    # Conectarla no le serviria al usuario; ofrecerla era exponer un dato interno ("se conecta pero no hace nada")
    assert _build_ui_actions({"validation_reports": [_auth("notion"), _auth("gmail")]})[0]["app"] == "gmail"
    assert len(_build_ui_actions({"validation_reports": [_auth("notion")]})) == 0
