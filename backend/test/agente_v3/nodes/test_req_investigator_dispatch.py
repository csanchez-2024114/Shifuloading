"""Unit tests for req_investigator_node's dispatch/cascade logic — pure control
flow, stage functions are mocked so no DB/LLM calls happen. Etapas: 1 = GATHER, 4 = CONFIRM."""

import pytest

import app.agent.shifu_base_v1.graph.req_nodes as req_nodes
from app.agent.shifu_base_v1.graph.req_nodes import req_investigator_node


@pytest.mark.asyncio
async def test_pops_pending_question_without_calling_any_level(monkeypatch):
    async def _boom(_state):
        raise AssertionError("stage function must not run while a question is queued")

    monkeypatch.setattr(req_nodes, "_LEVEL_FUNCS", {1: _boom})
    state = {"req_level": 1, "req_pending_questions": ["q1", "q2"]}
    result = await req_investigator_node(state)
    # req_relay: el responder entrega la pregunta tal cual
    assert result == {"req_pending_questions": ["q2"], "structured_prompt": "q1", "req_relay": True}


@pytest.mark.asyncio
async def test_pops_last_pending_question_clears_queue_to_none(monkeypatch):
    monkeypatch.setattr(req_nodes, "_LEVEL_FUNCS", {})
    state = {"req_level": 1, "req_pending_questions": ["only"]}
    result = await req_investigator_node(state)
    assert result == {"req_pending_questions": None, "structured_prompt": "only", "req_relay": True}


@pytest.mark.asyncio
async def test_single_level_with_prompt_stops_immediately_and_marks_relay(monkeypatch):
    async def level_1(_state):
        return {"structured_prompt": "asking something", "req_level_entered": 1}

    monkeypatch.setattr(req_nodes, "_LEVEL_FUNCS", {1: level_1})
    result = await req_investigator_node({"req_level": 1})
    assert result == {"structured_prompt": "asking something", "req_level_entered": 1, "req_relay": True}


@pytest.mark.asyncio
async def test_silent_transition_cascades_into_next_stage_same_turn(monkeypatch):
    """CONFIRM que recibe un cambio vuelve a GATHER sin mensaje propio: el despachador debe correr GATHER en la misma
    llamada, no devolver un turno en blanco."""
    calls = []

    async def confirm(_state):
        calls.append(4)
        return {"req_level": 1, "req_adjustment": "a las 10"}

    async def gather(state):
        calls.append(1)
        assert state["req_adjustment"] == "a las 10"  # lo que dejo la etapa anterior llega a la siguiente
        return {"structured_prompt": "plan nuevo", "req_level": 4}

    monkeypatch.setattr(req_nodes, "_LEVEL_FUNCS", {1: gather, 4: confirm})
    result = await req_investigator_node({"req_level": 4})
    assert calls == [4, 1]
    assert result["structured_prompt"] == "plan nuevo" and result["req_level"] == 4 and result["req_relay"] is True


@pytest.mark.asyncio
async def test_cascade_stops_once_req_level_is_none_even_without_prompt(monkeypatch):
    async def confirm(_state):
        return {"req_level": None, "req_deployed": True}

    monkeypatch.setattr(req_nodes, "_LEVEL_FUNCS", {4: confirm})
    result = await req_investigator_node({"req_level": 4})
    assert result == {"req_level": None, "req_deployed": True}  # sin mensaje no hay relay


@pytest.mark.asyncio
async def test_cascade_is_bounded(monkeypatch):
    async def loop(_state):
        return {"req_level": 1}

    monkeypatch.setattr(req_nodes, "_LEVEL_FUNCS", {1: loop})
    assert await req_investigator_node({"req_level": 1}) == {"req_level": 1}


@pytest.mark.asyncio
async def test_unknown_level_clears_flow_state():
    result = await req_investigator_node({"req_level": 99})
    assert result == {
        "req_level": None, "req_pending_questions": None, "req_level_entered": None,
    }
