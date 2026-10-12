"""Unit tests for _route_from_intake conditional edge in graph.py."""

from app.agent.shifu_base_v1.graph.builder_standard import _route_from_intake


def _state(**overrides):
    return {"is_closing": False, "account_selection_resolved": False, **overrides}


def test_is_closing_bypasses_fan_out():
    assert _route_from_intake(_state(is_closing=True)) == "responder"


def test_account_selection_resolved_bypasses_fan_out():
    assert _route_from_intake(_state(account_selection_resolved=True)) == "responder"


def test_both_false_sends_to_fan_out():
    result = _route_from_intake(_state())
    assert set(result) == {
        "catalog_checker", "auth_validator", "tavily_subgraph", "document_analyzer",
    }


def test_closing_and_resolved_both_true_still_responder():
    result = _route_from_intake(_state(is_closing=True, account_selection_resolved=True))
    assert result == "responder"


def test_req_level_continue_routes_to_investigator():
    result = _route_from_intake(_state(req_level=2, req_flow_action="continue"))
    assert result == "req_investigator"


def test_req_level_digress_bypasses_investigator_for_fan_out():
    """digress must NOT reach req_investigator — req_level stays set (paused)
    but this turn answers the actual question via the normal pipeline."""
    result = _route_from_intake(_state(req_level=2, req_flow_action="digress"))
    assert result != "req_investigator"
    assert set(result) == {
        "catalog_checker", "auth_validator", "tavily_subgraph", "document_analyzer",
    }


def test_req_level_cleared_after_cancel_routes_to_fan_out():
    """cancel already clears req_level in semantic_intake_node before this runs —
    confirms the router doesn't need req_flow_action to handle that case."""
    result = _route_from_intake(_state(req_level=None, req_flow_action="cancel"))
    assert result != "req_investigator"



def test_an_interface_notice_after_an_open_question_gets_no_reply():
    # Chat por turnos: si el agente pregunto algo, el aviso "cuenta conectada" no genera otro mensaje (antes salian dos
    # mensajes seguidos del agente) y tampoco avanza el flujo de requisitos
    from langchain_core.messages import AIMessage, HumanMessage
    msgs = [AIMessage("Conecta Sheets. ¿Qué datos quieres guardar?"), HumanMessage("[Aviso] Sheets conectada")]
    assert _route_from_intake(_state(system_event=True, req_level=2, messages=msgs)) == "end"


def test_an_interface_notice_without_an_open_question_lets_the_agent_resume():
    from langchain_core.messages import AIMessage, HumanMessage
    msgs = [AIMessage("Conecta Sheets y lo dejamos listo."), HumanMessage("[Aviso] Sheets conectada")]
    assert _route_from_intake(_state(system_event=True, req_level=2, messages=msgs)) == "responder"
