"""trace_log: el registro completo de cada turno (para auditar a cada mini agente) no debe perder datos ni romper un turno."""
import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.core import trace_log
from app.routes.chat.chat import _ChatStreamer


def _read(folder):
    files = list(folder.glob("*.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_disabled_by_default_and_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.delenv("SHIFU_TRACE_LOG", raising=False)
    monkeypatch.setenv("SHIFU_TRACE_DIR", str(tmp_path))
    assert trace_log.new_turn({"x": 1}) is None
    assert list(tmp_path.iterdir()) == []


def test_a_finished_turn_is_one_json_line_with_header_events_and_final_data(monkeypatch, tmp_path):
    monkeypatch.setenv("SHIFU_TRACE_LOG", "1")
    monkeypatch.setenv("SHIFU_TRACE_DIR", str(tmp_path))
    t = trace_log.new_turn({"conversation_id": "c1", "user_text": "hola"})
    t.event("node", node="semantic_intake")
    t.finish(reply="ok", error=None)
    t.finish(reply="se ignora: ya cerrado")          # cerrar dos veces no duplica la linea
    [rec] = _read(tmp_path)
    assert rec["conversation_id"] == "c1" and rec["reply"] == "ok" and rec["events"][0]["node"] == "semantic_intake"
    assert "ts" in rec and "total_ms" in rec


def test_an_unwritable_folder_never_breaks_the_turn(monkeypatch, tmp_path):
    blocker = tmp_path / "es_un_archivo"
    blocker.write_text("x")
    monkeypatch.setenv("SHIFU_TRACE_LOG", "1")
    monkeypatch.setenv("SHIFU_TRACE_DIR", str(blocker / "dentro"))   # no se puede crear una carpeta dentro de un archivo
    trace_log.new_turn({"a": 1}).finish(reply="x")                    # no debe lanzar


async def test_streamer_logs_full_prompt_output_tags_usage_and_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("SHIFU_TRACE_LOG", "1")
    monkeypatch.setenv("SHIFU_TRACE_DIR", str(tmp_path))
    turn = trace_log.new_turn({"conversation_id": "c2"})
    s = _ChatStreamer(asyncio.Queue(), turn_log=turn)

    msgs = [[HumanMessage("pregunta completa del usuario")]]
    await s.on_chat_model_start({}, msgs, run_id="r1", metadata={"langgraph_node": "response_evaluator"},
                                tags=["judge:persona"], invocation_params={"model_name": "gpt-4o-mini", "temperature": 0})
    ai = AIMessage(content="", tool_calls=[{"name": "_One", "args": {"note": "n", "severity": "minor", "feedback": ""}, "id": "1"}],
                   usage_metadata={"input_tokens": 1000, "output_tokens": 50, "total_tokens": 1050})
    await s.on_llm_end(LLMResult(generations=[[ChatGeneration(message=ai)]]), run_id="r1")

    await s.on_chat_model_start({}, msgs, run_id="r2", metadata={"langgraph_node": "responder"}, invocation_params={"model_name": "gpt-4o-mini"})
    await s.on_llm_error(RuntimeError("429 sin credito"), run_id="r2")
    turn.finish(reply="x")

    [rec] = _read(tmp_path)
    ok, bad = [e for e in rec["events"] if e["kind"] == "llm"]
    assert ok["tags"] == ["judge:persona"] and ok["model"] == "gpt-4o-mini" and ok["node"] == "response_evaluator"
    assert ok["messages"] == [{"role": "human", "content": "pregunta completa del usuario"}]   # el prompt completo, sin recortar
    assert ok["structured_output"] == [{"note": "n", "severity": "minor", "feedback": ""}]       # lo que respondio el mini agente
    assert ok["usage"]["input"] == 1000 and ok["usage"]["usd"] > 0
    assert bad["node"] == "responder" and "429 sin credito" in bad["error"]                      # los fallos tambien quedan


async def test_node_outputs_and_retries_are_recorded(monkeypatch, tmp_path):
    monkeypatch.setenv("SHIFU_TRACE_LOG", "1")
    monkeypatch.setenv("SHIFU_TRACE_DIR", str(tmp_path))
    turn = trace_log.new_turn({})
    s = _ChatStreamer(asyncio.Queue(), turn_log=turn)
    for i in (1, 2):   # dos pasadas del responder = un reintento
        await s.on_chain_start({}, {}, metadata={"langgraph_node": "responder"}, name="responder", run_id=f"n{i}")
        await s.on_chain_end({"mood_state": "HELPFUL"}, run_id=f"n{i}")
    turn.finish()
    assert [e["kind"] for e in _read(tmp_path)[0]["events"]] == ["node", "retry_reset", "node"]


async def test_a_json_verdict_returned_as_text_is_stored_already_parsed(monkeypatch, tmp_path):
    # los jueces devuelven su veredicto como JSON en el texto (no como tool_call): el registro debe poder leerse/filtrarse sin reparsear
    monkeypatch.setenv("SHIFU_TRACE_LOG", "1")
    monkeypatch.setenv("SHIFU_TRACE_DIR", str(tmp_path))
    turn = trace_log.new_turn({})
    s = _ChatStreamer(asyncio.Queue(), turn_log=turn)
    await s.on_chat_model_start({}, [[HumanMessage("x")]], run_id="j", metadata={"langgraph_node": "response_evaluator"}, tags=["judge:persona"])
    text = '{"note":"n","severity":"major","feedback":"f"}'
    await s.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content=text), text=text)]]), run_id="j")
    turn.finish()
    [llm] = [e for e in _read(tmp_path)[0]["events"] if e["kind"] == "llm"]
    assert llm["structured_output"] == [{"note": "n", "severity": "major", "feedback": "f"}]


def test_dev_tools_are_off_unless_explicitly_enabled(monkeypatch):
    # un usuario real no debe poder pedir los prompts del sistema (trace) ni encontrar la interfaz de pruebas
    from app.routes.chat.chat import dev_ui_enabled
    monkeypatch.delenv("SHIFU_DEV_UI", raising=False)
    assert dev_ui_enabled() is False
    monkeypatch.setenv("SHIFU_DEV_UI", "0")
    assert dev_ui_enabled() is False
    monkeypatch.setenv("SHIFU_DEV_UI", "1")
    assert dev_ui_enabled() is True
