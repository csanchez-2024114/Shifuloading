"""Variante langgraph-bigtool (USE_BIGTOOL=1): registro, índice y flujo de recuperación. Sin tokens:
modelo falso + DeterministicFakeEmbedding (el mismo texto da el mismo vector)."""
import pytest
from langchain_core.embeddings.fake import DeterministicFakeEmbedding
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from conftest import FakeSearch, fake_llm, run_turn, tool_call, types, uid


@pytest.fixture
def bt_settings(make_settings):
    return make_settings(use_bigtool=True, bigtool_demo_tools=True)


def _agent(responses, settings, memories_store=None):
    from assistant.bigtool_agent import build_bigtool_agent

    return build_bigtool_agent(fake_llm(*responses), settings, checkpointer=InMemorySaver(),
                               memories_store=memories_store or InMemoryStore(),
                               embeddings=DeterministicFakeEmbedding(size=64), search_fn=FakeSearch())


def _query(name, settings):
    # con embeddings falsos, la consulta idéntica a la descripción indexada encuentra la herramienta
    from assistant.bigtool_agent import build_registry

    t = build_registry(None, settings, InMemoryStore())[name]
    return f"{t.name}: {t.description}"


def test_registro_tiene_40_o_mas_y_nada_peligroso(bt_settings, make_settings):
    from assistant.bigtool_agent import build_registry

    reg = build_registry(None, bt_settings, InMemoryStore())
    assert len(reg) >= 40 and "acos" in reg
    assert {"calculadora", "fecha_hora", "buscar_web", "guardar_recuerdo", "buscar_recuerdos",
            "investigador_profundo"} <= set(reg)
    assert "enviar_email_simulado" not in reg
    sin_demo = build_registry(None, make_settings(use_bigtool=True), InMemoryStore())
    assert "acos" not in sin_demo and "weather_forecast" in sin_demo  # extras siempre, demo solo con flag


def test_indice_encuentra_acos(bt_settings):
    from assistant.bigtool_agent import NAMESPACE, build_registry, build_tool_index

    reg = build_registry(None, bt_settings, InMemoryStore())
    index = build_tool_index(reg, bt_settings, DeterministicFakeEmbedding(size=64))
    assert index.search(NAMESPACE, query=_query("acos", bt_settings), limit=1)[0].key == "acos"


def test_flujo_retrieve_tools_y_acos(bt_settings):
    agent = _agent([
        tool_call("retrieve_tools", {"query": _query("acos", bt_settings)}, "r1"),
        tool_call("acos", {"x": 0.5}, "c1"),
        "El arcocoseno de 0.5 es 1.0472",
    ], bt_settings)
    ev = run_turn(agent, bt_settings, "calcula el arcocoseno de 0.5", uid())

    ends = {e["name"]: e for e in ev if e["type"] == "tool_end"}
    assert [e["name"] for e in ev if e["type"] == "tool_start"] == ["retrieve_tools", "acos"]
    assert "acos" in ends["retrieve_tools"]["output"]
    assert ends["acos"]["output"].startswith("1.047")
    assert ev[-1]["type"] == "done"


def test_conversacion_normal_sin_retrieve_y_tokens_uno_a_uno(bt_settings):
    agent = _agent(["Hola, estoy bien, gracias por preguntar"], bt_settings)
    ev = run_turn(agent, bt_settings, "hola", uid())

    assert "tool_start" not in types(ev)
    tokens = [e["text"] for e in ev if e["type"] == "token"]
    assert len(tokens) > 1  # llegan token a token, el adaptador PromptedModel no rompe el streaming
    assert "".join(tokens).strip() == "Hola, estoy bien, gracias por preguntar"


def test_herramienta_que_falla_devuelve_error_sin_tumbar_el_turno(bt_settings):
    agent = _agent([
        tool_call("retrieve_tools", {"query": _query("acos", bt_settings)}, "r1"),
        tool_call("acos", {"x": 2}, "c1"),  # fuera de dominio -> ValueError
        "No se puede: está fuera del dominio",
    ], bt_settings)
    ev = run_turn(agent, bt_settings, "acos de 2", uid())
    fin = next(e for e in ev if e["type"] == "tool_end" and e["name"] == "acos")
    assert fin["output"].startswith("Error en la herramienta (ValueError)")
    assert ev[-1]["type"] == "done"


def test_memoria_por_user_id_entre_threads(bt_settings, store):
    """user_id llega a las herramientas del grafo bigtool (sin context_schema) vía get_runtime().context."""
    u, otro = uid("u"), uid("u")
    guardar = _query("guardar_recuerdo", bt_settings)
    buscar = _query("buscar_recuerdos", bt_settings)

    a = _agent([tool_call("retrieve_tools", {"query": guardar}, "r1"),
                tool_call("guardar_recuerdo", {"texto": "Le gusta el cafe de olla"}, "g1"), "Anotado"],
               bt_settings, memories_store=store)
    run_turn(a, bt_settings, "me gusta el cafe de olla", uid(), user_id=u)

    def buscar_como(user):
        b = _agent([tool_call("retrieve_tools", {"query": buscar}, "r1"),
                    tool_call("buscar_recuerdos", {"consulta": "cafe"}, "b1"), "listo"],
                   bt_settings, memories_store=store)
        ev = run_turn(b, bt_settings, "que me gusta?", uid(), user_id=user)
        return next(e for e in ev if e["type"] == "tool_end" and e["name"] == "buscar_recuerdos")["output"]

    assert "cafe de olla" in buscar_como(u)
    assert buscar_como(otro) == "Sin recuerdos"
