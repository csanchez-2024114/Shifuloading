"""TURN_TOKEN_CAP con aterrizaje suave: al 80% del tope, la siguiente llamada va sin herramientas y responde con lo ya
recuperado; el aborto queda como último recurso. Checkpointer REAL de MongoDB (base `assistant_test`), modelos falsos."""
import re

from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, run_turn, tool_call, uid
from test_cierre_abortado import _cerrado, _guardados, _sin_huerfanos
from test_mejoras import SearchConUso


class ConCoste(FakeChat):
    """Cada llamada reporta `costes[i]` tokens; guarda el tool_choice y el prompt de sistema de cada llamada."""
    costes: list = []
    vistos: list = []
    choice: str | None = None

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"choice": kwargs.get("tool_choice")})

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        system = next((str(m.content) for m in messages if m.type == "system"), "")
        self.vistos.append({"choice": self.choice, "system": system, "messages": list(messages)})
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)
        n = self.costes[len(self.vistos) - 1] if len(self.vistos) <= len(self.costes) else 10
        yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata={
            "input_tokens": n, "output_tokens": 0, "total_tokens": n}))


def _agente(s, llm, checkpointer):
    from assistant.agent import build_agent
    from assistant.tools import build_tools
    return build_agent(llm, build_tools(llm, s, search_fn=SearchConUso()), s, checkpointer=checkpointer)


def _texto(ev):
    return "".join(e.get("text", "") for e in ev if e["type"] == "token")


def test_aterrizaje_suave_responde_con_lo_recuperado(make_settings, mongo_checkpointer):
    from assistant.agent import SOFT_CAP_NOTE, turn_cap_msg

    s = make_settings(turn_token_cap=100000, model_call_limit=15)
    # 45k + 45k = 90k ≥ 80k: la 3ª llamada es el aterrizaje (sin herramientas); con ella se pasa del tope, sin abortar
    llm = ConCoste(messages=iter([tool_call("calculator", {"expression": "1+1"}, "c1"),
                                  tool_call("calculator", {"expression": "2+2"}, "c2"),
                                  "Con lo que tengo: 1+1=2 y 2+2=4. No pude seguir calculando el resto."]),
                   costes=[45000, 45000, 30000], vistos=[])
    agent = _agente(s, llm, mongo_checkpointer)
    thread = uid()
    ev = run_turn(agent, s, "calcula muchas cosas", thread)
    assert [v["choice"] for v in llm.vistos] == [None, None, "none"]
    assert SOFT_CAP_NOTE in llm.vistos[-1]["system"] and SOFT_CAP_NOTE not in llm.vistos[0]["system"]
    assert "Con lo que tengo" in _texto(ev) and turn_cap_msg(100000) not in _texto(ev)
    assert ev[-1]["type"] == "done"
    msgs = _guardados(thread)
    _sin_huerfanos(msgs)
    assert msgs[-1].content.startswith("Con lo que tengo")
    llm.messages, llm.costes = iter(["sigo bien"]), []
    assert "sigo bien" in _texto(run_turn(agent, s, "hola", thread))  # el siguiente mensaje empieza de cero


def test_aborto_de_respaldo_si_salta_del_70_al_110(make_settings, mongo_checkpointer):
    from assistant.agent import turn_cap_msg

    s = make_settings(turn_token_cap=100000, model_call_limit=15)
    # 70k (< 80k: sin aterrizaje) y luego 40k en una llamada que pide herramientas: 110k sin haber aterrizado
    llm = ConCoste(messages=iter([tool_call("calculator", {"expression": "1+1"}, "c1"),
                                  tool_call("calculator", {"expression": "2+2"}, "c2")]),
                   costes=[70000, 40000], vistos=[])
    agent = _agente(s, llm, mongo_checkpointer)
    thread = uid()
    ev = run_turn(agent, s, "calcula", thread)
    assert [v["choice"] for v in llm.vistos] == [None, None]
    assert turn_cap_msg(100000) in _texto(ev)
    _cerrado(thread, 100000, cancelados={"c2"}, terminados={"c1"})


class BigConCoste(ConCoste):
    pass


def test_aterrizaje_suave_en_bigtool(make_settings, mongo_checkpointer):
    from assistant.agent import SOFT_CAP_NOTE
    from assistant.bigtool_agent import build_bigtool_agent

    s = make_settings(use_bigtool=True, turn_token_cap=100000, model_call_limit=15)
    llm = BigConCoste(messages=iter([tool_call("calculator", {"expression": "1+1"}, "c1"),
                                     "Con lo que tengo: 2. No pude completar lo demás."]),
                      costes=[85000, 30000], vistos=[])
    agent = build_bigtool_agent(llm, s, checkpointer=mongo_checkpointer, memories_store=InMemoryStore(),
                                embeddings=DeterministicFakeEmbedding(size=64), search_fn=SearchConUso())
    thread = uid()
    ev = run_turn(agent, s, "calcula", thread)
    assert [v["choice"] for v in llm.vistos] == [None, "none"]
    assert SOFT_CAP_NOTE in llm.vistos[-1]["system"]
    assert "Con lo que tengo" in _texto(ev) and ev[-1]["type"] == "done"
    _sin_huerfanos(_guardados(thread))


def test_avisos_al_usuario_sin_marcadores_de_markdown():
    from assistant import agent

    avisos = {"LIMIT_MSG": agent.LIMIT_MSG, "CUT_NOTE": agent.CUT_NOTE,
              "TURN_CAP_MSG": agent.turn_cap_msg(45000)}
    crudo = re.compile(r"(^|\s)(\*\*?|__?|`)\S|\S(\*\*?|__?|`)($|[\s.,;:!?])")
    assert not {k: v for k, v in avisos.items() if crudo.search(v)}, "aviso con marcadores de markdown"


def test_respuesta_final_que_cruza_el_tope_no_se_aborta(make_settings, mongo_checkpointer):
    # prueba real: la 1ª llamada quedó en el 74% (sin aterrizaje), la respuesta final cruzó el tope y el aviso de
    # aborto se pegaba detrás de una respuesta completa
    from assistant.agent import turn_cap_msg

    s = make_settings(turn_token_cap=100000, model_call_limit=15)
    llm = ConCoste(messages=iter([tool_call("calculator", {"expression": "1+1"}, "c1"), "1+1 son 2."]),
                   costes=[74000, 40000], vistos=[])
    agent = _agente(s, llm, mongo_checkpointer)
    thread = uid()
    ev = run_turn(agent, s, "calcula", thread)
    assert _texto(ev) == "1+1 son 2." and turn_cap_msg(100000) not in _texto(ev)
    msgs = _guardados(thread)
    _sin_huerfanos(msgs)
    assert msgs[-1].content == "1+1 son 2."


def test_pasado_el_tope_no_verifica_y_la_respuesta_queda_no_verificada(make_settings, mongo_checkpointer):
    """Prueba real: con TURN_TOKEN_CAP=4000 el turno aterrizó y aun así ANSWER_VERIFY gastó otra llamada (2.794)."""
    from assistant.agent import UNVERIFIED_NOTE, build_agent, get_history
    from assistant.tools import build_tools
    from test_memoria_avanzada import recorder

    s = make_settings(turn_token_cap=100000, model_call_limit=15, answer_verify=True)
    # 70k + 15k de la búsqueda = 85k ≥ 80k: la respuesta es el aterrizaje; con evidencia, pero sin verificar
    llm = ConCoste(messages=iter([tool_call("web_search", {"query": "leyes IA"}, "w1"), "Resumen parcial."]),
                   costes=[70000, 10000], vistos=[])
    checker = recorder("OK")
    agent = build_agent(llm, build_tools(llm, s, search_fn=SearchConUso(15000)), s, checkpointer=mongo_checkpointer,
                        checker=checker)
    thread = uid()
    ev = run_turn(agent, s, "compara leyes", thread)
    assert [v["choice"] for v in llm.vistos] == [None, "none"]
    assert checker.seen == []  # ninguna llamada de verificación pasado el tope
    [ver] = [e for e in ev if e["type"] == "verify"]
    assert ver["status"] == "unverified" and ver["notes"] == [UNVERIFIED_NOTE] and "text" not in ver
    assert "verifying" not in [e.get("phase") for e in ev if e["type"] == "phase"]
    [resp] = [m for m in get_history(agent, thread, s) if m["role"] == "assistant"]  # al recargar se sigue viendo
    assert resp == {"role": "assistant", "content": "Resumen parcial.",
                    "verify": {"status": "unverified", "notes": [UNVERIFIED_NOTE]}}
    _sin_huerfanos(_guardados(thread))


def test_bajo_el_tope_si_verifica(make_settings, mongo_checkpointer):
    from assistant.agent import build_agent
    from assistant.tools import build_tools
    from test_memoria_avanzada import recorder

    s = make_settings(turn_token_cap=100000, model_call_limit=15, answer_verify=True)
    llm = ConCoste(messages=iter([tool_call("web_search", {"query": "q"}, "w1"), "Hay vuelos."]),
                   costes=[1000, 1000], vistos=[])
    checker = recorder("OK")
    agent = build_agent(llm, build_tools(llm, s, search_fn=SearchConUso(1000)), s, checkpointer=mongo_checkpointer,
                        checker=checker)
    ev = run_turn(agent, s, "busca vuelos", uid())
    assert len(checker.seen) == 1 and [e["status"] for e in ev if e["type"] == "verify"] == ["ok"]


def test_historial_mas_pesado_que_el_tope_va_sin_herramientas(make_settings, mongo_checkpointer):
    """Prueba real: el 2.º mensaje de un hilo de 5k tokens con tope 4.000. Ese turno no intenta herramientas."""
    from assistant.agent import HISTORY_CAP_NOTE, SOFT_CAP_NOTE, turn_cap_msg

    s = make_settings(turn_token_cap=4000, model_call_limit=15)
    llm = ConCoste(messages=iter(["Respuesta corta.", "Sigo aquí."]), costes=[50, 50], vistos=[])
    agent = _agente(s, llm, mongo_checkpointer)
    thread = uid()
    run_turn(agent, s, "hola", thread)
    assert llm.vistos[0]["choice"] is None  # historial corto: herramientas disponibles
    ev = run_turn(agent, s, "resume esto: " + "palabra " * 4000, thread)  # ~8k tokens aprox. > 4.000
    assert llm.vistos[1]["choice"] == "none"
    assert HISTORY_CAP_NOTE in llm.vistos[1]["system"] and SOFT_CAP_NOTE not in llm.vistos[1]["system"]
    assert "Sigo aquí." in _texto(ev) and turn_cap_msg(4000) not in _texto(ev) and ev[-1]["type"] == "done"
    _sin_huerfanos(_guardados(thread))


def test_historial_mas_pesado_que_el_tope_en_bigtool(make_settings, mongo_checkpointer):
    from assistant.agent import HISTORY_CAP_NOTE
    from assistant.bigtool_agent import build_bigtool_agent

    s = make_settings(use_bigtool=True, turn_token_cap=4000, model_call_limit=15)
    llm = BigConCoste(messages=iter(["Respuesta corta."]), costes=[50], vistos=[])
    agent = build_bigtool_agent(llm, s, checkpointer=mongo_checkpointer, memories_store=InMemoryStore(),
                                embeddings=DeterministicFakeEmbedding(size=64), search_fn=SearchConUso())
    ev = run_turn(agent, s, "resume esto: " + "palabra " * 4000, uid())
    assert [v["choice"] for v in llm.vistos] == ["none"] and HISTORY_CAP_NOTE in llm.vistos[0]["system"]
    assert "Respuesta corta." in _texto(ev) and ev[-1]["type"] == "done"


def test_sin_herramientas_por_historial_avisa_en_vivo_y_al_recargar(make_settings, mongo_checkpointer):
    """Prueba real (tope 1.500): respondió sin herramientas, pero nada le decía al usuario por qué."""
    from assistant.agent import get_history

    s = make_settings(turn_token_cap=4000, model_call_limit=15)
    llm = ConCoste(messages=iter(["Respuesta corta.", "No puedo buscar ahora."]), costes=[50, 50], vistos=[])
    agent = _agente(s, llm, mongo_checkpointer)
    thread = uid()
    assert "no_tools" not in [e["type"] for e in run_turn(agent, s, "hola", thread)]  # historial corto: sin aviso
    ev = run_turn(agent, s, "precio del bitcoin. " + "palabra " * 4000, thread)
    assert [e["type"] for e in ev].count("no_tools") == 1
    respuestas = [m for m in get_history(agent, thread, s) if m["role"] == "assistant"]
    assert "no_tools" not in respuestas[0] and respuestas[1]["no_tools"] is True
    _sin_huerfanos(_guardados(thread))


def test_aterrizaje_por_gasto_no_es_aviso_de_sin_herramientas(make_settings, mongo_checkpointer):
    s = make_settings(turn_token_cap=100000, model_call_limit=15)
    llm = ConCoste(messages=iter([tool_call("calculator", {"expression": "1+1"}, "c1"), "Con lo que tengo: 2."]),
                   costes=[85000, 10], vistos=[])
    ev = run_turn(_agente(s, llm, mongo_checkpointer), s, "calcula", uid())
    assert llm.vistos[-1]["choice"] == "none" and "no_tools" not in [e["type"] for e in ev]


def test_sin_herramientas_por_historial_en_bigtool(make_settings, mongo_checkpointer):
    from assistant.agent import get_history
    from assistant.bigtool_agent import build_bigtool_agent

    s = make_settings(use_bigtool=True, turn_token_cap=4000, model_call_limit=15)
    llm = BigConCoste(messages=iter(["Respuesta corta."]), costes=[50], vistos=[])
    agent = build_bigtool_agent(llm, s, checkpointer=mongo_checkpointer, memories_store=InMemoryStore(),
                                embeddings=DeterministicFakeEmbedding(size=64), search_fn=SearchConUso())
    thread = uid()
    ev = run_turn(agent, s, "resume esto: " + "palabra " * 4000, thread)
    assert "no_tools" in [e["type"] for e in ev] and "Respuesta corta." in _texto(ev)
    assert [m for m in get_history(agent, thread, s) if m["role"] == "assistant"][-1]["no_tools"] is True


def test_aviso_al_arrancar_si_el_tope_no_alcanza_para_prompt_y_herramientas(make_settings, caplog):
    import logging

    from assistant.agent import check_turn_cap
    from assistant.tools import build_tools
    from conftest import fake_llm

    tools = build_tools(fake_llm("x"), make_settings())
    with caplog.at_level(logging.WARNING, logger="assistant"):
        minimo = check_turn_cap(make_settings(turn_token_cap=1500), tools)
    assert minimo > 1500 and "TURN_TOKEN_CAP=1500" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="assistant"):
        assert check_turn_cap(make_settings(turn_token_cap=minimo + 1), tools) == minimo
        check_turn_cap(make_settings(turn_token_cap=0), tools)  # 0 = sin tope: nada que avisar
    assert "TURN_TOKEN_CAP" not in caplog.text
