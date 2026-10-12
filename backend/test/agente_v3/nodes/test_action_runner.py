"""action_runner (modo act): paralelo, dependencias, frenos y cerco, con LLM y funciones simuladas ($0)."""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

import app.functions.runner as fn_runner
from app.agent.shared.nodes import action_runner as ar
from app.agent.shared.nodes import response_evaluator as ev


class _Res:
    def __init__(self, ok, data=None, error=None):
        self.d = {"ok": ok, "data": data, "error": error}

    def model_dump(self, mode=None):
        return self.d


class _LLM:
    """Devuelve una AIMessage por vuelta, en orden."""
    def __init__(self, rounds):
        self.rounds = rounds  # misma lista: el nodo pide un LLM por vuelta

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, msgs, config=None):
        return self.rounds.pop(0) if self.rounds else AIMessage("listo")


def _call(name, i, **args):
    return {"name": ar._tool_name(name), "args": args, "id": f"c{i}"}


_WRITES = {  # id -> (verbo, confirmation_policy) de las escrituras falsas; todo lo demas es lectura
    "asana.tasks.create": ("create", "assume"),
    "asana.tasks.assign": ("update", "draft_and_confirm"),
    "clickup.tasks.create": ("create", "assume"),
}


def _fn(fid):
    verb, how = _WRITES.get(fid, ("read", "assume"))
    spec = SimpleNamespace(id=fid, app=fid.split(".")[0], description="d", input_schema={"type": "object"},
                           verb=SimpleNamespace(value=verb), confirmation_policy=SimpleNamespace(value=how))
    return SimpleNamespace(spec=spec, input_model=SimpleNamespace(model_validate=lambda a: a))


class _Col:
    def __init__(self):
        self.rows = []

    async def insert_one(self, doc):
        self.rows.append(doc)


class _Db:
    """Guarda lo que se inserta (action_log); las lecturas de Mongo estan simuladas en _setup."""
    def __init__(self):
        self.cols = {}

    def __getitem__(self, name):
        return self.cols.setdefault(name, _Col())


def _setup(monkeypatch, rounds, handler, policy=None):
    pool = {fid: _fn(fid) for fid in ("asana.tasks.list", "clickup.tasks.list", "asana.projects.search", *_WRITES)}

    async def connected(db, uid):
        return {"asana", "clickup"}

    async def search(p, q, apps, k=5):
        return list(p)

    async def personality():
        return {"action_policy": policy or {}}

    async def execute(fn, args, **kw):
        return await handler(fn.spec.id, args)

    monkeypatch.setattr(ar, "mongo_manager", SimpleNamespace(db=_Db()))
    monkeypatch.setattr(ar, "_connected", connected)
    monkeypatch.setattr(ar, "_pool", lambda apps: pool)
    monkeypatch.setattr(ar, "_search", search)
    monkeypatch.setattr(ar, "get_agent_personality", personality)
    monkeypatch.setattr(ar, "_llm", lambda model: _LLM(rounds))
    monkeypatch.setattr(fn_runner, "execute", execute)
    return {"user_id": "u1", "conversation_id": "c1", "messages": [HumanMessage("tareas de Asana y ClickUp")],
            "apps_involved": ["asana", "clickup"]}


async def _slow_ok(fid, args):
    await asyncio.sleep(0.2)
    return _Res(True, {"fid": fid})


async def test_independent_calls_run_in_parallel(monkeypatch):
    state = _setup(monkeypatch, [AIMessage("", tool_calls=[_call("asana.tasks.list", 1), _call("clickup.tasks.list", 2)])], _slow_ok)
    t0 = time.monotonic()
    out = await ar.action_runner_node(state)
    assert time.monotonic() - t0 < 0.35  # dos de 0.2 s en paralelo, no 0.4
    assert {r["fn"] for r in out["action_results"]} == {"asana.tasks.list", "clickup.tasks.list"}
    assert all(r["ok"] for r in out["action_results"]) and out["action_stop"] is None


async def test_semaphore_limits_parallelism(monkeypatch):
    state = _setup(monkeypatch, [AIMessage("", tool_calls=[_call("asana.tasks.list", 1), _call("clickup.tasks.list", 2)])],
                   _slow_ok, policy={"max_parallel": 1})
    t0 = time.monotonic()
    await ar.action_runner_node(state)
    assert time.monotonic() - t0 >= 0.4


async def test_one_failure_does_not_cancel_the_other(monkeypatch):
    async def handler(fid, args):
        if fid.startswith("asana"):
            raise RuntimeError("boom")
        return _Res(True, {"n": 1})
    state = _setup(monkeypatch, [AIMessage("", tool_calls=[_call("asana.tasks.list", 1), _call("clickup.tasks.list", 2)])], handler)
    out = await ar.action_runner_node(state)
    assert [r["fn"] for r in out["action_results"]] == ["clickup.tasks.list"]  # la otra se contesto con error al modelo


async def test_dependent_call_goes_in_next_round(monkeypatch):
    seen = []

    async def handler(fid, args):
        seen.append((fid, args))
        return _Res(True, {"gid": "P1"} if fid == "asana.projects.search" else {"tasks": []})
    state = _setup(monkeypatch, [AIMessage("", tool_calls=[_call("asana.projects.search", 1, text="Marketing")]),
                                 AIMessage("", tool_calls=[_call("asana.tasks.list", 2, project="P1")])], handler)
    await ar.action_runner_node(state)
    assert seen == [("asana.projects.search", {"text": "Marketing"}), ("asana.tasks.list", {"project": "P1"})]


async def test_repeated_call_stops(monkeypatch):
    same = [AIMessage("", tool_calls=[_call("asana.tasks.list", i)]) for i in range(3)]
    state = _setup(monkeypatch, same, _slow_ok)
    out = await ar.action_runner_node(state)
    assert out["action_stop"] == "repeated_call" and len(out["action_results"]) == 1


async def test_call_outside_the_fence_is_not_run(monkeypatch):
    ran = []

    async def handler(fid, args):
        ran.append(fid)
        return _Res(True)
    state = _setup(monkeypatch, [AIMessage("", tool_calls=[_call("hubspot.deals.search", 1)])], handler)
    out = await ar.action_runner_node(state)
    assert ran == [] and out["action_results"] == []


def test_pool_excludes_draft_and_deletes(monkeypatch):
    monkeypatch.delenv("SHIFU_FUNCTIONS_STATUSES", raising=False)
    assert ar._pool({"asana"}) == {}  # hoy todas estan en draft: en produccion no entra ninguna
    monkeypatch.setenv("SHIFU_FUNCTIONS_STATUSES", "active,draft")
    pool = ar._pool({"asana"})
    verbs = {f.spec.verb.value for f in pool.values()}
    assert {"read", "create", "update"} <= verbs and "delete" not in verbs
    assert all(f.spec.app == "asana" for f in pool.values())


def test_actions_backed_rejects_data_from_a_failed_app():
    results = [{"app": "asana", "ok": False}, {"app": "clickup", "ok": True}]
    assert not ev._actions_check(results, "Aquí tienes tus tareas de Asana: Factura, Reporte.")[0].passed
    assert ev._actions_check(results, "No pude leer Asana (error de permisos). En ClickUp tienes 3 tareas.")[0].passed
    assert ev._actions_check([{"app": "asana", "ok": True}], "Tus tareas de Asana: Factura.")[0].passed


# ── Fase 2: escrituras con confirmacion ──────────────────────────────────────────────────────────────────────────

from app.agent.shared.helpers import pending_confirm as pc  # noqa: E402
from app.agent.shared.nodes import semantic_intake as si  # noqa: E402
from app.agent.shifu_base_v1.graph.builder_standard import _route_from_intake  # noqa: E402


def _log(db):
    return db["action_log"].rows


async def test_assume_write_executes_now_and_is_logged(monkeypatch):
    ran = []

    async def handler(fid, args):
        ran.append(fid)
        return _Res(True, {"gid": "T1"})
    state = _setup(monkeypatch, [AIMessage("", tool_calls=[_call("asana.tasks.create", 1, title="Informe", api_token="x")])], handler)
    out = await ar.action_runner_node(state)
    assert ran == ["asana.tasks.create"] and "pending_action" not in out
    assert out["action_results"][0]["assumed"] is True and out["action_results"][0]["ok"]
    row = _log(ar.mongo_manager.db)[0]
    assert row["fn"] == "asana.tasks.create" and row["ok"] and row["via"] == "assumed" and row["conversation_id"] == "c1"
    assert row["args"]["api_token"] == "***" and row["args"]["title"] == "Informe"  # nunca credenciales en el registro
    assert "assumption" in ar.format_action_results(out["action_results"], None)


async def test_draft_and_confirm_write_is_held_not_executed(monkeypatch):
    ran = []

    async def handler(fid, args):
        ran.append(fid)
        return _Res(True, {"tasks": []})
    # la escritura pendiente no cuenta como falla; la lectura del mismo turno corre normal
    rounds = [AIMessage("", tool_calls=[_call("asana.tasks.assign", 1, task_gid="T1", assignee="ana"),
                                        _call("asana.tasks.list", 2)])]
    state = _setup(monkeypatch, rounds, handler)
    out = await ar.action_runner_node(state)
    assert ran == ["asana.tasks.list"]  # la escritura NO se ejecuto
    pend = out["pending_action"]
    assert pend["calls"] == [{"fn": "asana.tasks.assign", "app": "asana",
                              "args": {"task_gid": "T1", "assignee": "ana"}, "policy": "draft_and_confirm"}]
    assert pend["conversation_id"] == "c1" and pend["created_at"]
    held = [r for r in out["action_results"] if r.get("pending")]
    assert len(held) == 1 and out["action_stop"] is None
    assert _log(ar.mongo_manager.db) == []  # nada ejecutado, nada registrado
    block = ar.format_pending_block({**state, **out})
    assert "PENDING CONFIRMATION" in block and "asana.tasks.assign" in block
    assert "NOT EXECUTED" in ar.format_action_results(out["action_results"], None)


async def test_confirm_runs_exactly_the_stored_calls_without_llm(monkeypatch):
    ran = []

    async def handler(fid, args):
        ran.append((fid, args))
        return _Res(True, {"gid": "ok"})
    state = _setup(monkeypatch, [], handler)

    def no_llm(model):
        raise AssertionError("no LLM al confirmar")
    monkeypatch.setattr(ar, "_llm", no_llm)
    stored = {"calls": [{"fn": "asana.tasks.assign", "app": "asana", "args": {"task_gid": "T1", "assignee": "ana"},
                         "policy": "draft_and_confirm"}], "created_at": "2026-10-10T10:00:00+00:00", "conversation_id": "c1"}
    out = await ar.action_runner_node({**state, "pending_decision": "confirm", "pending_action": stored})
    assert ran == [("asana.tasks.assign", {"task_gid": "T1", "assignee": "ana"})]
    assert out["pending_action"] is None and out["action_results"][0]["ok"] and out["action_results"][0]["confirmed"]
    row = _log(ar.mongo_manager.db)[0]
    assert row["fn"] == "asana.tasks.assign" and row["via"] == "confirmed" and row["ok"] is True


async def test_confirm_with_disconnected_app_fails_and_still_clears(monkeypatch):
    state = _setup(monkeypatch, [], _slow_ok)

    async def connected(db, uid):
        return {"clickup"}  # asana ya no esta conectada
    monkeypatch.setattr(ar, "_connected", connected)
    everything = {fid: _fn(fid) for fid in _WRITES}
    monkeypatch.setattr(ar, "_pool", lambda apps: {k: v for k, v in everything.items() if v.spec.app in apps})
    stored = pc.build_pending([{"fn": "asana.tasks.assign", "app": "asana", "args": {}, "policy": "ask"}], "c1")
    out = await ar.action_runner_node({**state, "pending_decision": "confirm", "pending_action": stored})
    assert out["pending_action"] is None and out["action_results"][0]["ok"] is False
    assert out["action_results"][0]["error"]["code"] == "not_allowed"


async def test_change_replaces_pending_and_model_sees_the_old_one(monkeypatch):
    seen = {}
    rounds = [AIMessage("", tool_calls=[_call("asana.tasks.assign", 1, task_gid="T1", assignee="luis")])]
    state = _setup(monkeypatch, rounds, _slow_ok)

    class LLM(_LLM):
        async def ainvoke(self, msgs, config=None):
            seen["system"] = " ".join(str(m.content) for m in msgs)
            return await super().ainvoke(msgs, config)
    monkeypatch.setattr(ar, "_llm", lambda model: LLM(rounds))
    old = pc.build_pending([{"fn": "asana.tasks.assign", "app": "asana", "args": {"task_gid": "T1", "assignee": "ana"},
                             "policy": "draft_and_confirm"}], "c1")
    out = await ar.action_runner_node({**state, "pending_decision": "change", "pending_action": old})
    assert "assignee: ana" in seen["system"]  # argumentos uno por linea (describe_calls)
    assert out["pending_action"]["calls"][0]["args"]["assignee"] == "luis"


async def test_change_without_new_proposal_discards_the_old_one(monkeypatch):
    state = _setup(monkeypatch, [AIMessage("listo")], _slow_ok)
    old = pc.build_pending([{"fn": "asana.tasks.assign", "app": "asana", "args": {}, "policy": "ask"}], "c1")
    out = await ar.action_runner_node({**state, "pending_decision": "change", "pending_action": old})
    assert out["pending_action"] is None


async def test_digress_turn_leaves_pending_untouched(monkeypatch):
    state = _setup(monkeypatch, [AIMessage("listo")], _slow_ok)
    old = pc.build_pending([{"fn": "asana.tasks.assign", "app": "asana", "args": {}, "policy": "ask"}], "c1")
    out = await ar.action_runner_node({**state, "pending_decision": "digress", "pending_action": old})
    assert "pending_action" not in out  # sin la llave, el checkpoint conserva la pendiente


# semantic_intake: decide que hizo el usuario con la pendiente

def _pending(minutes_ago=1):
    p = pc.build_pending([{"fn": "asana.tasks.assign", "app": "asana", "args": {"task_gid": "T1"}, "policy": "ask"}], "c1")
    p["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    return p


def _intake_setup(monkeypatch, decision=None, ttl=None):
    calls = {"classified": 0, "intake": 0}

    async def classify(pending, text, last_assistant=""):
        calls["classified"] += 1
        return decision

    async def intake(state):
        calls["intake"] += 1
        return {"structured_prompt": None}

    async def personality():
        return {"action_policy": {"confirm_ttl_minutes": ttl} if ttl else {}}
    monkeypatch.setattr(si, "classify_pending", classify)
    monkeypatch.setattr(si, "_intake", intake)
    monkeypatch.setattr(si, "get_agent_personality", personality)
    return calls


def _istate(**kw):
    return {"messages": [HumanMessage("si, dale")], "pending_action": _pending(), **kw}


async def test_intake_confirm_goes_straight_to_action_runner(monkeypatch):
    calls = _intake_setup(monkeypatch, "confirm")
    out = await si.semantic_intake_node(_istate())
    assert out["pending_decision"] == "confirm" and "pending_action" not in out and calls["intake"] == 0
    assert _route_from_intake({**_istate(), **out}) == "action_runner"
    assert out["action_results"] is None  # se reinicia lo del turno anterior


async def test_intake_cancel_clears_pending_and_goes_to_responder(monkeypatch):
    _intake_setup(monkeypatch, "cancel")
    out = await si.semantic_intake_node(_istate())
    assert out["pending_decision"] == "cancel" and out["pending_action"] is None
    assert _route_from_intake({**_istate(), **out}) == "responder"
    assert "cancelled" in ar.format_pending_block({"pending_decision": "cancel"})


async def test_intake_change_routes_to_action_runner(monkeypatch):
    _intake_setup(monkeypatch, "change")
    out = await si.semantic_intake_node(_istate())
    assert _route_from_intake({**_istate(), **out}) == "action_runner"


async def test_intake_digress_runs_normal_flow_and_keeps_pending(monkeypatch):
    calls = _intake_setup(monkeypatch, "digress")
    out = await si.semantic_intake_node(_istate())
    assert calls["intake"] == 1 and out["pending_decision"] == "digress" and "pending_action" not in out


async def test_classifier_failure_is_not_a_confirmation(monkeypatch):
    class Boom:
        async def ainvoke(self, *a, **k):
            raise RuntimeError("openai caido")
    monkeypatch.setattr(pc, "_classifier", lambda: Boom())
    assert await pc.classify_pending(_pending(), "si") == "unclear"

    class Junk:
        async def ainvoke(self, *a, **k):
            return AIMessage("claro que si")  # no es JSON: tampoco cuenta como si
    monkeypatch.setattr(pc, "_classifier", lambda: Junk())
    assert await pc.classify_pending(_pending(), "si") == "unclear"

    class Yes:
        async def ainvoke(self, *a, **k):
            return AIMessage('{"decision": "confirm"}')
    monkeypatch.setattr(pc, "_classifier", lambda: Yes())
    assert await pc.classify_pending(_pending(), "si") == "confirm"


async def test_unclear_keeps_pending_and_reasks(monkeypatch):
    _intake_setup(monkeypatch, "unclear")
    out = await si.semantic_intake_node(_istate())
    assert out["pending_decision"] == "unclear" and "pending_action" not in out
    block = ar.format_pending_block({**_istate(), **out})
    assert "still open" in block and "asana.tasks.assign" in block


async def test_expired_pending_is_ignored(monkeypatch):
    calls = _intake_setup(monkeypatch, "confirm")
    out = await si.semantic_intake_node(_istate(pending_action=_pending(minutes_ago=61)))
    assert calls["classified"] == 0 and calls["intake"] == 1 and out["pending_decision"] is None
    # el ttl es dato: con 180 minutos la misma pendiente sigue vigente
    calls = _intake_setup(monkeypatch, "confirm", ttl=180)
    out = await si.semantic_intake_node(_istate(pending_action=_pending(minutes_ago=61)))
    assert calls["classified"] == 1 and out["pending_decision"] == "confirm"


async def test_system_event_does_not_trigger_the_classifier(monkeypatch):
    calls = _intake_setup(monkeypatch, "confirm")
    out = await si.semantic_intake_node(_istate(system_event=True))
    assert calls["classified"] == 0 and out["pending_decision"] is None


# evaluador: lo pendiente no esta hecho

def test_actions_check_rejects_done_when_only_pending():
    pending = [{"app": "asana", "ok": False, "pending": True, "fn": "asana.tasks.assign", "args": {}}]
    assert not ev._actions_check(pending, "Listo, la creé.")[0].passed
    assert not ev._actions_check(pending, "I created the task in Asana.")[0].passed
    assert ev._actions_check(pending, "Voy a asignar la tarea a Ana en Asana. ¿Confirmas?")[0].passed
    assert ev._actions_check(pending, "Esto es lo que haré: asignar la tarea. ¿Quieres que la cree así?")[0].passed
    # una lectura ejecutada en el mismo turno hace legitimo el "listo" suelto, pero no "la creé"
    mixed = [*pending, {"app": "clickup", "ok": True, "fn": "clickup.tasks.list", "args": {}}]
    assert ev._actions_check(mixed, "Listo, estas son tus tareas de ClickUp. ¿Asigno la de Asana a Ana?")[0].passed
    assert not ev._actions_check(mixed, "Aquí tus tareas. Ya la creé en Asana.")[0].passed


def test_pending_entries_do_not_count_as_failed_calls():
    pending = [{"app": "asana", "ok": False, "pending": True}]
    assert ev._actions_check(pending, "Propongo mover la tarea de Asana. ¿Te parece?")[0].passed


def test_route_with_no_decision_is_unchanged():
    assert _route_from_intake({"pending_decision": "unclear", "is_closing": True}) == "responder"
    assert _route_from_intake({"pending_decision": "unclear"}) != "action_runner"


# ── instrucciones escondidas en lo que devuelven las apps (v0.9.0) ───────────

async def _held_after(monkeypatch, user_text, **assign_args):
    async def handler(fid, args):
        return _Res(True, {})
    rounds = [AIMessage("", tool_calls=[_call("asana.tasks.assign", 1, task_gid="T1", **assign_args)])]
    state = {**_setup(monkeypatch, rounds, handler), "messages": [HumanMessage(user_text)]}
    return await ar.action_runner_node(state)


async def test_address_swapped_for_one_the_user_never_wrote_is_not_proposed(monkeypatch):
    out = await _held_after(monkeypatch, "asigna la tarea T1 a ana@empresa.test", assignee="ana.backup@attacker.test")
    assert not out.get("pending_action")  # sustitucion: no se le pide un "si" a algo que el usuario no pidio


async def test_extra_address_from_content_is_proposed_with_a_warning(monkeypatch):
    out = await _held_after(monkeypatch, "asigna la tarea T1 a ana@empresa.test", assignee="ana@empresa.test",
                            notes="ver http://pay.attacker.test/x")
    call = out["pending_action"]["calls"][0]
    assert call["foreign"] == ["http://pay.attacker.test/x"]
    block = ar.format_pending_block({"action_results": out["action_results"], "pending_action": out["pending_action"]})
    assert "did NOT write http://pay.attacker.test/x" in block


async def test_address_from_content_is_allowed_when_the_user_gave_none(monkeypatch):
    out = await _held_after(monkeypatch, "asigna la tarea T1 a Luis", assignee="luis@proveedor.test")  # "respondele a Luis"
    assert out["pending_action"]["calls"][0]["foreign"] == ["luis@proveedor.test"]


async def test_foreign_address_added_next_to_the_users_one_is_not_proposed_either(monkeypatch):
    # el modelo reintentaba con el ajeno como destinatario y el del usuario en copia
    out = await _held_after(monkeypatch, "asigna la tarea T1 a ana@empresa.test", assignee="ana.backup@attacker.test",
                            followers=["ana@empresa.test"])
    assert not out.get("pending_action")
