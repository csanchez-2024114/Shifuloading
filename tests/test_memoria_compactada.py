"""B2 de la prueba larga (docs/PRUEBA_USUARIO_LARGA.md): tras una compactación, update_memory no podía corregir un
recuerdo con varios datos porque el dato viejo ya no estaba en los mensajes. Con MEMORY_UPDATE_PRIOR_EVIDENCE=1 la
cita guardada en el recuerdo respalda lo que no cambia; el valor nuevo se sigue exigiendo en esta conversación.
Sin tokens: modelos falsos (el verificador revisa por contenido)."""
import re

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeChat, FakeSearch, _settings, fake_llm, run_turn, tool_call, uid

SEED = "los proveedores me entregan los jueves y tengo 3 empleadas, recuérdalo"
OLD = "Sus proveedores entregan los jueves y tiene tres empleadas"
NEW = "Sus proveedores entregan los jueves y tiene cuatro empleadas"
# dato del candidato -> lo que el usuario tuvo que escribir para respaldarlo
FACTS = [("jueves", "jueves"), ("tres empleadas", "3 empleadas"), ("cuatro empleadas", "son 4"),
         ("cinco empleadas", "5")]


class Checker(FakeChat):
    """Verificador de recuerdos falso: respalda el candidato solo si cada dato aparece en USER MESSAGES."""

    def _answer(self, messages):
        prompt = str(messages[-1].content)
        users = prompt.split("USER MESSAGES", 1)[1].split("CANDIDATE MEMORY:", 1)[0].lower()
        candidate = prompt.split("CANDIDATE MEMORY:", 1)[1].split("The memory is SUPPORTED", 1)[0].lower()
        ok = all(said in users for fact, said in FACTS if fact in candidate)
        self.messages = iter(['{"supported": %s, "quote": ""}' % ("true" if ok else "false")])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._answer(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        self._answer(messages)
        yield from super()._stream(messages, stop=stop, run_manager=run_manager, **kwargs)


def _build(s, responses, checkpointer, store):
    from assistant.core.agent import build_agent
    from assistant.core.tools import build_tools

    llm, checker = fake_llm(*responses), Checker(messages=iter([]))
    summarizer = fake_llm(*["- The user talked about their shop."] * 3)
    tools = build_tools(llm, s, search_fn=FakeSearch(), checker=checker)
    return build_agent(llm, tools, s, checkpointer=checkpointer, store=store, summarizer=summarizer,
                       checker=checker)


def _memories(store, user):
    from assistant.core.memory import memory_namespace

    return {i.key: i.value for i in store.search(memory_namespace(user), limit=50)}


def _tool_out(events, name):
    return next(e["output"] for e in events if e["type"] == "tool_end" and e["name"] == name)


@pytest.mark.parametrize("prior", [False, True])
def test_sembrar_compactar_corregir_y_leer_en_hilo_nuevo(prior):
    from assistant.core.agent import compact_thread, run_config
    from assistant.core.memory import user_texts

    s = _settings(memory_verify=True, memory_require_quote=True, memory_summarize=True,
                  context_window_tokens=100000, compact_keep_tokens=5, memory_update_prior_evidence=prior)
    saver, store, thread, user = InMemorySaver(), InMemoryStore(), uid(), uid("marta")

    # 1. sembrar
    agent = _build(s, [tool_call("save_memory", {"text": OLD, "evidence": SEED[:58]}, "s1"), "Anotado.",
                       "Va."], saver, store)
    ev = run_turn(agent, s, SEED, thread, user_id=user)
    assert _tool_out(ev, "save_memory").startswith("Memory saved")
    run_turn(agent, s, "oye y qué plantas aguantan el frío?", thread, user_id=user)
    [(key, value)] = _memories(store, user).items()
    assert value["evidence"] == SEED[:58]

    # 2. compactar: el mensaje de la siembra ya no está entre lo que escribió el usuario
    assert compact_thread(agent, thread, s) is not None
    texts = user_texts(agent.get_state(run_config(thread, s)).values["messages"])
    assert not any("jueves" in t for t in texts)

    # 3. corregir uno de los dos datos
    agent = _build(s, [tool_call("update_memory", {"id": key, "text": NEW, "evidence": "son 4"}, "u1"),
                       "Listo."], saver, store)
    ev = run_turn(agent, s, "corrección: no son 3 empleadas, son 4", thread, user_id=user)
    out = _tool_out(ev, "update_memory")
    stored = _memories(store, user)[key]
    if not prior:  # el bug: el verificador ya no ve "jueves" y rechaza todo el recuerdo
        assert out.startswith("Not updated: the user never stated")
        assert stored["text"] == OLD
        return
    assert out.startswith("Memory updated")
    assert stored["text"] == NEW and stored["evidence"] == "son 4"

    # 4. leer en un hilo nuevo del mismo usuario
    agent = _build(s, [tool_call("search_memories", {"query": "empleadas"}, "r1"), "Tienes cuatro empleadas."],
                   saver, store)
    ev = run_turn(agent, s, "¿cuántas empleadas tengo?", uid(), user_id=user)
    found = _tool_out(ev, "search_memories")
    assert "cuatro empleadas" in found and "tres empleadas" not in found


def _seeded(store, user):
    from assistant.core import memory

    memory.save_memory(store, user, OLD, thread_id="t0", evidence=SEED[:58], confidence="quoted")
    [key] = _memories(store, user)
    return key


def _checker():
    from assistant.core import memory

    return memory.make_memory_verifier(Checker(messages=iter([])))


def test_un_valor_que_el_usuario_nunca_dijo_sigue_rechazado():
    from assistant.core import memory

    store, user = InMemoryStore(), uid()
    key = _seeded(store, user)
    texts = ["actualiza lo de mis empleadas porfa"]  # no dice cuántas
    out = memory.revise(store, user, key, "Sus proveedores entregan los jueves y tiene cinco empleadas", "", texts,
                        verifier=_checker(), require_quote=True, prior_evidence=True)
    assert out.startswith("Not updated") and _memories(store, user)[key]["text"] == OLD


def test_la_cita_vieja_no_prueba_el_valor_nuevo():
    """Con MEMORY_REQUIRE_QUOTE, la evidencia debe estar en esta conversación: citar el recuerdo viejo no basta."""
    from assistant.core import memory

    store, user = InMemoryStore(), uid()
    key = _seeded(store, user)
    texts = ["corrige mis empleadas"]
    out = memory.revise(store, user, key, NEW, SEED[:58], texts, require_quote=True, prior_evidence=True)
    assert out.startswith("Not updated: evidence must quote") and _memories(store, user)[key]["text"] == OLD
    out = memory.revise(store, user, key, NEW, "son 4", texts + ["no son 3, son 4"], require_quote=True,
                        prior_evidence=True)
    assert out.startswith("Memory updated")
    assert _memories(store, user)[key]["evidence"] == "son 4"


def test_apagado_la_evidencia_guardada_no_se_usa():
    from assistant.core import memory

    store, user = InMemoryStore(), uid()
    key = _seeded(store, user)
    out = memory.revise(store, user, key, NEW, "son 4", ["no son 3, son 4"], verifier=_checker())
    assert out.startswith("Not updated") and re.search("tres", _memories(store, user)[key]["text"])
