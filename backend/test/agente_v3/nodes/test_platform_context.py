"""platform_context: el agente guia con las apps y funciones reales (y las funciones se buscan, no se inyectan todas)."""
from unittest.mock import AsyncMock

from app.agent.shared.helpers import platform_context as pc

_CATALOG = [
    {"name": "Gmail", "nameApi": "gmail", "category": "Google Suite"},
    {"name": "Asana", "nameApi": "asana", "category": "Project Management"},
]


def _fn(fid, verb, desc):
    return (fid, verb, desc, pc._terms(fid.replace(".", " ") + " " + desc))


def _use(monkeypatch, catalog, functions):
    monkeypatch.setattr(pc, "_catalog", AsyncMock(return_value=catalog))
    monkeypatch.setattr(pc, "_functions", lambda: functions)


async def test_lists_apps_marks_connected_and_adds_only_relevant_functions(monkeypatch):
    _use(monkeypatch, _CATALOG, [
        _fn("asana.tasks.create", "write", "Creates a task inside an Asana project"),
        _fn("salesforce.leads.list", "read", "Lists CRM leads from Salesforce"),
    ])
    state = {"user_connected_apps": {"gmail": ["a@b.c"]}, "messages": [],
             "structured_prompt": "I want to create tasks in Asana whenever a customer email arrives"}
    ctx = await pc.build_platform_context(state)
    assert "Gmail*" in ctx and "Asana*" not in ctx   # solo la conectada va marcada
    assert "enviar_correo" not in ctx                # v0.8.0: las acciones del sistema viejo (BigTools) ya no se ofrecen
    assert "asana.tasks.create" in ctx
    assert "salesforce.leads.list" not in ctx        # lo irrelevante no entra al prompt


async def test_function_search_needs_real_overlap_with_the_request(monkeypatch):
    _use(monkeypatch, _CATALOG, [_fn("asana.tasks.create", "write", "Creates a task inside an Asana project")])
    ctx = await pc.build_platform_context({"messages": [], "structured_prompt": "tell me a joke about penguins"})
    assert "asana.tasks.create" not in ctx


async def test_empty_platform_returns_empty_string(monkeypatch):
    _use(monkeypatch, [], [])
    assert await pc.build_platform_context({"messages": []}) == ""


async def test_says_what_a_mentioned_app_cannot_do(monkeypatch):
    # Instagram solo tiene lectura de perfil: el agente no debe prometer publicar (paso en una prueba real)
    catalog = _CATALOG + [{"name": "Instagram", "nameApi": "instagram", "category": "Social Media"}]
    _use(monkeypatch, catalog, [_fn("instagram.user.get", "read", "Returns the connected Instagram professional account")])
    ctx = await pc.build_platform_context({"messages": [], "structured_prompt": "post on my Instagram when new clothes arrive"})
    assert "Instagram: 1 read function(s)" in ctx and "NO write functions" in ctx
    assert "cannot post" in ctx


async def test_app_without_any_action_is_marked_connection_only(monkeypatch):
    catalog = _CATALOG + [{"name": "Trello", "nameApi": "trello", "category": "Project Management"}]
    _use(monkeypatch, catalog, [])
    ctx = await pc.build_platform_context({"messages": [], "structured_prompt": "move cards in Trello"})
    assert "- Trello: coming soon" in ctx
    assert "Trello (coming soon)" in ctx  # en la lista: el agente no la sugiere como alternativa
    assert set(pc.unavailable_apps(ctx)) == {"trello"}  # el juez lee de vuelta estas lineas: constructor y lector en sincronia


def test_catalog_key_and_legacy_key_find_the_same_actions():
    from app.agent.shared.helpers.bigtools_registry import registry_tools
    assert registry_tools("google_sheets") == registry_tools("sheets") != []
    assert registry_tools("shopify") == []


async def test_an_app_that_does_not_exist_stays_a_fact_for_the_whole_automation_flow(monkeypatch):
    # Turno 3 del flujo: el usuario ya no nombra Shopify, pero la automatizacion depende de ella (escenario 2, 2026-10-10)
    _use(monkeypatch, _CATALOG, [_fn("gmail.messages.send", "create", "Sends an email")])
    state = {"messages": [], "structured_prompt": "Ya conecté gmail", "req_level": 1, "req_apps_scope": ["shopify", "gmail"]}
    ctx = await pc.build_platform_context(state)
    assert "shopify: not integrated yet" in ctx and "may be possible later" in ctx
    assert "shopify" in pc.unavailable_apps(ctx) and "gmail" not in pc.unavailable_apps(ctx)
    ended = await pc.build_platform_context({**state, "req_level": None})
    assert "shopify" not in ended  # fuera del flujo, el alcance viejo ya no cuenta


def test_app_capability_comes_from_the_registry(monkeypatch):
    monkeypatch.setattr(pc, "_functions", lambda: [("discord.messages.list", "read", "", set()),
                                                   ("asana.tasks.create", "create", "", set()),
                                                   ("google_sheets.values.append", "update", "", set())])
    assert pc.app_capability("Discord") == "read"
    assert pc.app_capability("asana") == "write"
    assert pc.app_capability("Google Sheets") == "write"   # nombre visible -> nameApi
    assert pc.app_capability("Google Docs") == "none"       # solo tenia acciones en el sistema viejo (BigTools), que ya no cuenta
    assert pc.app_capability("Shopify") == "none"
