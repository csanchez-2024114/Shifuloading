"""Escrituras en el hilo con el checkpointer REAL de MongoDB (base `assistant_test`) y modelos falsos.
InMemorySaver no tiene el índice único de `checkpoint_writes` (thread, ns, checkpoint, task_id, idx): un mensaje
abortado por TURN_TOKEN_CAP justo después de que el modelo pidiera herramientas guardaba su cierre con E11000 y el
hilo perdía la llamada, las cancelaciones y el aviso. Aquí: aborto en cada momento, la rama en que el cierre no se
puede guardar, y los demás flujos que reescriben mensajes (corrección, corte, resumen, HITL, bigtool)."""
import logging
import time

from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from conftest import FakeChat, MONGO_URI, TEST_DB, fake_llm, run_turn, tool_call, uid
from test_memoria_avanzada import FILLER, _agent, recorder
from test_mejoras import ConUso, Cortado, CortadoPrimero, SearchConUso


class Visto(ConUso):
    """ConUso (30k tokens por llamada) que además guarda los mensajes de cada llamada."""
    vistos: list = []

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.vistos.append(list(messages))
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


class VistoSinUso(FakeChat):
    vistos: list = []

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.vistos.append(list(messages))
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


@tool("slow_tool")
def lenta(x: str) -> str:
    """Slow test tool."""
    time.sleep(1.5)
    return "slow result"


def _agente(s, llm, search, checkpointer, extra=()):
    from assistant.agent import build_agent
    from assistant.tools import build_tools
    return build_agent(llm, [*build_tools(llm, s, search_fn=search), *extra], s, checkpointer=checkpointer)


def _guardados(thread):
    """Mensajes del último checkpoint GUARDADO, leídos con un saver nuevo (como tras reiniciar el servidor)."""
    from assistant import memory
    saver = memory.build_checkpointer(memory.ping_mongo(MONGO_URI), TEST_DB)
    return saver.get_tuple({"configurable": {"thread_id": thread}}).checkpoint["channel_values"]["messages"]


def _sin_huerfanos(messages):
    llamadas = [c["id"] for m in messages if m.type == "ai" for c in m.tool_calls]
    respuestas = [m.tool_call_id for m in messages if m.type == "tool"]
    assert sorted(llamadas) == sorted(respuestas), (llamadas, respuestas)  # cada llamada con una sola respuesta


def _cerrado(thread, cap, cancelados, terminados=()):
    """El hilo guardado termina con las llamadas canceladas, las terminadas intactas y el aviso."""
    from assistant.agent import CANCELLED_TOOL_MSG, TURN_CAP_MSG
    msgs = _guardados(thread)
    _sin_huerfanos(msgs)
    tools = {m.tool_call_id: m.content for m in msgs if m.type == "tool"}
    assert {k for k, v in tools.items() if v == CANCELLED_TOOL_MSG} == set(cancelados)
    assert all(tools[k] != CANCELLED_TOOL_MSG for k in terminados)
    assert msgs[-1].type == "ai" and msgs[-1].content == TURN_CAP_MSG.format(cap=cap).strip()
    return msgs


def _sigue_usable(agent, llm, make_settings, thread, extra_settings=None):
    llm.messages = iter(["otra respuesta"])
    s2 = make_settings(turn_token_cap=0, model_call_limit=15, **(extra_settings or {}))
    ev = run_turn(agent, s2, "hola de nuevo", thread)
    assert ev[-1]["type"] == "done" and "error" not in [e["type"] for e in ev]
    assert "otra respuesta" in "".join(e.get("text", "") for e in ev)
    _sin_huerfanos(llm.vistos[-1])  # el modelo no recibe llamadas sin respuesta (la API real lo rechazaría)
    _sin_huerfanos(_guardados(thread))


def _sin_error_de_cierre(caplog):
    assert not [r for r in caplog.records if "NO se guardó su cierre" in r.getMessage()]


def test_aborto_justo_tras_pedir_herramientas(make_settings, mongo_checkpointer, caplog):
    # 30k por llamada ≥ tope de 20k: se aborta en cuanto el nodo model registra la respuesta con las llamadas.
    # Antes del arreglo: E11000 en checkpoint_writes y el cierre no se guardaba.
    s = make_settings(turn_token_cap=20000, model_call_limit=15)
    pedido = AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "1+1"}, "id": "c1"},
                                               {"name": "current_datetime", "args": {}, "id": "d1"}])
    llm = Visto(messages=iter([pedido]), vistos=[])
    agent = _agente(s, llm, SearchConUso(), mongo_checkpointer)
    thread = uid()
    ev = run_turn(agent, s, "calcula y dime la hora", thread)
    assert "tool_start" not in [e["type"] for e in ev] and ev[-1]["type"] == "done"
    _sin_error_de_cierre(caplog)
    _cerrado(thread, 20000, cancelados={"c1", "d1"})
    _sigue_usable(agent, llm, make_settings, thread)


def test_aborto_con_herramientas_a_medio_ejecutar(make_settings, mongo_checkpointer, caplog):
    # la búsqueda (30k) termina y pasa el tope mientras slow_tool sigue corriendo. Al cerrar el stream, LangGraph
    # espera a las herramientas que ya están corriendo: su resultado real se guarda (no queda como cancelada)
    s = make_settings(turn_token_cap=20000, model_call_limit=15)
    pedido = AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "rapida"}, "id": "w1"},
                                               {"name": "slow_tool", "args": {"x": "y"}, "id": "l1"}])
    llm = VistoSinUso(messages=iter([pedido]), vistos=[])
    agent = _agente(s, llm, SearchConUso(30000), mongo_checkpointer, extra=[lenta])
    thread = uid()
    ev = run_turn(agent, s, "busca y espera", thread)
    # el aborto llega con el resultado de la búsqueda (instantánea), mientras slow_tool duerme 1.5 s
    assert "tool_end" not in [e["type"] for e in ev] and ev[-1]["type"] == "done"
    _sin_error_de_cierre(caplog)
    msgs = _cerrado(thread, 20000, cancelados=set(), terminados={"w1", "l1"})
    assert {m.tool_call_id: m.content for m in msgs if m.type == "tool"}["l1"] == "slow result"
    time.sleep(2)
    _cerrado(thread, 20000, cancelados=set(), terminados={"w1", "l1"})  # nada llega tarde a ensuciar el hilo
    _sigue_usable(agent, llm, make_settings, thread)


def test_aborto_dentro_del_investigador(make_settings, mongo_checkpointer, caplog):
    # agente e investigador comparten el modelo falso; la primera búsqueda del investigador (30k) pasa el tope y el
    # aviso de avance de la segunda llega mientras deep_research sigue corriendo. El investigador ve el tope, se
    # detiene y devuelve lo que encontró: ese resultado parcial queda guardado como respuesta de deep_research
    s = make_settings(turn_token_cap=20000, model_call_limit=15, investigator_token_budget=0)
    llm = VistoSinUso(messages=iter([
        tool_call("deep_research", {"task": "compara A y B"}, "inv"),
        tool_call("web_search", {"query": "q0"}, "s0"), tool_call("web_search", {"query": "q1"}, "s1"),
        "RESUMEN"]), vistos=[])
    search = SearchConUso(30000)
    agent = _agente(s, llm, search, mongo_checkpointer)
    thread = uid()
    ev = run_turn(agent, s, "investiga A vs B", thread)
    assert search.calls == ["q0"] and "tool_end" not in [e["type"] for e in ev]
    _sin_error_de_cierre(caplog)
    msgs = _cerrado(thread, 20000, cancelados=set(), terminados={"inv"})
    assert "Research stopped" in [m for m in msgs if m.type == "tool"][0].content
    _sigue_usable(agent, llm, make_settings, thread)


class BigVisto(Visto):
    def bind_tools(self, tools, **kwargs):
        return self


def test_aborto_en_bigtool(make_settings, mongo_checkpointer, caplog):
    from assistant.bigtool_agent import build_bigtool_agent

    s = make_settings(use_bigtool=True, turn_token_cap=20000, model_call_limit=15)
    llm = BigVisto(messages=iter([tool_call("calculator", {"expression": "2+2"}, "c1")]), vistos=[])
    agent = build_bigtool_agent(llm, s, checkpointer=mongo_checkpointer, memories_store=InMemoryStore(),
                                embeddings=DeterministicFakeEmbedding(size=64), search_fn=SearchConUso())
    thread = uid()
    run_turn(agent, s, "suma", thread)
    _sin_error_de_cierre(caplog)
    _cerrado(thread, 20000, cancelados={"c1"})
    _sigue_usable(agent, llm, make_settings, thread, {"use_bigtool": True})


def test_si_el_cierre_no_se_guarda_avisa_registra_y_el_hilo_sigue(make_settings, mongo_checkpointer, caplog,
                                                                   monkeypatch):
    from assistant.agent import TURN_CAP_MSG

    s = make_settings(turn_token_cap=20000, model_call_limit=15)
    llm = Visto(messages=iter([tool_call("calculator", {"expression": "1+1"}, "c1")]), vistos=[])
    agent = _agente(s, llm, SearchConUso(), mongo_checkpointer)

    def falla(*a, **k):
        raise RuntimeError("Mongo no disponible")

    monkeypatch.setattr(agent, "update_state", falla)
    thread = uid()
    with caplog.at_level(logging.ERROR, logger="assistant.agent"):
        ev = run_turn(agent, s, "calcula", thread)
    texto = "".join(e["text"] for e in ev if e["type"] == "token")
    assert TURN_CAP_MSG.format(cap=20000) in texto and ev[-1]["type"] == "done"  # el usuario recibe el aviso
    [r] = [r for r in caplog.records if "NO se guardó su cierre" in r.getMessage()]
    assert thread in r.getMessage() and "1 llamada(s)" in r.getMessage() and "Mongo no disponible" in r.exc_text
    monkeypatch.undo()
    _sigue_usable(agent, llm, make_settings, thread)  # parte del último checkpoint: sin la llamada colgando


# --------------------------------------------------------------------------- otros flujos que reescriben mensajes


def test_correccion_de_answer_verify_con_mismo_id_en_mongo(make_settings, mongo_checkpointer):
    from assistant.agent import get_history

    s = make_settings(answer_verify=True)
    checker = recorder("París tiene unos 2.1 millones de habitantes.", "OK")
    llm = fake_llm(tool_call("web_search", {"query": "población de París 2.1 millones"}, "w1"),
                   "París tiene 50 millones de habitantes.", "De nada.")
    agent = _agent(s, llm, checker=checker, checkpointer=mongo_checkpointer)
    thread = uid()
    [v] = [e for e in run_turn(agent, s, "¿Cuántos habitantes tiene París?", thread) if e["type"] == "verify"]
    assert v["status"] == "corrected"
    msgs = _guardados(thread)
    assert [m.type for m in msgs] == ["human", "ai", "tool", "ai"] and msgs[-1].content == v["text"]  # reemplazó
    assert get_history(agent, thread, s)[-1]["original"] == "París tiene 50 millones de habitantes."
    ev = run_turn(agent, s, "gracias", thread)
    assert ev[-1]["type"] == "done" and "De nada." in "".join(e.get("text", "") for e in ev)


def test_aviso_de_corte_y_reintento_con_mismo_id_en_mongo(settings, mongo_checkpointer):
    from assistant.agent import CUT_NOTE

    thread = uid()
    agent = _agent(settings, Cortado(messages=iter(["Semana 1: rodaje suave de"])), checkpointer=mongo_checkpointer)
    run_turn(agent, settings, "plan largo", thread)
    msgs = _guardados(thread)
    assert [m.type for m in msgs] == ["human", "ai"] and msgs[-1].content.endswith(CUT_NOTE)

    llm = CortadoPrimero(messages=iter(["Resumen con lo investigado."]), settings_seen=[])
    thread2 = uid()
    run_turn(_agent(settings, llm, checkpointer=mongo_checkpointer), settings, "investiga", thread2)
    msgs = _guardados(thread2)
    assert [m.type for m in msgs] == ["human", "ai"] and msgs[-1].content == "Resumen con lo investigado."


def test_reemplazo_del_historial_al_resumir_en_mongo(make_settings, mongo_checkpointer):
    from assistant.agent import get_history

    s = make_settings(memory_summarize=True, summary_trigger_tokens=600, summary_keep_tokens=250)
    main = recorder(*[f"respuesta {i}" for i in range(7)])
    summarizer = recorder(*["- The user said their name is Zorba."] * 7)
    agent = _agent(s, main, summarizer=summarizer, checkpointer=mongo_checkpointer)
    thread = uid()
    for i in range(7):
        ev = run_turn(agent, s, f"Mensaje {i}. Me llamo Zorba. " + FILLER, thread)
        assert ev[-1]["type"] == "done" and "error" not in [e["type"] for e in ev]
    assert summarizer.seen
    msgs = _guardados(thread)
    assert msgs[0].additional_kwargs.get("lc_source") == "summarization" and "Zorba" in msgs[0].content
    assert len(msgs) < 14 and msgs[-1].content == "respuesta 6"  # lo viejo se quitó del checkpoint guardado
    assert get_history(agent, thread, s)[0] == {"role": "summary"}


def test_hitl_interrupcion_y_reanudacion_en_mongo(hitl_settings, mongo_checkpointer):
    from assistant.agent import stream_events

    s = hitl_settings
    llm = fake_llm(tool_call("send_simulated_email", {"recipient": "a@b.com", "subject": "Hola", "body": "x"}),
                   "Listo, email enviado")
    agent = _agent(s, llm, checkpointer=mongo_checkpointer)
    thread = uid()
    assert any(e["type"] == "interrupt" for e in run_turn(agent, s, "manda un email", thread))
    ev = list(stream_events(agent, Command(resume={"decisions": [{"type": "approve"}]}), thread, "u1", s))
    assert ev[-1]["type"] == "done" and "tool_end" in [e["type"] for e in ev]
    msgs = _guardados(thread)
    _sin_huerfanos(msgs)
    assert msgs[-1].content == "Listo, email enviado"


def test_bigtool_recupera_herramientas_y_sigue_en_mongo(make_settings, mongo_checkpointer):
    from assistant.bigtool_agent import build_bigtool_agent
    from test_bigtool import _query

    s = make_settings(use_bigtool=True, bigtool_demo_tools=True)
    agent = build_bigtool_agent(
        fake_llm(tool_call("retrieve_tools", {"query": _query("acos", s)}, "r1"), tool_call("acos", {"x": 0.5}, "c1"),
                 "El arcocoseno de 0.5 es 1.0472", "otra"),
        s, checkpointer=mongo_checkpointer, memories_store=InMemoryStore(),
        embeddings=DeterministicFakeEmbedding(size=64), search_fn=SearchConUso())
    thread = uid()
    assert run_turn(agent, s, "arcocoseno de 0.5", thread)[-1]["type"] == "done"
    assert run_turn(agent, s, "y otra cosa", thread)[-1]["type"] == "done"
    msgs = _guardados(thread)
    _sin_huerfanos(msgs)
    assert msgs[-1].content == "otra"
