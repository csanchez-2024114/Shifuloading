"""Endurecimiento de feat/seguridad-core (P2-P4 y S1/S5 de docs/AUDITORIA_AGENTE.md). Cada interruptor que cambia lo
que ve o hace el agente va apagado por defecto; aquí se prueba encendido. Modelos falsos, sin red."""
import time

from langgraph.checkpoint.memory import InMemorySaver

from conftest import FakeChat, FakeSearch, _settings, run_turn, tool_call, uid


class Lento(FakeChat):
    """Cada llamada al modelo tarda `delay` segundos."""
    delay: float = 0.0

    def _stream(self, *args, **kwargs):
        time.sleep(self.delay)
        yield from super()._stream(*args, **kwargs)


def _agente(settings, llm, search=None):
    from assistant.core.agent import build_agent
    from assistant.core.tools import build_tools

    return build_agent(llm, build_tools(llm, settings, search_fn=search or FakeSearch()), settings,
                       checkpointer=InMemorySaver())


# --------------------------------------------------------------------------- TURN_MAX_SECONDS


def test_turn_max_seconds_apagado_por_defecto():
    assert _settings().turn_max_seconds == 0


def test_turn_max_seconds_cierra_en_la_frontera_de_paso_y_deja_el_hilo_usable():
    from assistant.core.agent import get_history, turn_time_msg

    s = _settings(turn_max_seconds=0.05, turn_token_cap=0)
    respuestas = [tool_call("calculator", {"expression": f"{i}+1"}, f"c{i}") for i in range(5)] + ["fin"]
    llm = Lento(messages=iter(respuestas), delay=0.06)
    agent = _agente(s, llm)
    thread = uid("tiempo")
    ev = run_turn(agent, s, "calcula mucho", thread)
    texto = "".join(e["text"] for e in ev if e["type"] == "token")
    assert turn_time_msg(0.05) in texto and "TURN_MAX_SECONDS" in texto and ev[-1]["type"] == "done"
    assert sum(e["type"] == "tool_start" for e in ev) <= 1  # no siguió llamando al modelo
    state = agent.get_state({"configurable": {"thread_id": thread}}).values["messages"]
    llamadas = {c["id"] for m in state if m.type == "ai" for c in m.tool_calls}
    assert llamadas <= {m.tool_call_id for m in state if m.type == "tool"}  # ninguna llamada colgando
    assert get_history(agent, thread, s)[-1]["content"] == turn_time_msg(0.05).strip()

    llm.delay, llm.messages = 0.0, iter(["otra respuesta"])
    ev2 = run_turn(agent, _settings(turn_max_seconds=0), "hola de nuevo", thread)
    assert ev2[-1]["type"] == "done" and "otra respuesta" in "".join(e.get("text", "") for e in ev2)


def test_turn_max_seconds_no_corta_una_respuesta_final_en_curso():
    s = _settings(turn_max_seconds=0.05, turn_token_cap=0)
    llm = Lento(messages=iter(["respuesta final completa"]), delay=0.08)
    ev = run_turn(_agente(s, llm), s, "hola", uid("tiempo"))
    texto = "".join(e["text"] for e in ev if e["type"] == "token")
    assert texto.strip() == "respuesta final completa" and ev[-1]["type"] == "done"
