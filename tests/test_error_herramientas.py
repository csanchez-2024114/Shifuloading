"""TOOL_ERROR_DETAIL_HIDDEN: con 0 (default) el modelo ve el detalle de la excepción de una herramienta, como siempre;
con 1 solo el tipo, y el detalle va al log. En el agente normal y en bigtool. Sin tokens."""
import logging

from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from conftest import _settings, fake_llm, run_turn, tool_call, uid

SECRET = "mongodb://usuario:clave@host-interno/db"


@tool("lookup_order", description="Looks up an order.")
def lookup_order(order_id: str) -> str:
    raise ValueError(f"no se pudo conectar a {SECRET}")


def _tool_output(settings):
    from assistant.core.agent import build_agent, run_config

    llm = fake_llm(tool_call("lookup_order", {"order_id": "7"}, "t1"), "No pude consultar el pedido.")
    agent = build_agent(llm, [lookup_order], settings, checkpointer=InMemorySaver())
    thread = uid()
    run_turn(agent, settings, "¿y mi pedido 7?", thread)
    msgs = agent.get_state(run_config(thread, settings)).values["messages"]
    return next(m.content for m in msgs if m.type == "tool")


def test_por_defecto_el_modelo_ve_el_detalle():
    out = _tool_output(_settings())
    assert out.startswith("Tool error (ValueError): ") and SECRET in out


def test_con_el_interruptor_solo_el_tipo_y_el_detalle_al_log(caplog):
    with caplog.at_level(logging.WARNING):
        out = _tool_output(_settings(tool_error_detail_hidden=True))
    assert out == "Tool error (ValueError). Try another approach."
    assert SECRET in caplog.text and "lookup_order" in caplog.text


def test_bigtool_igual(caplog):
    from assistant.core.extensions.bigtool import _seguro

    assert SECRET in _seguro(lookup_order).invoke({"order_id": "7"})
    with caplog.at_level(logging.WARNING):
        assert _seguro(lookup_order, hidden=True).invoke({"order_id": "7"}) == \
            "Tool error (ValueError). Try another approach."
    assert SECRET in caplog.text
