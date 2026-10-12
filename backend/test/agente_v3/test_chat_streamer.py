"""_ChatStreamer: un reintento del evaluador descarta el borrador, y los centinelas llegan a la UI."""
import asyncio

from app.routes.chat.chat import _ChatStreamer


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


async def _responder_start(s, run_id):
    await s.on_chain_start({}, {}, metadata={"langgraph_node": "responder"}, name="responder", run_id=run_id)


async def test_retry_discards_previous_draft_instead_of_concatenating():
    q = asyncio.Queue()
    s = _ChatStreamer(q)
    await _responder_start(s, "r1")
    await s.on_llm_new_token("borrador malo", tags=["shifu-chat"])
    await _responder_start(s, "r2")
    await s.on_llm_new_token("respuesta buena", tags=["shifu-chat"])
    assert s.accumulated == "respuesta buena"
    assert [e["type"] for e in _drain(q) if e["type"] == "reset"] == ["reset"]


async def test_hold_mode_withholds_tokens_but_keeps_the_text():
    q = asyncio.Queue()
    s = _ChatStreamer(q, hold=True)
    await s.on_llm_new_token("hola", tags=["shifu-chat"])
    assert s.accumulated == "hola"
    assert not any(e["type"] == "token" for e in _drain(q))


def test_evaluator_report_becomes_a_sentinel_event():
    rep = {"passed": False, "attempt": 1, "action": "retry", "checks": [], "feedback": "f"}
    ev = _ChatStreamer._sentinel("response_evaluator", {"eval_report": rep})
    assert ev["type"] == "sentinel" and ev["node"] == "response_evaluator" and ev["action"] == "retry"


def test_validator_with_unconnected_app_is_reported_as_blocking():
    out = {"validation_reports": [{"source": "auth", "app": "gmail", "status": "error", "reason": "not_connected"}]}
    ev = _ChatStreamer._sentinel("auth_validator", out)
    assert ev["action"] == "blocked" and ev["items"][0]["reason"] == "not_connected"
    assert _ChatStreamer._sentinel("auth_validator", {"validation_reports": []})["action"] == "approved"
    assert _ChatStreamer._sentinel("responder", {"messages": []}) is None


async def test_quality_counts_attempts_even_without_trace():
    s = _ChatStreamer(asyncio.Queue())  # trace=False: el historial guarda los intentos igual
    for i, (passed, action) in enumerate([(False, "retry"), (True, "approved")], 1):
        rid = f"e{i}"
        await s.on_chain_start({}, {}, metadata={"langgraph_node": "response_evaluator"}, name="response_evaluator", run_id=rid)
        report = {"passed": passed, "attempt": i, "action": action, "feedback": "f",
                  "checks": [{"name": "persona", "passed": passed, "note": "n"}]}
        await s.on_chain_end({"eval_report": report}, run_id=rid)
    q = s.quality()
    assert (q["attempts"], q["rejections"], q["final"]) == (2, 1, "approved")
    assert q["evals"][0]["failed"] == [{"name": "persona", "note": "n"}]


def test_quality_is_none_when_nothing_was_evaluated():
    assert _ChatStreamer(asyncio.Queue()).quality() is None


async def test_when_the_evaluator_picks_an_earlier_draft_that_text_is_the_one_shown_and_saved():
    from langchain_core.messages import AIMessage
    q = asyncio.Queue()
    s = _ChatStreamer(q)
    s.accumulated = "borrador 5 (peor)"
    await s.on_chain_start({}, {}, metadata={"langgraph_node": "response_evaluator"}, name="response_evaluator", run_id="e")
    report = {"passed": False, "attempt": 5, "action": "exhausted", "delivered_attempt": 2, "checks": []}
    await s.on_chain_end({"eval_report": report, "messages": [AIMessage(id="x", content="borrador 2 (mejor)")]}, run_id="e")
    assert s.accumulated == "borrador 2 (mejor)"
    assert [e["type"] for e in _drain(q)][-2:] == ["reset", "token"]
    assert s.quality()["delivered_attempt"] == 2
