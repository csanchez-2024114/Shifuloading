"""Un perfil externo (tests/profiles/minimal, cargado por ruta con puntos) con herramienta y prompt propios funciona
sin tocar core/. Modelos falsos, sin red ni Mongo."""
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conftest import FakeSearch, _settings, fake_llm, run_turn, tool_call, uid

CORE = Path(__file__).resolve().parents[1] / "src" / "assistant" / "core"


@pytest.fixture
def minimal(monkeypatch):
    from assistant.core.profile import load_profile

    monkeypatch.setenv("AGENT_PROFILE", "profiles.minimal")
    return load_profile()


def test_minimo_responde_con_su_herramienta_y_su_prompt(minimal):
    from assistant.core.agent import build_agent, system_prompt_text
    from assistant.core.tools import build_tools

    settings = _settings(enable_hitl_demo=True)
    llm = fake_llm(tool_call("word_count", {"text": "uno dos tres"}), "Son tres palabras")
    tools = build_tools(llm, settings, search_fn=FakeSearch())
    assert [t.name for t in tools] == ["word_count"]
    assert system_prompt_text(settings, minimal).startswith("You are Minimal, a test assistant.")

    agent = build_agent(llm, tools, settings, checkpointer=InMemorySaver())
    thread = uid("min")
    ev = run_turn(agent, settings, "cuenta las palabras de: uno dos tres", thread)
    fin = next(e for e in ev if e["type"] == "tool_end")
    assert fin["name"] == "word_count" and fin["output"] == "3 words." and fin["status"] == "success"
    assert "".join(e["text"] for e in ev if e["type"] == "token").strip() == "Son tres palabras"
    assert ev[-1] == {"type": "done", "thread_id": thread}


def test_minimo_hereda_la_base_de_textos_con_una_propia(minimal):
    from assistant.core.i18n import tr
    from assistant.packs.i18n import es

    assert tr("http.thread_not_found") == "No encontré esa conversación."  # la propia, del perfil activo
    assert tr("agent.cut_note", minimal) == es.CUT_NOTE  # el resto, de la base
    assert minimal.intents.continue_request.pattern == "(?!)"  # sin reglas de intención: el default neutro


def test_minimo_no_toca_el_nucleo():
    for path in CORE.rglob("*.py"):
        texto = path.read_text(encoding="utf-8-sig")
        assert "minimal" not in texto and "word_count" not in texto, path
