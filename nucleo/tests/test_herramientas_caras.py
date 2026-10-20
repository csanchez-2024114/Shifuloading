"""Herramientas caras sin pedirlas y respuestas cortadas (prueba de 3 escenarios): una web_search por llamada al
modelo, confirmación antes de deep_research (pausa y reanudación), "continúa" que sigue donde quedó y margen de salida
con esfuerzo alto. Modelos falsos; los flujos con pausa van con el checkpointer REAL de MongoDB (`assistant_test`)."""
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from conftest import FakeChat, FakeSearch, fake_llm, run_turn, tool_call, uid
from test_cierre_abortado import _guardados, _sin_huerfanos
from test_memoria_avanzada import _agent, recorder
from test_mejoras import Cortado


def _tres_busquedas():
    return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": f"q{i}"}, "id": f"w{i}"}
                                             for i in range(3)])


def test_una_sola_busqueda_por_llamada_al_modelo(settings):
    from assistant.tools import ONE_SEARCH_MSG

    search = FakeSearch()
    from assistant.agent import build_agent
    from assistant.tools import build_tools
    from langgraph.checkpoint.memory import InMemorySaver
    llm = fake_llm(_tres_busquedas(), "respuesta")
    agent = build_agent(llm, build_tools(llm, settings, search_fn=search), settings, checkpointer=InMemorySaver())
    fines = {e["output"] for e in run_turn(agent, settings, "busca tres cosas", uid()) if e["type"] == "tool_end"}
    assert search.calls == ["q0"]
    assert ONE_SEARCH_MSG in fines and any(o.startswith("[engine: duckduckgo]") for o in fines)


def test_una_sola_busqueda_por_llamada_en_bigtool(make_settings, mongo_checkpointer):
    from assistant.bigtool_agent import build_bigtool_agent
    from assistant.tools import ONE_SEARCH_MSG

    s = make_settings(use_bigtool=True)
    search = FakeSearch()
    agent = build_bigtool_agent(fake_llm(_tres_busquedas(), "respuesta"), s, checkpointer=mongo_checkpointer,
                                memories_store=InMemoryStore(), embeddings=DeterministicFakeEmbedding(size=64),
                                search_fn=search)
    fines = [e["output"] for e in run_turn(agent, s, "busca tres cosas", uid()) if e["type"] == "tool_end"]
    assert search.calls == ["q0"] and fines.count(ONE_SEARCH_MSG) == 2


# --------------------------------------------------------------------------- confirmación de deep_research


def _agente_investigador(s, llm, search, checkpointer):
    from assistant.agent import build_agent
    from assistant.tools import build_tools
    return build_agent(llm, build_tools(llm, s, search_fn=search), s, checkpointer=checkpointer)


def _resume(agent, s, thread, decision):
    from assistant.agent import stream_events
    return list(stream_events(agent, Command(resume={"decisions": [decision]}), thread, "u1", s))


def test_deep_research_pide_confirmacion_y_sigue_al_aprobar(settings, mongo_checkpointer):
    from assistant.packs.i18n.es import DEEP_RESEARCH_CONFIRM

    search = FakeSearch()
    llm = fake_llm(tool_call("deep_research", {"task": "viaje a Lisboa"}, "inv"),
                   tool_call("web_search", {"query": "Lisboa museos"}, "s1"), "RESUMEN del investigador",
                   "Plan con lo investigado")
    agent = _agente_investigador(settings, llm, search, mongo_checkpointer)
    thread = uid()
    ev = run_turn(agent, settings, "quiero planear 5 días en Lisboa con 900 euros", thread)
    [intr] = [e for e in ev if e["type"] == "interrupt"]
    assert intr["action_requests"][0]["name"] == "deep_research"
    assert intr["action_requests"][0]["description"] == DEEP_RESEARCH_CONFIRM
    assert search.calls == [] and "tool_end" not in [e["type"] for e in ev]  # nada corre antes de confirmar
    ev2 = _resume(agent, settings, thread, {"type": "approve"})
    assert search.calls == ["Lisboa museos"] and ev2[-1]["type"] == "done"
    assert "Plan con lo investigado" in "".join(e.get("text", "") for e in ev2)
    _sin_huerfanos(_guardados(thread))


def test_deep_research_rechazada_responde_sin_investigar(settings, mongo_checkpointer):
    search = FakeSearch()
    llm = fake_llm(tool_call("deep_research", {"task": "viaje a Lisboa"}, "inv"), "Plan sin investigar")
    agent = _agente_investigador(settings, llm, search, mongo_checkpointer)
    thread = uid()
    run_turn(agent, settings, "quiero planear 5 días en Lisboa con 900 euros", thread)
    ev = _resume(agent, settings, thread, {"type": "reject", "message": "The user declined this action."})
    assert search.calls == [] and "Plan sin investigar" in "".join(e.get("text", "") for e in ev)
    msgs = _guardados(thread)
    _sin_huerfanos(msgs)
    [rechazo] = [m.content for m in msgs if m.type == "tool"]
    assert "The user declined this action." in rechazo


def test_deep_research_pedida_explicitamente_no_pregunta(settings, mongo_checkpointer):
    search = FakeSearch()
    llm = fake_llm(tool_call("deep_research", {"task": "ley de IA"}, "inv"),
                   tool_call("web_search", {"query": "ley IA UE"}, "s1"), "RESUMEN", "Respuesta")
    agent = _agente_investigador(settings, llm, search, mongo_checkpointer)
    ev = run_turn(agent, settings, "Investiga a fondo la ley de IA de la UE", uid())
    assert "interrupt" not in [e["type"] for e in ev] and search.calls == ["ley IA UE"]


def test_deep_research_en_bigtool_pide_confirmacion(make_settings, mongo_checkpointer):
    from assistant.bigtool_agent import build_bigtool_agent
    from assistant.packs.i18n.es import DEEP_RESEARCH_CONFIRM
    from assistant.tools import RESEARCH_DECLINED_MSG

    s = make_settings(use_bigtool=True)
    search = FakeSearch()
    llm = fake_llm(tool_call("deep_research", {"task": "viaje"}, "inv"), "Plan sin investigar",
                   tool_call("deep_research", {"task": "viaje"}, "inv2"),
                   tool_call("web_search", {"query": "Lisboa"}, "s1"), "RESUMEN", "Plan investigado")
    agent = build_bigtool_agent(llm, s, checkpointer=mongo_checkpointer, memories_store=InMemoryStore(),
                                embeddings=DeterministicFakeEmbedding(size=64), search_fn=search)
    thread = uid()
    [intr] = [e for e in run_turn(agent, s, "planea 5 días en Lisboa", thread) if e["type"] == "interrupt"]
    assert intr["action_requests"][0]["description"] == DEEP_RESEARCH_CONFIRM
    ev = _resume(agent, s, thread, {"type": "reject", "message": "x"})
    assert RESEARCH_DECLINED_MSG in [e.get("output") for e in ev if e["type"] == "tool_end"] and search.calls == []
    run_turn(agent, s, "vale, otro plan para Oporto", thread)
    ev = _resume(agent, s, thread, {"type": "approve"})
    assert search.calls == ["Lisboa"] and "Plan investigado" in "".join(e.get("text", "") for e in ev)
    _sin_huerfanos(_guardados(thread))


# --------------------------------------------------------------------------- respuestas cortadas


class CortadoYLuegoSigue(Cortado):
    """1ª respuesta: cortada por max_output_tokens. Después responde normal. Guarda lo que ve cada llamada."""
    vistos: list = []

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self.vistos.append(list(messages))
        if len(self.vistos) == 1:
            yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        else:
            yield from FakeChat._stream(self, messages, stop=stop, run_manager=run_manager, **kwargs)


def test_continua_sigue_donde_quedo_sin_rehacer(settings):
    from assistant.agent import CONTINUE_NOTE
    from assistant.packs.i18n.es import CUT_NOTE

    llm = CortadoYLuegoSigue(messages=iter(["def total(filas):\n    suma = 0", "    for f in filas:", "otra cosa"]),
                             vistos=[])
    agent = _agent(settings, llm)
    thread = uid()
    ev = run_turn(agent, settings, "escríbeme la función total", thread)
    assert "".join(e.get("text", "") for e in ev).endswith(CUT_NOTE) and "⚠️" in CUT_NOTE
    run_turn(agent, settings, "continúa", thread)
    vistos = llm.vistos[1]
    system = str(vistos[0].content)
    cortada = [m for m in vistos if m.type == "ai"][-1]
    assert CONTINUE_NOTE in system
    assert str(cortada.content).endswith("suma = 0") and CUT_NOTE not in str(cortada.content)  # sin el aviso
    run_turn(agent, settings, "gracias, ahora otra cosa", thread)  # un mensaje normal no lleva la nota
    assert CONTINUE_NOTE not in str(llm.vistos[2][0].content)


class VeKwargs(FakeChat):
    """create_agent pasa los model_settings (reasoning, max_tokens) a bind_tools: aquí se guardan."""
    kwargs_vistos: list = []

    def bind_tools(self, tools, **kwargs):
        self.kwargs_vistos.append(kwargs)
        return self


def test_esfuerzo_alto_reserva_margen_de_salida(make_settings):
    from assistant.agent import contexto_para, stream_events

    s = make_settings(max_tokens=8000, model_call_limit=0, effort_high_max_tokens=12000)
    assert contexto_para("u", s, "alto").max_tokens == 12000
    assert contexto_para("u", s, "medio").max_tokens is None  # solo con esfuerzo alto
    assert contexto_para("u", make_settings(max_tokens=0, model_call_limit=0), "alto").max_tokens is None  # 0 = sin tope
    assert contexto_para("u", make_settings(max_tokens=20000, model_call_limit=0), "alto").max_tokens is None
    llm = VeKwargs(messages=iter(["ok", "ok"]), kwargs_vistos=[])
    agent = _agent(s, llm)
    list(stream_events(agent, {"messages": [{"role": "user", "content": "hola"}]}, uid(), "u", s, "alto"))
    list(stream_events(agent, {"messages": [{"role": "user", "content": "hola"}]}, uid(), "u", s, "medio"))
    assert llm.kwargs_vistos[0].get("max_tokens") == 12000 and "max_tokens" not in llm.kwargs_vistos[1]


def test_reglas_del_prompt_y_de_save_memory():
    from pathlib import Path

    from assistant.agent import system_prompt_text
    from assistant.memory import memory_policy
    from assistant.tools import GUARDAR_RECUERDO_DOC

    texto = (Path(__file__).resolve().parents[1] / "src" / "assistant" / "profiles" / "default" / "prompts" / "system.md").read_text(encoding="utf-8-sig")
    for regla in ("at most one web_search per step", "Use deep_research only when the user explicitly asks",
                  "check it with check_python_syntax", "continue exactly where it stopped"):
        assert regla in texto, regla
    # MEMORY_SAVE_POLICY=broad conserva las reglas de guardado anteriores
    amplia = memory_policy("broad")
    for regla in ("durable technical constraints", "Do not save passing details of a single task",
                  "Stable facts the user mentions while asking for something else"):
        assert regla in amplia, regla
    assert "durable technical constraints" in GUARDAR_RECUERDO_DOC and "Never save details of the current task" in GUARDAR_RECUERDO_DOC
    assert memory_policy("strict") in system_prompt_text()  # strict por defecto
