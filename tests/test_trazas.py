"""TRACE_METADATA: run_id por turno, metadatos en la traza (sin contenido de mensajes) y evento SSE "run". Con el
default (0) nada cambia. Sin tokens: modelo falso."""
import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from conftest import _settings, build_test_agent, run_turn, tool_call, types, uid


def _capturing(agent):
    """Guarda la config con la que stream_events llama al grafo en cada turno."""
    seen = []
    original = agent.stream

    def stream(payload, config=None, **kwargs):
        seen.append(config)
        return original(payload, config=config, **kwargs)

    agent.stream = stream
    return seen


def test_apagado_no_hay_evento_run_ni_run_id():
    s = _settings()
    agent = build_test_agent(["hola"], s, checkpointer=InMemorySaver())
    seen = _capturing(agent)
    ev = run_turn(agent, s, "hola", uid())
    assert "run" not in types(ev)
    assert "run_id" not in seen[0] and "metadata" not in seen[0]


def test_run_id_y_metadatos_sin_contenido():
    s = _settings(trace_metadata=True)
    agent = build_test_agent(["Respuesta secreta 123"], s, checkpointer=InMemorySaver())
    seen = _capturing(agent)
    thread = uid()
    ev = run_turn(agent, s, "mi dato privado es 4242", thread, user_id="ana")
    assert ev[0]["type"] == "run" and ev[-1]["type"] == "done"
    run_id = uuid.UUID(ev[0]["run_id"])
    cfg = seen[0]
    assert cfg["run_id"] == run_id and cfg["run_name"] == "agent_turn"
    meta = cfg["metadata"]
    assert meta["thread_id"] == thread and meta["user_id"] == "ana" and meta["turn_kind"] == "chat"
    assert meta["model"] == s.llm_model and meta["profile"] == "default" and len(meta["prompt_sha256"]) == 16
    assert not any("4242" in str(v) or "secreta" in str(v) for v in meta.values())  # sin contenido de mensajes
    assert "agent_turn" in cfg["tags"]


def test_el_sha_del_prompt_es_estable_y_cada_turno_tiene_su_run_id():
    s = _settings(trace_metadata=True, enable_hitl_demo=True)
    agent = build_test_agent(
        ["uno", tool_call("send_simulated_email", {"recipient": "a@b.c", "subject": "s", "body": "b"}), "Enviado."],
        s, checkpointer=InMemorySaver())
    seen = _capturing(agent)
    thread = uid()
    a = run_turn(agent, s, "hola", thread)
    b = run_turn(agent, s, "manda un correo", thread)
    assert "interrupt" in types(b)
    from assistant.core.agent import stream_events

    c = list(stream_events(agent, Command(resume={"decisions": [{"type": "approve"}]}), thread, "u1", s))
    ids = [a[0]["run_id"], b[0]["run_id"], c[0]["run_id"]]
    assert len(set(ids)) == 3 and c[0]["type"] == "run"
    assert seen[2]["metadata"]["turn_kind"] == "resume"
    assert len({cfg["metadata"]["prompt_sha256"] for cfg in seen}) == 1  # la fecha no cuenta


def test_prompt_sha_ignora_la_fecha():
    from assistant.core.tracing import prompt_sha256

    base = "## Rules\n- be nice\n\nUser's current local date and time: Saturday 2026-10-17 10:00 (UTC-0600)."
    otro = base.replace("Saturday 2026-10-17 10:00", "Sunday 2026-10-18 23:59")
    assert prompt_sha256(base) == prompt_sha256(otro) != prompt_sha256(base.replace("nice", "brief"))
