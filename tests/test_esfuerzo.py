"""Esfuerzo automático: el tope de llamadas al modelo depende del esfuerzo del mensaje."""
from langgraph.checkpoint.memory import InMemorySaver

from conftest import build_test_agent, tool_call, types, uid


def _bucle(n):
    # el modelo falso pide la calculadora una y otra vez (simula un bucle)
    return [tool_call("calculator", {"expression": "1+1"}, f"call_{i}") for i in range(n)]


def _run(agent, settings, esfuerzo):
    from assistant.agent import stream_events

    payload = {"messages": [{"role": "user", "content": "hola"}]}
    return list(stream_events(agent, payload, uid(), "u1", settings, esfuerzo))


def test_esfuerzo_bajo_corta_en_5_llamadas(make_settings):
    from assistant.packs.i18n.es import LIMIT_MSG

    s = make_settings(model_call_limit=0)
    agent = build_test_agent(_bucle(20), s, checkpointer=InMemorySaver())
    ev = _run(agent, s, "bajo")
    assert ev[0] == {"type": "effort", "level": "bajo", "max_calls": 5, "reasoning": "low", "source": "auto"}
    assert types(ev).count("tool_start") == 5
    assert any(e["type"] == "token" and LIMIT_MSG in e["text"] for e in ev)
    assert ev[-1]["type"] == "done"


def test_esfuerzo_alto_permite_mas_que_recursion_limit_base(make_settings):
    # recursion_limit=25 alcanzaría solo ~5 rondas; con esfuerzo alto se ajusta solo
    s = make_settings(model_call_limit=0, recursion_limit=25)
    agent = build_test_agent(_bucle(12) + ["listo"], s, checkpointer=InMemorySaver())
    ev = _run(agent, s, "alto")
    assert types(ev).count("tool_start") == 12
    assert ev[-1]["type"] == "done"


def test_tope_fijo_ignora_esfuerzo(make_settings):
    s = make_settings(model_call_limit=3)
    agent = build_test_agent(_bucle(10), s, checkpointer=InMemorySaver())
    ev = _run(agent, s, "alto")
    assert "effort" not in types(ev)
    assert types(ev).count("tool_start") == 3
