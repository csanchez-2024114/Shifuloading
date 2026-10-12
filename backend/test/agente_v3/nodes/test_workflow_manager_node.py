"""workflow_manager (intent "command"): el modelo llama herramientas locales; forma de action_results, frenos y ruta. Sin red."""
from datetime import datetime, timezone
from types import SimpleNamespace

from bson import ObjectId
from langchain_core.messages import AIMessage, HumanMessage
from mongomock_motor import AsyncMongoMockClient

from app.agent.shared.nodes import action_runner as ar
from app.agent.shared.nodes import response_evaluator as ev
from app.agent.shared.nodes import workflow_manager as wm
from app.agent.shifu_base_v1.graph.builder_standard import _route_after_fan_in, v3_graph
from app.agent.shifu_base_v1.graph.node_labels import get_node_label

USER = str(ObjectId())


class _LLM:
    """Devuelve una AIMessage por vuelta, en orden (y recuerda lo que vio)."""
    def __init__(self, rounds):
        self.rounds, self.seen = rounds, []

    def bind_tools(self, tools):
        self.tools = [t["function"]["name"] for t in tools]
        return self

    async def ainvoke(self, msgs, config=None):
        self.seen.append(msgs)
        return self.rounds.pop(0) if self.rounds else AIMessage("listo")


def _call(name, i, **args):
    return {"name": name, "args": args, "id": f"c{i}"}


async def _setup(monkeypatch, rounds, status="active"):
    db = AsyncMongoMockClient()["wm_node_test"]
    res = await db["workflows"].insert_one({"user_id": USER, "name": "Reporte", "status": status, "steps": [],
                                            "updated_at": datetime.now(timezone.utc)})
    llm = _LLM(rounds)
    monkeypatch.setattr(wm, "mongo_manager", SimpleNamespace(db=db))
    monkeypatch.setattr(wm, "_llm", lambda model: llm)
    state = {"user_id": USER, "conversation_id": "c1", "user_timezone": "America/Mexico_City",
             "messages": [HumanMessage("pausa mi reporte")]}
    return state, str(res.inserted_id), db, llm


def _made(out):
    """Las llamadas que hizo el modelo, sin la lista que el nodo agrega solo."""
    return [r for r in out["action_results"] if not r.get("auto")]


async def test_writes_action_results_with_the_action_runner_shape(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [])
    llm.rounds = [AIMessage("", tool_calls=[_call("list_workflows", 1)]),
                  AIMessage("", tool_calls=[_call("pause_workflow", 2, workflow_id=wf)])]
    out = await wm.workflow_manager_node(state)
    assert out["action_stop"] is None
    first, second = _made(out)
    assert set(first) == {"fn", "app", "args", "ok", "data", "error", "ms"}  # las mismas llaves que action_runner
    assert first["fn"] == "shifu.workflows.list_workflows" and first["app"] == "shifu" and first["ok"] is True
    assert isinstance(first["data"], str) and "Reporte" in first["data"] and first["error"] is None
    assert second["fn"] == "shifu.workflows.pause_workflow" and second["args"] == {"workflow_id": wf} and second["ok"]
    assert (await db["workflows"].find_one({"_id": ObjectId(wf)}))["status"] == "paused"
    assert "list_workflows" in llm.tools and "delete_workflow" in llm.tools and len(llm.tools) == 7


async def test_a_failed_call_is_recorded_with_its_error_and_the_responder_block_reads_it(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [AIMessage("", tool_calls=[_call("get_workflow", 1, workflow_id=str(ObjectId()))])])
    out = await wm.workflow_manager_node(state)
    r = _made(out)[0]
    assert r["ok"] is False and r["data"] is None and r["error"]["code"] == "not_found"
    block = ar.format_action_results(out["action_results"], out["action_stop"])
    assert "shifu.workflows.get_workflow" in block and "FAILED (not_found)" in block


async def test_repeated_identical_call_stops(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [])
    llm.rounds = [AIMessage("", tool_calls=[_call("list_workflows", i)]) for i in range(3)]
    out = await wm.workflow_manager_node(state)
    assert out["action_stop"] == "repeated_call" and len(_made(out)) == 1


async def test_more_than_8_calls_stops_before_running_the_extra_ones(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [])
    llm.rounds = [AIMessage("", tool_calls=[_call("get_workflow", i, workflow_id=f"{i:024x}") for i in range(5)]),
                  AIMessage("", tool_calls=[_call("get_workflow", 9 + i, workflow_id=f"{i + 10:024x}") for i in range(5)])]
    out = await wm.workflow_manager_node(state)
    assert out["action_stop"] == "limit" and len(_made(out)) == 5


async def test_stops_at_4_rounds(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [])
    llm.rounds = [AIMessage("", tool_calls=[_call("get_workflow", i, workflow_id=f"{i:024x}")]) for i in range(6)]
    out = await wm.workflow_manager_node(state)
    assert out["action_stop"] == "limit" and len(_made(out)) == 4 and len(llm.rounds) == 2


async def test_unknown_tool_and_bad_args_do_not_crash(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [AIMessage("", tool_calls=[
        _call("drop_database", 1), _call("run_now", 2)])])  # run_now sin workflow_id
    out = await wm.workflow_manager_node(state)
    assert [r["error"]["code"] for r in _made(out)] == ["not_allowed", "not_found"]


async def test_no_call_means_no_results_and_no_user_means_nothing_runs(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [AIMessage("hay dos con ese nombre")])
    out = await wm.workflow_manager_node(state)  # sin llamadas igual lleva la lista: el responder explica con el estado real
    assert out["action_stop"] is None and [r["fn"] for r in out["action_results"]] == ["shifu.workflows.list_workflows"]
    assert out["action_results"][0]["auto"] and _made(out) == []
    assert await wm.workflow_manager_node({**state, "user_id": None}) == {"action_results": []}


async def test_the_model_sees_the_recent_conversation_to_resolve_it(monkeypatch):
    state, wf, db, llm = await _setup(monkeypatch, [AIMessage("ok")])
    state["messages"] = [HumanMessage("que workflows tengo"), AIMessage("Tienes Reporte."), HumanMessage("pausalo")]
    await wm.workflow_manager_node(state)
    text = " ".join(str(m.content) for m in llm.seen[0])
    assert "Tienes Reporte." in text and "pausalo" in text and "DATA" in text  # el prompt trata los resultados como datos


# ── Grafo ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _intent(intent):
    return {"semantic_intake_debug": {"detected_intent": intent}}


def test_command_intent_routes_to_the_node_and_the_others_are_unchanged():
    assert _route_after_fan_in(_intent("command")) == "workflow_manager"
    assert _route_after_fan_in(_intent("act")) == "action_runner"
    assert _route_after_fan_in(_intent("question")) == "responder"
    assert _route_after_fan_in({}) == "responder"


def test_node_is_in_the_compiled_graph_and_has_a_label():
    assert "workflow_manager" in v3_graph.get_graph().nodes
    assert get_node_label("workflow_manager") == "Revisando tus workflows..."


# ── Responder y juez con la app "shifu" ───────────────────────────────────────────────────────────────────────

def test_evaluator_accepts_an_honest_reply_when_a_shifu_call_failed_and_flags_a_false_one():
    failed = [{"fn": "shifu.workflows.pause_workflow", "app": "shifu", "args": {}, "ok": False, "data": None,
               "error": {"code": "not_found", "message": "x"}, "ms": 1}]
    assert ev._actions_check(failed, "No encontré ese workflow, ¿cuál de ellos quieres pausar?")[0].passed
    assert not ev._actions_check(failed, "Listo, Shifu pausó tu workflow.")[0].passed
