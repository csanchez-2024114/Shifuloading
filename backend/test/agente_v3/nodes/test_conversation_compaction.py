"""Compactacion de la conversacion: resumen rodante + ventana. Todo con mocks, sin OpenAI."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.shared.memory import conversation_compactor as cc
from app.agent.shared.nodes import memory_updater, response_evaluator as ev, responder
from app.agent.shared.nodes.semantic_intake import _EMPTY_RESULT


def _chat(n):
    """n mensajes alternados: m0 usuario, m1 asistente, ..."""
    return [(HumanMessage if i % 2 == 0 else AIMessage)(f"m{i}") for i in range(n)]


@pytest.fixture
def updater(monkeypatch):
    """memory_updater con politica configurable y un compactor falso que registra lo que recibe."""
    calls = []

    def use(compaction=None, result="RESUMEN"):
        async def personality():
            return {"memory_policy": {"compaction": compaction} if compaction is not None else {}}

        async def fake_compact(previous, folded, model):
            calls.append({"previous": previous, "folded": [m.content for m in folded], "model": model})
            return result(previous) if callable(result) else result
        monkeypatch.setattr(memory_updater, "get_agent_personality", personality)
        monkeypatch.setattr(memory_updater, "compact", fake_compact)
        return calls
    return use


# ── Disparador (memory_updater._compact) ──────────────────────────────────────────

async def test_no_compaction_under_the_threshold(updater):
    calls = updater()
    assert await memory_updater._compact({"messages": _chat(20)}) == {}  # 20 no supera max_messages=20
    assert calls == []


async def test_compaction_folds_the_slice_leaving_the_window(updater):
    calls = updater()
    out = await memory_updater._compact({"messages": _chat(21)})
    assert calls[0]["folded"] == [f"m{i}" for i in range(9)]  # 21 - keep(12) = 9 mensajes salen
    assert calls[0]["previous"] == "" and calls[0]["model"] == "gpt-4o-mini"
    assert out == {"conversation_summary": "RESUMEN", "summary_upto": 9}


async def test_second_compaction_merges_with_the_previous_summary(updater):
    calls = updater(result=lambda prev: prev + "+NUEVO")
    # ya hay resumen hasta 9; con 30 mensajes quedan 21 sin plegar (> 20) y se pliegan 9..17
    out = await memory_updater._compact({"messages": _chat(30), "conversation_summary": "VIEJO", "summary_upto": 9})
    assert calls[0]["previous"] == "VIEJO"
    assert calls[0]["folded"] == [f"m{i}" for i in range(9, 18)]
    assert out == {"conversation_summary": "VIEJO+NUEVO", "summary_upto": 18}


async def test_compactor_failure_keeps_the_previous_summary_and_does_not_advance(updater):
    updater(result=lambda prev: prev)  # compact() devuelve el previo cuando falla
    out = await memory_updater._compact({"messages": _chat(30), "conversation_summary": "VIEJO", "summary_upto": 9})
    assert out == {}  # el estado conserva "VIEJO"/9; el turno siguiente reintenta


async def test_compaction_never_breaks_the_turn(updater, monkeypatch):
    updater()
    monkeypatch.setattr(memory_updater, "compact", AsyncMock(side_effect=RuntimeError("boom")))
    assert await memory_updater._compact({"messages": _chat(30)}) == {}


async def test_policy_is_data_and_system_events_are_skipped(updater):
    calls = updater({"max_messages": 4, "keep_messages": 2, "model": "otro-modelo"})
    out = await memory_updater._compact({"messages": _chat(6)})
    assert out["summary_upto"] == 4 and calls[0]["model"] == "otro-modelo"
    assert await memory_updater._compact({"messages": _chat(6), "system_event": True}) == {}
    updater({"enabled": False})
    assert await memory_updater._compact({"messages": _chat(40)}) == {}


async def test_only_human_and_ai_messages_are_counted(updater):
    calls = updater()
    msgs = _chat(21)
    msgs.insert(3, SystemMessage("ruido"))
    out = await memory_updater._compact({"messages": msgs})
    assert out["summary_upto"] == 9 and "ruido" not in calls[0]["folded"]


# ── Compactor ─────────────────────────────────────────────────────────────────────

async def test_compact_returns_previous_summary_when_the_llm_fails(monkeypatch):
    monkeypatch.setattr(cc.ChatOpenAI, "ainvoke", AsyncMock(side_effect=RuntimeError("sin red")))
    assert await cc.compact("VIEJO", _chat(3), "gpt-4o-mini") == "VIEJO"


async def test_compact_sends_previous_summary_and_messages_with_its_tag(monkeypatch):
    llm = AsyncMock(return_value=AIMessage("- nuevo resumen"))
    monkeypatch.setattr(cc.ChatOpenAI, "ainvoke", llm)
    assert await cc.compact("VIEJO", _chat(2), "gpt-4o-mini") == "- nuevo resumen"
    sent, kwargs = llm.await_args.args[-1], llm.await_args.kwargs
    assert "VIEJO" in sent[1][1] and "USER: m0" in sent[1][1] and "ASSISTANT: m1" in sent[1][1]
    assert kwargs["config"] == {"tags": ["conversation_compactor"]}


# ── Responder: resumen + ventana ──────────────────────────────────────────────────

@pytest.fixture
def sent_to_llm(monkeypatch):
    monkeypatch.setattr(responder, "get_agent_identity", AsyncMock(return_value={}))
    monkeypatch.setattr(responder, "get_agent_personality", AsyncMock(return_value={}))
    monkeypatch.setattr(responder, "build_system_messages", MagicMock(return_value=[SystemMessage("You are Shifu.")]))
    llm = AsyncMock(return_value=AIMessage("ok"))
    monkeypatch.setattr(responder.ChatOpenAI, "ainvoke", llm)

    async def run(state):
        await responder.responder_node({"apps_involved": [], "effort_level": "low", "model_name": "gpt-4o-mini", **state})
        return llm.await_args.args[0]
    return run


async def test_responder_sends_summary_plus_window_only(sent_to_llm):
    msgs = _chat(25)  # m24 es el mensaje actual del usuario
    sent = await sent_to_llm({"messages": msgs, "conversation_summary": "El usuario se llama Ana.", "summary_upto": 13})
    texts = [m.content for m in sent]
    assert any("Earlier in this conversation" in t and "El usuario se llama Ana." in t for t in texts)
    assert [t for t in texts if t.startswith("m")] == [f"m{i}" for i in range(13, 25)]
    assert sent[-1].content == "m24"


async def test_responder_never_drops_the_current_user_message(sent_to_llm):
    msgs = _chat(25)
    sent = await sent_to_llm({"messages": msgs, "conversation_summary": "S", "summary_upto": 99})  # indice fuera de rango
    assert sent[-1].content == "m24" and isinstance(sent[-1], HumanMessage)


async def test_responder_without_summary_sends_the_whole_history(sent_to_llm):
    sent = await sent_to_llm({"messages": _chat(25)})
    assert [m.content for m in sent if m.content.startswith("m")] == [f"m{i}" for i in range(25)]
    assert not any("Earlier in this conversation" in str(m.content) for m in sent)


# ── Juez ──────────────────────────────────────────────────────────────────────────

async def test_judge_body_contains_the_summary_before_the_history(monkeypatch):
    monkeypatch.setattr(ev, "get_agent_personality", AsyncMock(return_value={
        "quality_control": {"checks": [{"name": "no_fabrication", "criterion": "x"}]}}))
    monkeypatch.setattr(ev, "build_platform_context", AsyncMock(return_value=""))
    monkeypatch.setattr(ev, "get_agent_identity", AsyncMock(return_value={}))
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=ev._Eval(checks=[ev._Check(name="no_fabrication", passed=True, note="")], feedback=""))
    monkeypatch.setattr(ev, "_llm", llm)
    state = {"messages": [HumanMessage("¿cómo me llamo?"), AIMessage("Ana")], "eval_retry_count": 0,
             "conversation_summary": "- El usuario se llama Ana."}
    await ev.response_evaluator_node(state)
    sent = llm.ainvoke.await_args.args[0][1]["content"]
    assert "EARLIER IN THIS CONVERSATION (summary):\n- El usuario se llama Ana." in sent
    assert sent.index("EARLIER IN THIS CONVERSATION (summary)") < sent.index("CONVERSATION SO FAR")


# ── Estado ────────────────────────────────────────────────────────────────────────

def test_semantic_intake_does_not_reset_the_summary_fields():
    # viven en el checkpoint: si el reinicio por turno las incluyera, el resumen se perderia cada turno
    assert "conversation_summary" not in _EMPTY_RESULT and "summary_upto" not in _EMPTY_RESULT
