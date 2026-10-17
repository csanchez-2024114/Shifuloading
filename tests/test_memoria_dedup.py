"""save_memory sin duplicados (MEMORY_DEDUP) y regla de búsqueda económica en memoria (MEMORY_SEARCH_ECONOMY).
Sin tokens: modelos falsos; Mongo solo en assistant_test."""
import pytest
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langgraph.store.memory import InMemoryStore

from conftest import fake_llm, run_turn, tool_call, uid


def _remember(store, user, text, quote, **kw):
    from assistant import memory

    return memory.remember(store, user, text, quote, [quote], **kw)


@pytest.fixture(params=["memoria", "mongo"])
def any_store(request):
    if request.param == "memoria":
        return InMemoryStore()
    return request.getfixturevalue("store")  # MongoDBStore en assistant_test


def test_dato_equivalente_no_se_duplica_y_sugiere_update_con_el_id(any_store):
    from assistant import memory

    user = uid("u")
    _remember(any_store, user, "Toma té verde; dejó el café de olla", "ahora tomo té verde, dejé el café de olla",
              dedup=True)
    [existente] = memory.list_memories(any_store, user)
    msg = _remember(any_store, user, "toma té verde", "tomo té verde", dedup=True)
    assert msg.startswith("Not run: an equivalent memory already exists") and existente["key"] in msg
    assert "update_memory" in msg
    assert len(memory.list_memories(any_store, user)) == 1  # no se creó un duplicado


def test_dato_distinto_si_se_guarda(any_store):
    from assistant import memory

    user = uid("u")
    _remember(any_store, user, "Toma té verde por las mañanas", "tomo té verde por las mañanas", dedup=True)
    for texto, cita in [("Tiene un gato llamado Michi", "tengo un gato llamado Michi"),
                        ("Toma café de olla los domingos", "los domingos tomo café de olla")]:
        assert _remember(any_store, user, texto, cita, dedup=True) == memory.SAVED_MSG
    assert len(memory.list_memories(any_store, user)) == 3


def test_sin_interruptor_se_guarda_como_antes():
    from assistant import memory

    store, user = InMemoryStore(), uid("u")
    _remember(store, user, "Toma té verde", "tomo té verde")
    assert _remember(store, user, "toma té verde", "tomo té verde") == memory.SAVED_MSG
    assert len(memory.list_memories(store, user)) == 2


def test_duplicado_por_puntuacion_semantica():
    from assistant import memory

    store = InMemoryStore(index={"dims": 32, "embed": DeterministicFakeEmbedding(size=32), "fields": ["text"]})
    user = uid("u")
    _remember(store, user, "Vive en Mérida", "vivo en Mérida", dedup=True)
    # el embedding falso es determinista: el mismo texto puntúa 1.0 aunque las palabras no basten (1 raíz)
    msg = _remember(store, user, "Vive en Mérida", "vivo en Mérida", dedup=True, dedup_score=0.99)
    assert msg.startswith("Not run: an equivalent memory")


def test_agente_no_duplica_y_la_ui_lo_marca_como_no_realizado(make_settings, store):
    from assistant import memory
    from assistant.agent import build_agent
    from assistant.tools import build_tools

    s = make_settings(memory_dedup=True)
    user = uid("u")
    memory.save_memory(store, user, "Toma té verde; dejó el café de olla")
    pedido = tool_call("save_memory", {"text": "toma té verde", "evidence": "tomo té verde"}, "s1")
    llm = fake_llm(pedido, "Ya lo tenía anotado.")
    agent = build_agent(llm, build_tools(llm, s), s, store=store)
    ev = run_turn(agent, s, "Recuerda que tomo té verde", uid(), user_id=user)
    fin = next(e for e in ev if e["type"] == "tool_end")
    assert fin["status"] == "skipped" and "update_memory" in fin["output"]
    assert len(memory.list_memories(store, user)) == 1
