"""Regresion (corrida v064_wf): T1 "crear workflow: cada lunes ... hoja ... Gmail" -> T2 "si, asi esta bien".
El nivel 1 hacia 3 preguntas genericas aunque el mensaje ya traia horario, apps y resultado; el "si" las consumia una a
una sin avanzar, y el responder decia "conecta Google Sheets" porque platform_context no veia la cuenta conectada."""
import os
from unittest.mock import AsyncMock, MagicMock


from langchain_core.messages import AIMessage, HumanMessage

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")

from app.agent.shared.helpers import platform_context as pc  # noqa: E402
from app.agent.shared.nodes import semantic_intake as si  # noqa: E402
from app.agent.shifu_base_v1.graph import req_nodes  # noqa: E402
from app.agent.shifu_base_v1.graph.builder_standard import _route_from_intake  # noqa: E402

T1 = ("quiero crear un workflow: cada lunes a las 9 de la manana lee la hoja "
      "https://docs.google.com/spreadsheets/d/abc123/edit y mandame el total por Gmail a yo@ejemplo.com")


def _llm(content):
    return MagicMock(ainvoke=AsyncMock(return_value=AIMessage(content=content)))


async def test_t2_yes_continues_the_flow_and_routes_to_req_investigator(monkeypatch):
    # estado tras T1 con el flujo activo y una pregunta pendiente
    monkeypatch.setattr(si, "_flow_gate_llm", _llm('{"action": "continue"}'))
    state = {"req_level": 1, "req_level_entered": 1, "req_pending_questions": ["q2"],
             "messages": [HumanMessage(T1), AIMessage("Que apps usas?"), HumanMessage("si, asi esta bien")]}
    out = await si.semantic_intake_node(state)
    assert out["req_flow_action"] == "continue"
    assert _route_from_intake({**state, **out}) == "req_investigator"


async def test_flow_gate_prompt_says_declining_a_suggestion_is_not_cancel(monkeypatch):
    llm = _llm('{"action": "continue"}')
    monkeypatch.setattr(si, "_flow_gate_llm", llm)
    await si._classify_flow_action({"messages": [AIMessage("Quieres ver un ejemplo?"), HumanMessage("no, asi esta bien")]})
    assert "NOT cancel" in llm.ainvoke.call_args.args[0][0].content


async def test_platform_context_marks_apps_whose_account_the_flow_validated(monkeypatch):
    # el flujo de requisitos no pasa por auth_validator: user_connected_apps llega vacio, los reportes si traen la cuenta
    monkeypatch.setattr(pc, "_catalog", AsyncMock(return_value=[
        {"name": "Gmail", "nameApi": "gmail", "category": "Google Suite"},
        {"name": "Asana", "nameApi": "asana", "category": "Project Management"}]))
    monkeypatch.setattr(pc, "_functions", lambda: [])
    ctx = await pc.build_platform_context({
        "messages": [], "structured_prompt": "x", "user_connected_apps": None,
        "validation_reports": [{"source": "auth", "app": "gmail", "status": "ok"},
                               {"source": "auth", "app": "asana", "status": "missing"}]})
    assert "Gmail*" in ctx and "Asana*" not in ctx


async def test_gate_sees_the_real_flow_question_not_only_the_paraphrase(monkeypatch):
    # corrida v064_wf2: el responder sustituyo la pregunta del nivel 4 por otra cosa y "no, asi esta bien" se tomo por cancelar
    llm = _llm('{"action": "continue"}')
    monkeypatch.setattr(si, "_flow_gate_llm", llm)
    state = {"structured_prompt": "¿Corremos la prueba final y lo activamos?",
             "messages": [AIMessage("Ve a la seccion de conexiones"), HumanMessage("no, asi esta bien, gracias")]}
    assert await si._classify_flow_action(state) == "continue"
    assert "prueba final" in llm.ainvoke.call_args.args[0][1].content


async def test_platform_context_tells_the_model_not_to_ask_to_connect_a_connected_app(monkeypatch):
    monkeypatch.setattr(pc, "_catalog", AsyncMock(return_value=[
        {"name": "Gmail", "nameApi": "gmail", "category": "Google Suite"}]))
    monkeypatch.setattr(pc, "_functions", lambda: [])
    ctx = await pc.build_platform_context({"messages": [], "structured_prompt": "send gmail", "apps_involved": ["gmail"],
                                           "user_connected_apps": {"gmail": ["a@b.c"]}})
    assert "ALREADY connected" in ctx


async def test_gate_cancel_at_confirm_is_handled_by_the_flow_not_by_the_generic_cancel(monkeypatch):
    # En CONFIRM ya hay un borrador guardado: "no, mejor no" debe llegar a req_investigator para descartarlo y decirle al
    # usuario que no se activo nada, no limpiar el estado y dejar el borrador huerfano.
    monkeypatch.setattr(si, "_flow_gate_llm", _llm('{"action": "cancel"}'))
    state = {"req_level": 4, "structured_prompt": "¿Lo activo así?",
             "messages": [AIMessage("Plan... ¿Lo activo así?"), HumanMessage("no, mejor no")]}
    out = await si.semantic_intake_node(state)
    assert out["req_flow_action"] == "continue" and "req_level" not in out and out["req_relay"] is False
    assert _route_from_intake({**state, **out}) == "req_investigator"


async def test_gate_cancel_while_gathering_still_clears_the_flow(monkeypatch):
    monkeypatch.setattr(si, "_flow_gate_llm", _llm('{"action": "cancel"}'))
    state = {"req_level": 1, "messages": [AIMessage("¿Qué hoja?"), HumanMessage("cancela todo")]}
    out = await si.semantic_intake_node(state)
    assert out["req_level"] is None
