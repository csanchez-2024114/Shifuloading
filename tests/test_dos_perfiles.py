"""Dos perfiles en el mismo proceso: con AGENT_PROFILE=default activo, un agente construido con otro perfil usa SUS
reglas de intención, SU léxico de memoria, SUS avisos del turno y SU tarjeta de deep_research, y no contamina al agente
del perfil activo (ni al revés), aunque sus turnos se intercalen. Sin tokens."""
import re
from dataclasses import replace

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings, run_turn, tool_call, types, uid


class Gasta(FakeChat):
    """FakeChat que informa `tokens` por llamada."""

    tokens: int = 0

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        chunks = list(super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        last = chunks[-1].message
        usage = {"input_tokens": self.tokens, "output_tokens": 0, "total_tokens": self.tokens}
        chunks[-1] = ChatGenerationChunk(message=AIMessageChunk(content=last.content, usage_metadata=usage,
                                                                tool_call_chunks=last.tool_call_chunks,
                                                                chunk_position="last"))
        yield from chunks


def _perfil_b():
    from assistant.core.i18n import TextCatalog
    from assistant.core.profile import load_profile
    from assistant.packs.i18n import es

    base = load_profile("default")
    return replace(
        base, name="perfil_b",
        texts=TextCatalog(es.TEXTS, {"agent.turn_cap": "TOPE-B {cap}", "tools.deep_research_confirm": "TARJETA-B"}),
        intents=replace(base.intents, explicit_research=re.compile(r"\bmodo b\b")),
        lexicon=replace(base.lexicon, subject=re.compile(r"^\s*el cliente\s+", re.I)))


def _agente(perfil, *responses, tokens=0, store=None, **overrides):
    from assistant.core.agent import build_agent
    from assistant.core.tools import build_tools

    s = _settings(**overrides)
    llm = Gasta(messages=iter(list(responses)), tokens=tokens)
    tools = build_tools(llm, s, search_fn=FakeSearch(), profile=perfil)
    return build_agent(llm, tools, s, checkpointer=InMemorySaver(), store=store or InMemoryStore(),
                       profile=perfil), s


def _default():
    from assistant.core.profile import load_profile

    return load_profile("default")


def _texto(ev):
    return "".join(e.get("text", "") for e in ev if e["type"] == "token")


def test_el_perfil_activo_es_default(monkeypatch):
    from assistant.core.profile import active_profile, current_profile

    monkeypatch.delenv("AGENT_PROFILE", raising=False)
    assert active_profile().name == "default" and current_profile().name == "default"


def test_aviso_de_tope_de_cada_perfil():
    a, sa = _agente(_default(), tool_call("calculator", {"expression": "1+1"}, "c1"), tokens=90000,
                    turn_token_cap=50000)
    b, sb = _agente(_perfil_b(), tool_call("calculator", {"expression": "1+1"}, "c1"), tokens=90000,
                    turn_token_cap=50000)
    tb = _texto(run_turn(b, sb, "suma", uid()))
    ta = _texto(run_turn(a, sa, "suma", uid()))
    assert "TOPE-B 50" in tb and "TURN_TOKEN_CAP" not in tb
    assert "TURN_TOKEN_CAP" in ta and "TOPE-B" not in ta


def test_reglas_de_intencion_y_tarjeta_de_cada_perfil():
    msg = "Compara opiniones sobre el café, modo b"
    resp = [tool_call("deep_research", {"task": "café"}, "d1"), tool_call("web_search", {"query": "café"}, "s1"),
            "RESUMEN", "Informe."]
    b, sb = _agente(_perfil_b(), *resp)
    a, sa = _agente(_default(), *resp)
    ev_b = run_turn(b, sb, msg, uid())
    ev_a = run_turn(a, sa, msg, uid())
    # en B, "modo b" es pedir investigar: sin tarjeta. En default no lo es: tarjeta con su texto de siempre
    assert "interrupt" not in types(ev_b) and "Informe." in _texto(ev_b)
    [card] = [e for e in ev_a if e["type"] == "interrupt"]
    assert card["action_requests"][0]["description"] != "TARJETA-B"
    # sin "modo b", B también pide confirmación, con SU texto
    b2, sb2 = _agente(_perfil_b(), tool_call("deep_research", {"task": "té"}, "d2"), "x")
    [card_b] = [e for e in run_turn(b2, sb2, "Compara opiniones sobre el té", uid()) if e["type"] == "interrupt"]
    assert card_b["action_requests"][0]["description"] == "TARJETA-B"


def test_lexico_de_memoria_de_cada_perfil():
    from assistant.core import memory

    store = InMemoryStore()
    save = tool_call("save_memory", {"text": "El cliente vive en Mérida", "evidence": "vivo en Mérida"}, "g1")
    b, sb = _agente(_perfil_b(), save, "ok", store=store)
    a, sa = _agente(_default(), save, "ok", store=store)
    run_turn(b, sb, "vivo en Mérida", uid(), user_id="beto")
    run_turn(a, sa, "vivo en Mérida", uid(), user_id="ana")
    assert [m["text"] for m in memory.list_memories(store, "beto")] == ["Vive en Mérida"]  # B quita "El cliente"
    assert [m["text"] for m in memory.list_memories(store, "ana")] == ["El cliente vive en Mérida"]


def test_turnos_intercalados_no_se_contaminan():
    from assistant.core.profile import current_profile

    a, sa = _agente(_default(), *[tool_call("calculator", {"expression": "1"}, f"c{i}") for i in range(3)],
                    tokens=90000, turn_token_cap=50000)
    b, sb = _agente(_perfil_b(), *[tool_call("calculator", {"expression": "1"}, f"c{i}") for i in range(3)],
                    tokens=90000, turn_token_cap=50000)
    gen_a = iter(run_turn(a, sa, "uno", uid()))
    tb = _texto(run_turn(b, sb, "dos", uid()))
    ta = _texto(list(gen_a))
    assert "TOPE-B" in tb and "TOPE-B" not in ta
    assert current_profile().name == "default"  # al terminar los turnos, el perfil del turno se restaura
