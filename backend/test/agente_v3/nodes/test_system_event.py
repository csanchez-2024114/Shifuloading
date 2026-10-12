"""Aviso de la interfaz (system_event): no se trata como respuesta del usuario."""
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.shared.nodes.semantic_intake import semantic_intake_node


async def test_semantic_intake_does_not_classify_an_interface_notice_as_an_answer():
    state = {"system_event": True, "req_level": 1, "req_pending_questions": ["¿qué datos?"],
             "messages": [AIMessage("¿Qué datos quieres guardar?"), HumanMessage("[Aviso automático] Sheets conectada")]}
    out = await semantic_intake_node(state)  # sin LLM: el conftest bloquea llamadas reales
    assert out["req_flow_action"] == "system_event"
    assert "req_level" not in out and "req_pending_questions" not in out  # la pregunta pendiente sigue en pie
