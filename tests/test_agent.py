from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from conftest import FakeSearch, build_test_agent, run_turn, tool_call, types, uid


def test_stream_emite_tokens_y_done(settings):
    agent = build_test_agent(["Hola, soy tu asistente"], settings, checkpointer=InMemorySaver())
    thread = uid()
    events = run_turn(agent, settings, "hola", thread)

    tokens = [e for e in events if e["type"] == "token"]
    assert tokens
    assert "".join(e["text"] for e in tokens).strip() == "Hola, soy tu asistente"
    assert events[-1] == {"type": "done", "thread_id": thread}
    assert "error" not in types(events)


def test_stream_tool_start_y_tool_end_en_orden(settings):
    agent = build_test_agent(
        [tool_call("calculadora", {"expresion": "2+2"}), "El resultado es 4"],
        settings,
        checkpointer=InMemorySaver(),
    )
    events = run_turn(agent, settings, "cuanto es 2+2", uid())
    t = types(events)

    assert "tool_start" in t and "tool_end" in t
    assert t.index("tool_start") < t.index("tool_end") < t.index("token")
    start = next(e for e in events if e["type"] == "tool_start")
    end = next(e for e in events if e["type"] == "tool_end")
    assert start["id"] == end["id"] == "call_1"
    assert start["name"] == end["name"] == "calculadora"
    assert start["args"] == {"expresion": "2+2"}
    assert end["status"] == "success" and "4" in end["output"]
    assert end.get("engine") is None
    assert t[-1] == "done"


def test_buscar_web_expone_engine_duckduckgo(settings):
    search = FakeSearch(engine="duckduckgo")
    agent = build_test_agent(
        [tool_call("buscar_web", {"consulta": "langgraph"}), "Encontre info"],
        settings,
        checkpointer=InMemorySaver(),
        search_fn=search,
    )
    events = run_turn(agent, settings, "busca langgraph", uid())

    end = next(e for e in events if e["type"] == "tool_end")
    assert end["name"] == "buscar_web"
    assert end["engine"] == "duckduckgo"
    assert search.calls == ["langgraph"]
    assert types(events)[-1] == "done"


def test_hitl_interrupt_y_resume(hitl_settings):
    settings = hitl_settings
    agent = build_test_agent(
        [
            tool_call("enviar_email_simulado",
                      {"destinatario": "a@b.com", "asunto": "Hola", "cuerpo": "Texto"}),
            "Listo, email enviado",
        ],
        settings,
        checkpointer=InMemorySaver(),
    )
    thread = uid()
    events = run_turn(agent, settings, "manda un email a a@b.com", thread)

    interrupts = [e for e in events if e["type"] == "interrupt"]
    assert len(interrupts) == 1
    assert interrupts[0]["action_requests"][0]["name"] == "enviar_email_simulado"
    assert "tool_end" not in types(events)  # la herramienta aun no se ejecuto

    from assistant.agent import stream_events

    resumed = list(stream_events(
        agent, Command(resume={"decisions": [{"type": "approve"}]}), thread, "u1", settings
    ))
    t = types(resumed)
    assert "tool_end" in t and "done" in t
    assert t.index("tool_end") < t.index("done")
    assert next(e for e in resumed if e["type"] == "tool_end")["name"] == "enviar_email_simulado"
