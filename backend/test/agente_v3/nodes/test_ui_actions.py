"""Acciones de interfaz: el catalogo es dato; el codigo decide que se ofrece y valida lo que el modelo pide."""
from app.agent.shared.helpers import ui_actions as ua
from app.routes.chat.chat import _build_ui_actions

CATALOG = [
    {"id": "open_workflows", "label": {"es": "Ver mis workflows", "en": "See my workflows"}, "source": "user", "description": "Opens the workflows panel."},
    {"id": "open_app", "label": "Ver esta app", "source": "user", "description": "Opens one app.", "params": {"app": "app key"}},
    {"id": "open_billing", "label": "Ver mi plan", "source": "user", "description": "Opens billing.", "plans": ["pro"]},
    {"id": "delete_account", "label": "Borrar mi cuenta", "source": "user", "description": "Deletes the account.", "confirm": True},
    {"id": "connect_app", "label": "Conectar app", "source": "system", "description": "Connect button."},
]
ALL = [a["id"] for a in CATALOG]


async def _offer(monkeypatch, supported, plan):
    async def catalog():
        return CATALOG
    monkeypatch.setattr(ua, "get_catalog", catalog)
    return await ua.offer(supported, plan)


async def test_a_turn_only_offers_what_the_client_supports_and_the_plan_allows(monkeypatch):
    assert await _offer(monkeypatch, ALL, "free") == ["open_workflows", "open_app", "delete_account"]  # billing: solo pro
    assert await _offer(monkeypatch, ALL, "pro") == ["open_workflows", "open_app", "open_billing", "delete_account"]
    assert await _offer(monkeypatch, ["open_app", "inventada", "connect_app"], "pro") == ["open_app"]  # ni de sistema
    # un cliente que no declara nada (o manda basura) no recibe ninguna: el agente no promete botones que no existen
    for nothing in (None, [], "open_app", [1, {"id": "open_app"}]):
        assert await _offer(monkeypatch, nothing, "pro") == []


def test_the_model_only_sees_the_offered_actions():
    block = ua.prompt_block(ua.offered(CATALOG, ["open_workflows", "open_app", "connect_app"]))
    assert "open_workflows — Opens the workflows panel." in block and "Params: app (app key)" in block
    assert "connect_app" not in block and "delete_account" not in block
    assert ua.prompt_block(ua.offered(CATALOG, [])) == "" == ua.prompt_block(ua.offered(CATALOG, None))


def test_requests_are_validated_against_what_was_offered():
    offered = ua.offered(CATALOG, ["open_workflows", "open_app"])
    asked = [{"id": "open_app", "params": {"app": "gmail", "inventado": "x"}}, {"id": "open_app"}, {"id": "borrar_todo"},
             {"id": "delete_account"}, {"id": "connect_app"}, "basura", {"id": "open_workflows", "params": None}]
    assert ua.resolve(asked, offered) == [
        {"type": "ui_action", "id": "open_app", "label": "Ver esta app", "params": {"app": "gmail"}, "confirm": False},
        {"type": "ui_action", "id": "open_workflows", "label": "Ver mis workflows", "params": {}, "confirm": False}]
    assert ua.resolve(None, offered) == [] == ua.resolve("open_workflows", offered)


def test_label_follows_the_users_language_and_confirm_travels_to_the_frontend():
    offered = ua.offered(CATALOG, ALL)
    label = lambda lang: ua.resolve([{"id": "open_workflows"}], offered, lang)[0]["label"]  # noqa: E731
    assert (label("English"), label("Spanish"), label("French"), label(None)) == ("See my workflows", *["Ver mis workflows"] * 3)
    assert ua.resolve([{"id": "delete_account"}], offered)[0]["confirm"] is True


def test_requested_actions_reach_the_frontend_and_no_connect_button_is_added_to_them():
    shown = [{"type": "ui_action", "id": "open_workflows", "label": "Ver mis workflows", "params": {}, "confirm": False}]
    needs = [{"source": "auth", "app": "gmail", "needs_auth": True, "status": "error"}]
    assert _build_ui_actions({"requested_ui_actions": shown, "validation_reports": needs}) == shown
    assert [a["type"] for a in _build_ui_actions({"validation_reports": needs})] == ["connect_app"]
    assert _build_ui_actions({}) == []


def test_the_workflow_card_is_sent_only_on_the_turn_that_activates_it():
    from app.agent.shifu_base_v1.graph.state import ShifuOutputState
    done = {"req_workflow_id": "w1", "req_deployed": True, "req_relay": True, "req_deployed_steps": [{"n": 1}],
            "req_trigger_summary": "cada lunes", "req_trigger_type": "schedule"}
    assert [a["type"] for a in _build_ui_actions(done)] == ["render_workflow", "open_trigger"]
    assert _build_ui_actions({**done, "req_relay": False}) == []      # turno posterior: el id sigue en el estado
    assert _build_ui_actions({**done, "req_deployed": False}) == []   # borrador en confirmacion: aun no esta activo
    # ainvoke() solo devuelve los campos de ShifuOutputState: si falta uno, la accion nunca llega al frontend
    assert set(done) <= set(ShifuOutputState.__annotations__)
