"""B1 de la prueba larga (docs/PRUEBA_USUARIO_LARGA.md): un recuerdo no guardado o no actualizado, o un "Error: …"
devuelto como texto, salían con status "success" y la UI les ponía "✓". Ahora son "skipped", en vivo y al recargar.
Sin tokens: modelos falsos."""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import _settings, build_test_agent, run_turn, tool_call, uid


def _status(events, name):
    return [e["status"] for e in events if e["type"] == "tool_end" and e["name"] == name]


def test_recuerdo_no_guardado_ni_actualizado_y_error_no_llevan_check():
    from assistant.core.agent import get_history

    s = _settings(memory_require_quote=True)
    agent = build_test_agent([
        tool_call("save_memory", {"text": "Es médico", "evidence": "soy médico"}, "g1"),  # nunca lo dijo
        tool_call("update_memory", {"id": "no-existe", "text": "Vive en Puebla", "evidence": "vivo en Puebla"}, "u1"),
        tool_call("calculator", {"expression": "__import__('os')"}, "c1"),
        tool_call("check_python_syntax", {"code": "def f(:\n  pass"}, "p1"),
        "Listo."], s, checkpointer=InMemorySaver(), store=InMemoryStore())
    thread = uid()
    ev = run_turn(agent, s, "hola, ¿qué tal?", thread)
    outputs = {e["name"]: e["output"] for e in ev if e["type"] == "tool_end"}
    assert outputs["save_memory"].startswith("Not saved:") and _status(ev, "save_memory") == ["skipped"]
    assert outputs["update_memory"].startswith("Not updated:") and _status(ev, "update_memory") == ["skipped"]
    assert outputs["calculator"].startswith("Error:") and _status(ev, "calculator") == ["skipped"]
    # un error de sintaxis es el resultado de la herramienta: sí corrió
    assert outputs["check_python_syntax"].startswith("SyntaxError") and _status(ev, "check_python_syntax") == ["success"]

    tools = {m["name"]: m.get("status") for m in get_history(agent, thread, s) if m["role"] == "tool"}
    assert tools["save_memory"] == tools["update_memory"] == tools["calculator"] == "skipped"
    assert tools.get("check_python_syntax") in (None, "success")


def test_lo_que_si_se_hizo_sigue_con_check():
    s = _settings()
    agent = build_test_agent([
        tool_call("save_memory", {"text": "Le gusta el té", "evidence": "me gusta el té"}, "g1"),
        tool_call("calculator", {"expression": "2+2"}, "c1"), "Listo."], s, checkpointer=InMemorySaver(),
        store=InMemoryStore())
    ev = run_turn(agent, s, "me gusta el té, recuérdalo", uid())
    assert _status(ev, "save_memory") == ["success"] and _status(ev, "calculator") == ["success"]
