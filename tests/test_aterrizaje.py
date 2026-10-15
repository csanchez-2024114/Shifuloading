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
