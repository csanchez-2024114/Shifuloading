"""Medidor de contexto, compactación por porcentaje de la ventana y política de memoria global. Sin tokens: modelos falsos; los que tocan estado de hilos, con MongoDBSaver en
assistant_test."""
import re

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, fake_llm, run_turn, tool_call, uid

FILLER = " ".join(["relleno sintético para ocupar tokens en la conversación."] * 12)


class UsageChat(FakeChat):
    """Modelo falso que informa usage_metadata como la API: entrada = lo que recibe (aprox.) + `extra`
    (prompt y herramientas), salida = su texto + `reasoning` tokens de razonamiento. Guarda cada entrada."""
    extra: int = 1000
    reasoning: int = 0
    seen: list = []

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        msg = next(self.messages)
        if isinstance(msg, str):
            msg = AIMessage(content=msg)
        text = msg.content if isinstance(msg.content, str) else ""
        for piece in re.findall(r"\S+\s*", text):
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))
        inp = count_tokens_approximately([m for m in messages if m.type != "system"]) + self.extra
        out = max(1, len(text) // 4) + self.reasoning
        usage = {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out,
                 "output_token_details": {"reasoning": self.reasoning}}
        calls = [{"name": tc["name"], "args": __import__("json").dumps(tc["args"]), "id": tc["id"], "index": i,
                  "type": "tool_call_chunk"} for i, tc in enumerate(msg.tool_calls)]
        yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=calls, usage_metadata=usage,
                                                         chunk_position="last"))


def usage_chat(*responses, extra=1000, reasoning=0) -> UsageChat:
    return UsageChat(messages=iter(list(responses)), extra=extra, reasoning=reasoning, seen=[])


class SummaryRecorder(FakeChat):
    """Resumidor falso: guarda cada prompt e informa uso (con model_name, como la API: get_usage_metadata_callback
    agrupa por modelo)."""
    prompts: list = []
    usage: dict = {"input_tokens": 500, "output_tokens": 50, "total_tokens": 550}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # fuera del grafo (compactación manual)
        self.prompts.append(" ".join(str(m.content) for m in messages))
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        result.generations[0].message.usage_metadata = dict(self.usage)
        result.generations[0].message.response_metadata = {"model_name": "resumidor-falso"}
        return result

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):  # dentro del stream del agente
        self.prompts.append(" ".join(str(m.content) for m in messages))
        yield ChatGenerationChunk(message=AIMessageChunk(content=next(self.messages), usage_metadata=dict(self.usage),
                                                         response_metadata={"model_name": "resumidor-falso"},
                                                         chunk_position="last"))


def summarizer(*texts) -> SummaryRecorder:
    return SummaryRecorder(messages=iter(list(texts)), prompts=[])


def _agent(settings, llm, checkpointer=None, store=None, summ=None, search_fn=None):
    from assistant.agent import build_agent
    from assistant.tools import build_tools

    tools = build_tools(llm, settings, search_fn=search_fn or FakeSearch())
    return build_agent(llm, tools, settings, checkpointer=checkpointer or InMemorySaver(), store=store,
                       summarizer=summ)


def _values(agent, thread):
    return agent.get_state({"configurable": {"thread_id": thread}}).values


def _client(agent, settings, store=None):
    from assistant.server import create_app

    return TestClient(create_app(agent=agent, settings=settings, store=store or InMemoryStore()))


# --------------------------------------------------------------------------- bloque 1: medidor


def test_hilo_nuevo_empieza_en_el_contexto_base_estimado(make_settings):
    from assistant.agent import fixed_prompt_tokens

    s = make_settings(context_window_tokens=128000)
    agent = _agent(s, usage_chat("x"))
    data = _client(agent, s).get(f"/threads/{uid()}/context").json()
    assert data["estimated"] and data["tokens"] == agent.base_context_tokens > 1000
    assert agent.base_context_tokens == fixed_prompt_tokens(agent.nodes["tools"].bound.tools_by_name.values(),
                                                            settings=s)
    assert data["window"] == 128000 and data["percent"] == round(100 * data["tokens"] / 128000, 1)
    assert data["total_consumed"] == 0 and data["compactions"] == 0 and data["can_compact"]


def test_ventana_por_defecto_sale_del_perfil_del_modelo(make_settings):
    from assistant.config import DEFAULT_CONTEXT_WINDOW

    assert make_settings().context_window() == 1050000  # perfil de gpt-6-luna en langchain
    assert make_settings(llm_model="modelo-sin-perfil").context_window() == DEFAULT_CONTEXT_WINDOW
    assert make_settings(context_window_tokens=32000).context_window() == 32000


def test_medidor_usa_el_uso_real_sube_en_cada_turno_y_se_reconstruye_del_checkpoint(make_settings, mongo_checkpointer):
    s = make_settings(context_window_tokens=128000)
    llm = usage_chat("respuesta uno", "respuesta dos", reasoning=40)
    agent = _agent(s, llm, checkpointer=mongo_checkpointer)
    thread = uid()

    ev1 = run_turn(agent, s, "Primera pregunta. " + FILLER, thread)
    ctx1 = [e for e in ev1 if e["type"] == "context"]
    assert ctx1 and not ctx1[-1]["estimated"]  # en vivo, al terminar el paso del modelo
    last = _values(agent, thread)["messages"][-1]
    usage = last.usage_metadata
    # entrada + salida, sin el razonamiento (no se reenvía)
    assert ctx1[-1]["tokens"] == usage["input_tokens"] + usage["output_tokens"] - 40

    ev2 = run_turn(agent, s, "Segunda pregunta. " + FILLER, thread)
    ctx2 = [e for e in ev2 if e["type"] == "context"][-1]["tokens"]
    assert ctx2 > ctx1[-1]["tokens"]

    # otro agente con el mismo checkpointer (= recargar la página o reiniciar el servidor): mismo valor, 0 tokens
    otro = _agent(s, usage_chat(), checkpointer=mongo_checkpointer)
    data = _client(otro, s).get(f"/threads/{thread}/context").json()
    assert data["tokens"] == ctx2 and not data["estimated"]
    totales = [m.usage_metadata["total_tokens"] for m in _values(agent, thread)["messages"] if m.type == "ai"]
    assert data["total_consumed"] == sum(totales) and data["last_turn"] == totales[-1]
    assert data["total_input"] + data["total_output"] == data["total_consumed"]

    # una conversación nueva no hereda nada de esta
    nuevo = _client(otro, s).get(f"/threads/{uid()}/context").json()
    assert nuevo["tokens"] == otro.base_context_tokens and nuevo["total_consumed"] == 0


def test_compactar_ahora_reduce_el_contexto_y_deja_marca(make_settings, mongo_checkpointer):
    from assistant.agent import get_history

    s = make_settings(context_window_tokens=8000, compact_keep_pct=10)
    llm = usage_chat(*[f"respuesta {i}" for i in range(6)])
    summ = summarizer("- El usuario se llama Zorba.")
    agent = _agent(s, llm, checkpointer=mongo_checkpointer, summ=summ)
    thread = uid()
    for i in range(5):
        run_turn(agent, s, f"Mensaje {i}. Me llamo Zorba. " + FILLER, thread)
    client = _client(agent, s)
    antes = client.get(f"/threads/{thread}/context").json()

    r = client.post(f"/threads/{thread}/compact").json()
    assert r["compacted"] and r["record"]["manual"] and r["record"]["spent"] == 550
    despues = client.get(f"/threads/{thread}/context").json()
    assert despues["tokens"] < antes["tokens"] and despues["estimated"]  # tras compactar: estimado hasta la próxima
    assert despues["compactions"] == 1 and despues["last_compaction"]["after"] == despues["tokens"]
    assert despues["total_consumed"] == antes["total_consumed"] + 550
    hist = get_history(agent, thread, s)
    assert hist[0]["role"] == "summary" and hist[0]["compaction"]["after"] < hist[0]["compaction"]["before"]
    assert "Zorba" in summ.prompts[0]

    # el hilo sigue funcionando y el siguiente turno vuelve a dar el uso real
    ev = run_turn(agent, s, "¿Cómo me llamo?", thread)
    assert ev[-1]["type"] == "done"
    assert not client.get(f"/threads/{thread}/context").json()["estimated"]


def test_compactar_sin_compactador_responde_501(make_settings):
    from assistant.server import create_app

    class SinCompactador:
        def get_state(self, config):
            return type("S", (), {"values": {}, "interrupts": ()})()

    client = TestClient(create_app(agent=SinCompactador(), settings=make_settings(), store=InMemoryStore()))
    assert client.post("/threads/x/compact").status_code == 501
    assert client.get("/threads/x/context").json()["can_compact"] is False


# --------------------------------------------------------------------------- bloque 2: disparo por porcentaje


def test_compacta_por_porcentaje_de_la_ventana_una_vez_por_turno_con_registro(make_settings, mongo_checkpointer):
    s = make_settings(memory_summarize=True, context_window_tokens=4000, compact_trigger_pct=85, compact_keep_pct=10)
    assert not s.compact_legacy() and s.compact_trigger() == 3400 and s.compact_keep() == 400
    llm = usage_chat(*[f"respuesta {i}" for i in range(12)], extra=2200)
    summ = summarizer(*["- resumen"] * 12)
    agent = _agent(s, llm, checkpointer=mongo_checkpointer, summ=summ)
    thread = uid()
    eventos = []
    for i in range(12):
        ev = run_turn(agent, s, f"Mensaje {i}. " + FILLER, thread)
        assert [e["type"] for e in ev].count("summarized") <= 1  # como máximo una compactación por turno
        eventos.append(ev)
    log = _values(agent, thread)["compaction_log"]
    assert log, "se pasó el 85% de la ventana y no compactó"
    rec = log[0]
    assert set(rec) >= {"before", "after", "ratio", "spent", "secs", "layers", "manual"}
    assert rec["before"] >= 3400 > rec["after"] and rec["ratio"] < 1 and rec["layers"] == ["summary"]
    assert rec["spent"] == 550 and not rec["manual"]
    sumd = next(e for ev in eventos for e in ev if e["type"] == "summarized")
    assert sumd["before"] == rec["before"] and sumd["after"] == rec["after"]
    # el encabezado deja claro que el resumen es de la parte más antigua
    first = _values(agent, thread)["messages"][0]
    assert first.content.startswith("Summary of the OLDEST part of this conversation")


def test_variables_anteriores_mantienen_el_disparo_por_tokens_de_mensajes(make_settings):
    s = make_settings(summary_trigger_tokens=600, summary_keep_tokens=250, context_window_tokens=4000)
    assert s.compact_legacy() and s.compact_trigger() == 600 and s.compact_keep() == 250


def test_no_compacta_si_el_turno_ya_aterrizo(make_settings, monkeypatch):
    from assistant import agent as agent_mod

    s = make_settings(memory_summarize=True, context_window_tokens=2000, turn_token_cap=50000)
    agent = _agent(s, usage_chat(), summ=summarizer("- resumen"))
    msgs = [HumanMessage(f"m{i} " + FILLER, id=f"h{i}") if i % 2 == 0 else AIMessage(f"r{i}", id=f"a{i}")
            for i in range(12)]
    counter = agent_mod.TurnTokens()
    monkeypatch.setattr(agent_mod, "_turn_counter", lambda: counter)
    runtime = type("R", (), {"stream_writer": staticmethod(lambda e: None)})()
    counter.total = 41000  # 82% del tope: esta llamada aterriza
    assert agent.compactor.before_model({"messages": list(msgs)}, runtime) is None
    counter.total = 0
    assert agent.compactor.before_model({"messages": list(msgs)}, runtime) is not None




def _hilo_con_resultados_grandes():
    grande = "dato " * 400
    msgs = []
    for i in range(3):
        msgs += [HumanMessage(f"pregunta {i}"), tool_call("web_search", {"query": f"q{i}"}, f"c{i}"),
                 ToolMessage(f"resultado {i}: {grande}", tool_call_id=f"c{i}", name="web_search"),
                 AIMessage(f"interpretación del resultado {i}")]
    msgs += [HumanMessage("pregunta de memoria"), tool_call("search_memories", {"query": "x"}, "m1"),
             ToolMessage("recuerdo " + grande, tool_call_id="m1", name="search_memories"), AIMessage("según tu memoria")]
    return msgs










# --------------------------------------------------------------------------- bloque 4: memoria global


def test_politica_estricta_por_defecto_en_prompt_y_herramienta(make_settings):
    from assistant.agent import system_prompt_text
    from assistant.memory import memory_policy
    from assistant.tools import build_tools

    s = make_settings()
    assert s.memory_save_policy == "strict" and s.memory_max_per_turn == 3
    texto = system_prompt_text(s)
    assert "ONLY when" in texto and "Never save conversation content" in texto and "at most 3" in texto
    assert memory_policy("broad") in system_prompt_text(make_settings(memory_save_policy="broad"))
    doc = next(t for t in build_tools(fake_llm(), s) if t.name == "save_memory").description
    assert "ONLY when the user explicitly asks you to remember" in doc and "Never save conversation" in doc


def test_tope_de_recuerdos_por_mensaje(make_settings, store):
    from assistant.memory import memory_namespace

    s = make_settings(memory_max_per_turn=3)
    datos = ["Vive en Mérida", "Tiene una perrita llamada Canela", "Es fan del Club América", "Toma café de olla"]
    citas = ["vivo en Mérida", "mi perrita se llama Canela", "soy fan del Club América", "tomo café de olla"]
    pedido = AIMessage(content="", tool_calls=[{"name": "save_memory", "args": {"text": d, "evidence": c},
                                                "id": f"s{i}"} for i, (d, c) in enumerate(zip(datos, citas))])
    agent = _agent(s, fake_llm(pedido, "listo"), store=store)
    user = uid("u")
    ev = run_turn(agent, s, "Recuerda: " + ", ".join(citas), uid(), user_id=user)
    fin = [e for e in ev if e["type"] == "tool_end"]
    assert [e["status"] for e in fin].count("skipped") == 1  # el cuarto no corre (la UI no le pone ✓)
    guardados = [i.value["text"] for i in store.search(memory_namespace(user), limit=10)]
    assert sorted(guardados) == sorted(datos[:3])


def test_conversacion_nueva_no_ve_el_contenido_de_otra_solo_la_memoria_global(make_settings, mongo_checkpointer, store):
    s = make_settings()
    user = uid("u")
    hilo1, hilo2 = uid(), uid()
    guardar = tool_call("save_memory", {"text": "Vive en Mérida", "evidence": "vivo en Mérida"}, "s1")
    calc = tool_call("calculator", {"expression": "1234*5"}, "k1")
    buscar = tool_call("search_memories", {"query": "where does the user live"}, "b1")
    llm = usage_chat(guardar, "anotado", calc, "son 6170", "¿Algo más?", buscar, "Vives en Mérida.")
    agent = _agent(s, llm, checkpointer=mongo_checkpointer, store=store)
    run_turn(agent, s, "Hola, vivo en Mérida.", hilo1, user_id=user)
    run_turn(agent, s, "¿Cuánto es 1234*5? La palabra clave secreta es ZANAHORIA.", hilo1, user_id=user)

    run_turn(agent, s, "Hola de nuevo", hilo2, user_id=user)
    primera = llm.seen[-1]  # lo que vio el modelo al abrir la conversación nueva
    texto = " ".join(str(m.content) for m in primera)
    assert "ZANAHORIA" not in texto and "6170" not in texto and "Mérida" not in texto  # nada se inyecta
    assert [m.type for m in primera] == ["system", "human"]
    run_turn(agent, s, "¿Dónde vivo?", hilo2, user_id=user)
    resultado = next(m for m in _values(agent, hilo2)["messages"] if m.type == "tool")
    assert "Mérida" in resultado.content and "ZANAHORIA" not in resultado.content  # solo lo guardado en memoria global
