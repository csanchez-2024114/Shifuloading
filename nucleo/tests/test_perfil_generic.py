"""Prueba de pivote: el perfil `generic` (AGENT_PROFILE=generic) arranca y responde con modelos falsos, recorre una
herramienta y una aprobación (tarjeta de deep_research) por HTTP, sin tocar core/. Sin red ni Mongo."""
import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from conftest import FakeSearch, _settings, fake_llm, tool_call, uid

HERRAMIENTAS = ["web_search", "calculator", "current_datetime", "save_memory", "search_memories", "update_memory",
                "deep_research"]


@pytest.fixture
def generic(monkeypatch):
    from assistant.core.profile import load_profile

    monkeypatch.setenv("AGENT_PROFILE", "generic")  # la tarjeta de deep_research lee las reglas del perfil activo
    return load_profile()


def _sse(response):
    return [json.loads(b.strip()[len("data: "):]) for b in response.text.split("\n\n") if b.strip()]


def test_generic_carga_con_sus_piezas(generic):
    from assistant.core.agent import evidence_tools, system_prompt_text
    from assistant.packs import ui
    from assistant.packs.lang import es_en

    assert generic.name == "generic" and generic.static_dir == ui.STATIC_DIR
    assert generic.intents is es_en.INTENTS and generic.lexicon is es_en.LEXICON  # de packs/, no vacíos
    assert system_prompt_text(_settings(), generic).startswith("You are a general-purpose conversational assistant.")
    assert evidence_tools(generic) == ("web_search", "deep_research")
    assert [n for n, p in generic.tool_policies.items() if p.approval] == ["deep_research"]


def test_generic_herramientas_sin_sintaxis_ni_email(generic):
    from assistant.core.tools import build_tools

    for settings in (_settings(), _settings(enable_hitl_demo=True)):
        assert [t.name for t in build_tools(fake_llm("x"), settings, search_fn=FakeSearch())] == HERRAMIENTAS


def test_generic_arranca_responde_herramienta_y_aprobacion(generic):
    from assistant.core import server
    from assistant.core.agent import build_agent
    from assistant.core.tools import build_tools

    settings = _settings()
    llm = fake_llm(
        tool_call("calculator", {"expression": "6*7"}),          # turno 1: una herramienta
        "Son 42",
        tool_call("deep_research", {"task": "A frente a B"}, "call_inv"),  # turno 2: pide la tarjeta
        "RESUMEN del investigador",                                # subagente, tras aprobar
        "Respuesta final",
    )
    agent = build_agent(llm, build_tools(llm, settings, search_fn=FakeSearch()), settings,
                        checkpointer=InMemorySaver())
    app = server.create_app(agent=agent, settings=settings)
    assert app.title == "Asistente genérico"
    with TestClient(app) as c:
        index = c.get("/")
        assert index.status_code == 200 and index.content == (generic.static_dir / "index.html").read_bytes()

        thread = uid("gen")
        ev = _sse(c.post("/chat", json={"message": "cuánto es 6*7", "thread_id": thread}))
        fin = next(e for e in ev if e["type"] == "tool_end")
        assert fin["name"] == "calculator" and fin["status"] == "success" and "42" in fin["output"]
        assert "".join(e["text"] for e in ev if e["type"] == "token").strip() == "Son 42"
        assert ev[-1] == {"type": "done", "thread_id": thread}

        # "estudio" no es pedir investigar de forma explícita: sale la tarjeta y la herramienta no corre
        ev = _sse(c.post("/chat", json={"message": "hazme un estudio de A frente a B", "thread_id": thread}))
        tarjeta = next(e for e in ev if e["type"] == "interrupt")
        assert tarjeta["action_requests"][0]["name"] == "deep_research"
        assert not any(e["type"] == "tool_end" for e in ev)

        ev = _sse(c.post("/resume", json={"thread_id": thread, "decisions": [{"type": "approve"}]}))
        fin = next(e for e in ev if e["type"] == "tool_end")
        assert fin["name"] == "deep_research" and "RESUMEN del investigador" in fin["output"]
        assert "Respuesta final" in "".join(e["text"] for e in ev if e["type"] == "token")
        assert ev[-1]["type"] == "done"


def test_perfil_inexistente_lista_los_disponibles(monkeypatch):
    from assistant.core.config import ConfigError
    from assistant.core.profile import load_profile

    monkeypatch.setenv("AGENT_PROFILE", "no_existe")
    with pytest.raises(ConfigError) as exc:
        load_profile()
    assert str(exc.value) == ("No existe el perfil 'no_existe' (AGENT_PROFILE). Perfiles disponibles: coder, "
                              "default, generic.")
