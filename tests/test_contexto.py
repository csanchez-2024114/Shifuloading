"""Política de memoria global (MEMORY_SAVE_POLICY, MEMORY_MAX_PER_TURN) e independencia entre conversaciones.
 Sin tokens: modelos falsos; los que tocan estado de hilos, con MongoDBSaver en
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
