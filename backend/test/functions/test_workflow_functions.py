"""Workflows que corren pasos por el sistema nuevo de funciones (function_id), sin Mongo real ni red.

Camino simulado de punta a punta por el ejecutor real; el camino viejo (BigTools) sigue para pasos sin function_id.
"""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI
from functions_helpers import DESC
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel, Field

from app.database import get_current_user, get_db
from app.functions import registry, runner
from app.functions.registry import function, isolated_registry, load_all, register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType, Verb
from app.routes.workflows import run as run_routes
from app.services.workflow_run_service import create_run, claim_run_by_id, get_run
from app.workers.workflow_executor import WorkflowExecutor

USER = str(ObjectId())


@pytest.fixture(scope="module", autouse=True)
def _loaded():
    # Antes de cualquier isolated_registry: si no, los modulos se importarian dentro y se perderian al salir.
    load_all()


@pytest.fixture
def db():
    return AsyncMongoMockClient()["wf_test"]


@pytest.fixture
def seen(monkeypatch):
    """Registra los argumentos con que el ejecutor llama al runner (y delega en el real)."""
    calls = []
    real = runner.execute

    async def spy(fn, raw_input, **kw):
        calls.append({"id": fn.spec.id, "args": raw_input, "simulate": kw.get("simulate"), "account_id": kw.get("account_id")})
        return await real(fn, raw_input, **kw)

    monkeypatch.setattr(runner, "execute", spy)
    return calls


def two_steps():
    return [
        {"order": 1, "name": "Quien soy", "app": "asana", "action": "users.get", "function_id": "asana.users.get", "config": {"nodeType": "action"}},
        {"order": 2, "name": "Favoritos", "app": "asana", "action": "users.list_favorites", "function_id": "asana.users.list_favorites",
         "config": {"nodeType": "action", "workspace": "{{step_1.account_id}}"}},
    ]


async def run_steps(db, steps, simulate=True, user=USER):
    run_id = await create_run("wf1", "Mi workflow", user, "a@b.test", steps, db, simulate=simulate)
    run = await claim_run_by_id(run_id, db)
    await WorkflowExecutor(run, db).execute()
    return await get_run(run_id, db)


async def test_create_run_copies_all_step_fields(db):
    steps = [{"order": 1, "name": "x", "function_id": "asana.users.get", "type": "condition", "then_step": 3, "max_retries": 2,
              "compensation_action": {"action": "undo"}, "config": {"a": 1}}]
    run = await get_run(await create_run("wf", "n", USER, "a@b.test", steps, db, simulate=True), db)
    s = run["steps"][0]
    assert s["function_id"] == "asana.users.get" and s["type"] == "condition" and s["then_step"] == 3
    assert s["max_retries"] == 2 and s["compensation_action"] == {"action": "undo"}
    assert s["status"] == "pending" and run["simulate"] is True


async def test_old_step_docs_still_create_runs(db):
    run = await get_run(await create_run("wf", "n", USER, "a@b.test", [{"name": "viejo", "app": "gmail", "action": "x"}], db), db)
    assert run["steps"][0]["order"] == 1 and "function_id" not in run["steps"][0] and run["simulate"] is False


async def test_two_function_steps_run_simulated_and_template_resolves(db, seen):
    run = await run_steps(db, two_steps())
    assert run["status"] == "completed"
    assert [s["status"] for s in run["steps"]] == ["completed", "completed"]
    # {{step_1.account_id}} salio del ejemplo del paso 1 y nodeType no llego a la funcion
    assert seen[1]["args"] == {"workspace": "1200000000000001"}
    assert all(c["simulate"] is True for c in seen)
    assert json.loads(run["steps"][1]["result"])["items"][0]["name"] == "Web 2026"


async def test_env_flag_simulates_without_run_flag(db, seen, monkeypatch):
    monkeypatch.setenv("SHIFU_FUNCTIONS_SIMULATE", "1")
    run = await run_steps(db, two_steps(), simulate=False)
    assert run["status"] == "completed" and all(c["simulate"] for c in seen)


async def test_failing_function_fails_the_step_and_logs_outcome(db, seen):
    # Sin cuenta conectada la funcion real devuelve missing_connection -> el paso falla con ese codigo.
    run = await run_steps(db, two_steps()[:1], simulate=False)
    assert run["status"] == "failed"
    assert run["steps"][0]["status"] == "failed" and run["steps"][0]["error"].startswith("missing_connection:")
    log = await db["tool_outcome_log"].find_one({"action": "asana.users.get"})
    assert log and log["success"] is False and log["user_id"] == USER


async def test_successful_real_path_logs_outcome_and_passes_account(db, seen, monkeypatch):
    async def fake_execute(fn, raw_input, **kw):
        from app.functions.spec import Result, ResultMeta
        return Result.success({"account_id": "7"}, meta=ResultMeta(function_id=fn.spec.id, version=1, duration_ms=12))

    monkeypatch.setattr(runner, "execute", fake_execute)
    steps = two_steps()[:1]
    steps[0]["account_id"] = "acc-9"
    run = await run_steps(db, steps, simulate=False)
    assert run["status"] == "completed" and json.loads(run["steps"][0]["result"]) == {"account_id": "7"}
    log = await db["tool_outcome_log"].find_one({"action": "asana.users.get"})
    assert log["success"] is True and log["duration_ms"] == 12


def register_demo():
    register_app(AppSpec(app="demo", provider_keys=["demo"], auth=AuthSpec(type=AuthType.none)))

    class In(BaseModel):
        name: str = Field(description="Name of the thing to act on in the demo app")

    class Out(BaseModel):
        ok: bool = Field(description="Always true in the demo")

    ex = lambda: [{"name": "default", "input": {"name": "a"}, "output": {"ok": True}}]  # noqa: E731

    @function(id="demo.things.delete", version=1, verb=Verb.delete, description=DESC, examples=ex())
    async def delete(ctx, args: In) -> Out:
        return Out(ok=True)

    @function(id="demo.things.send", version=1, verb=Verb.create, exits_outside=True, description=DESC, examples=ex())
    async def send(ctx, args: In) -> Out:
        return Out(ok=True)


async def test_delete_function_is_refused_but_draft_and_confirm_runs(db, seen):
    with isolated_registry():
        register_demo()
        steps = [
            {"order": 1, "name": "Borrar", "app": "demo", "action": "del", "function_id": "demo.things.delete", "config": {"name": "a"}},
            {"order": 2, "name": "Enviar", "app": "demo", "action": "send", "function_id": "demo.things.send", "config": {"name": "a"}},
        ]
        run = await run_steps(db, steps)
    assert run["steps"][0]["status"] == "failed" and "confirmacion" in run["steps"][0]["error"]
    assert run["steps"][1]["status"] == "completed"
    assert [c["id"] for c in seen] == ["demo.things.send"]  # la de borrar nunca llego al runner
    assert run["status"] == "failed"  # un paso fallo


async def test_unknown_function_fails_the_step(db):
    run = await run_steps(db, [{"order": 1, "name": "x", "function_id": "nada.nada.nada", "config": {}}])
    assert run["steps"][0]["status"] == "failed" and "no registrada" in run["steps"][0]["error"]


async def test_legacy_step_without_function_id_keeps_the_bigtools_path(db, seen, monkeypatch):
    # Importar el loader viejo crea el cliente de Tavily a nivel de modulo: basta una clave falsa (no hay red al importar).
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    import app.services.bigtools_loader as loader
    import app.services.chat_memory as chat_memory

    llamadas = []

    async def tool(**kw):
        llamadas.append(kw)
        return "viejo-ok"

    async def no_integrations(user_id, db):
        return []

    monkeypatch.setattr(chat_memory, "load_user_integrations", no_integrations)
    monkeypatch.setattr(loader, "get_all_bigtools", lambda *a, **k: [SimpleNamespace(name="legacy_tool", tool=tool)])
    monkeypatch.setattr(loader, "bigtool_to_lc", lambda bt: None)
    run = await run_steps(db, [{"order": 1, "name": "Viejo", "app": "gmail", "action": "legacy_tool", "config": {"to": "x"}}])
    assert run["status"] == "completed" and run["steps"][0]["result"] == "viejo-ok"
    assert llamadas == [{"to": "x"}] and seen == []


async def test_dry_run_uses_function_examples_and_keeps_legacy_mock(db, seen):
    steps = two_steps() + [{"order": 3, "name": "Viejo", "app": "gmail", "action": "legacy_tool", "config": {}}]
    run = {"_id": "dry", "user_id": USER, "workflow_id": "wf1", "steps": steps}
    out = await WorkflowExecutor(run, db, dry_run=True).execute_dry_run()
    t = out["trace"]
    assert json.loads(t[0]["mock_result"])["account_id"] == "1200000000000001"
    assert json.loads(t[1]["mock_result"])["items"][0]["name"] == "Web 2026" and "error" not in t[1]
    assert seen[1]["args"] == {"workspace": "1200000000000001"}  # la plantilla se resolvio con el ejemplo
    assert t[2]["mock_result"].startswith("[DRY RUN]")


async def test_dry_run_shows_when_a_step_needs_a_human(db):
    with isolated_registry():
        register_demo()
        run = {"_id": "dry", "user_id": USER, "workflow_id": "wf1",
               "steps": [{"order": 1, "function_id": "demo.things.delete", "config": {"name": "a"}}]}
        out = await WorkflowExecutor(run, db, dry_run=True).execute_dry_run()
    assert "confirmacion" in out["trace"][0]["error"]


# --- Endpoint ---------------------------------------------------------------------------------------

def make_app(db, user_id) -> FastAPI:
    app = FastAPI()
    app.state.db = db
    app.include_router(run_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"_id": ObjectId(user_id), "id": user_id, "email": "a@b.test"}
    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def add_workflow(db, user=USER):
    res = await db["workflows"].insert_one({"user_id": user, "name": "WF", "user_email": "a@b.test", "status": "active", "steps": two_steps()})
    return str(res.inserted_id)


async def test_run_endpoint_runs_simulated_and_get_returns_steps(db, seen):
    wf = await add_workflow(db)
    async with client(make_app(db, USER)) as c:
        r = await c.post(f"/api/v1/workflows/{wf}/run?simulate=1")
        assert r.status_code == 200 and r.json()["status"] == "running"
        run_id = r.json()["run_id"]
        await asyncio.gather(*run_routes._TASKS)
        got = (await c.get(f"/api/v1/workflows/runs/{run_id}")).json()
    assert got["status"] == "completed" and got["simulate"] is True
    assert [s["status"] for s in got["steps"]] == ["completed", "completed"] and got["steps"][0]["function_id"] == "asana.users.get"


async def test_other_users_workflow_and_run_are_404(db, seen):
    wf = await add_workflow(db, user=USER)
    intruder = str(ObjectId())
    async with client(make_app(db, intruder)) as c:
        assert (await c.post(f"/api/v1/workflows/{wf}/run?simulate=1")).status_code == 404
        assert (await c.post("/api/v1/workflows/no-es-un-id/run")).status_code == 404
    assert await db["workflow_runs"].count_documents({}) == 0
    async with client(make_app(db, USER)) as c:
        run_id = (await c.post(f"/api/v1/workflows/{wf}/run?simulate=1")).json()["run_id"]
        await asyncio.gather(*run_routes._TASKS)
    async with client(make_app(db, intruder)) as c:
        assert (await c.get(f"/api/v1/workflows/runs/{run_id}")).status_code == 404


async def test_plan_concurrency_limit_returns_429(db, seen):
    wf = await add_workflow(db)
    await db["workflow_runs"].insert_one({"user_id": USER, "status": "running", "steps": []})  # plan free: 1 a la vez
    async with client(make_app(db, USER)) as c:
        r = await c.post(f"/api/v1/workflows/{wf}/run?simulate=1")
    assert r.status_code == 429


def test_whole_template_keeps_its_type():
    """"{{step_1.items}}" como valor completo llega como lista; dentro de un texto sigue siendo texto."""
    import json
    from app.workers.workflow_executor import WorkflowExecutor
    ex = WorkflowExecutor.__new__(WorkflowExecutor)
    out = ex._substitute_vars({"ids": "{{step_1.items}}", "n": "{{step_1.count}}", "msg": "hay {{step_1.count}} filas"},
                              {1: json.dumps({"items": [1, 2], "count": 2})})
    assert out["ids"] == [1, 2] and out["n"] == 2 and out["msg"] == "hay 2 filas"


def test_template_paths_into_nested_output():
    """El planificador escribe {{step_1.rows[0][0]}}: la ruta con [n] y con .n llega a la celda, con su tipo."""
    import json
    from app.workers.workflow_executor import WorkflowExecutor
    ex = WorkflowExecutor.__new__(WorkflowExecutor)
    res = {1: json.dumps({"rows": [[1200, "Acme"], [980, "Globex"]], "header": ["Amount", "Client"]})}
    out = ex._substitute_vars(
        {"a": "{{step_1.rows[0][0]}}", "b": "{{step_1.rows.1.1}}", "c": "{{step_1.header[1]}}",
         "d": "Total: {{step_1.rows[1][0]}}", "e": "{{step_1.rows[0]}}", "f": "{{step_1.rows[9][0]}}"}, res)
    assert out["a"] == 1200 and out["b"] == "Globex" and out["c"] == "Client"   # valor completo: conserva el tipo
    assert out["d"] == "Total: 980" and out["e"] == [1200, "Acme"]
    assert out["f"] == res[1]   # ruta inexistente: como antes, el texto de la salida (no revienta)
