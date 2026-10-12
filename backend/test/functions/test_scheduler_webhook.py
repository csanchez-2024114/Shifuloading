"""Etapa 4: programador, zona horaria del cron, webhook y {{trigger.campo}}. Mongomock, sin red ni OpenAI."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI
from mongomock_motor import AsyncMongoMockClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter
from app.database import get_db
from app.functions.registry import function, isolated_registry, load_all, register_app
from app.functions.spec import AppSpec, AuthSpec, AuthType, Verb
from app.routes.workflows import webhook as webhook_routes
from app.services import scheduled_task_service as sts
from app.services.workflow_launcher import _TASKS
from app.workers import scheduler_loop
from app.workers.workflow_executor import WorkflowExecutor
from functions_helpers import DESC
from pydantic import BaseModel, Field

USER = str(ObjectId())
UTC = timezone.utc


@pytest.fixture(scope="module", autouse=True)
def _loaded():
    load_all()  # antes de cualquier isolated_registry (ver test_workflow_functions)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["stage4_test"]


@pytest.fixture(autouse=True)
def _simulate(monkeypatch):
    monkeypatch.setenv("SHIFU_FUNCTIONS_SIMULATE", "1")  # el programador y el webhook simulan: ninguna app externa


def steps():
    return [{"order": 1, "name": "Quien soy", "app": "asana", "action": "users.get", "function_id": "asana.users.get",
             "config": {"nodeType": "action"}}]


async def add_workflow(db, status="active", **extra):
    res = await db["workflows"].insert_one(
        {"user_id": USER, "name": "WF", "user_email": "a@b.test", "status": status, "steps": steps(), **extra})
    return str(res.inserted_id)


async def one_run(db):
    runs = await db["workflow_runs"].find({}).to_list(10)
    assert len(runs) == 1
    return runs[0]


# --- Cron con zona horaria ---------------------------------------------------------------------------

def test_cron_is_read_in_the_user_zone_and_returned_in_utc():
    sat = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)  # sabado
    # "cada lunes 9:00" en Ciudad de Mexico (UTC-6, sin horario de verano) = 15:00 UTC
    assert sts._next_cron_run("0 9 * * 1", after=sat, tz_name="America/Mexico_City") == datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
    assert sts._next_cron_run("0 9 * * 1", after=sat) == datetime(2026, 10, 12, 9, 0, tzinfo=UTC)  # sin zona: UTC como siempre
    assert sts._next_cron_run("0 9 * * 1", after=sat, tz_name="No/Existe") == datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def test_cron_follows_daylight_saving_changes():
    # Madrid: UTC+2 en octubre, UTC+1 despues del 25 de octubre de 2026.
    before = sts._next_cron_run("0 9 * * *", after=datetime(2026, 10, 10, 12, tzinfo=UTC), tz_name="Europe/Madrid")
    after = sts._next_cron_run("0 9 * * *", after=datetime(2026, 11, 10, 12, tzinfo=UTC), tz_name="Europe/Madrid")
    assert before.hour == 7 and after.hour == 8


async def test_created_task_stores_timezone_and_utc_next_run(db):
    await sts.create_scheduled_task(USER, "a@b.test", "wf", "n", "cron",
                                    {"cron_expression": "0 9 * * 1", "timezone": "America/Mexico_City"}, db)
    task = await db["scheduled_tasks"].find_one({})
    assert task["schedule_config"]["timezone"] == "America/Mexico_City"
    nxt = task["next_run_at"].replace(tzinfo=UTC)  # mongomock puede devolver la fecha sin zona: es UTC
    assert nxt.hour == 15 and nxt.weekday() == 0 and nxt > datetime.now(UTC)


# --- Programador -------------------------------------------------------------------------------------

async def add_task(db, wf_id, run_at=None, schedule_type="once", **cfg):
    config = {"run_at": (run_at or datetime.now(UTC) - timedelta(seconds=1)).isoformat(), **cfg} if schedule_type == "once" else cfg
    return await sts.create_scheduled_task(USER, "a@b.test", wf_id, "t", schedule_type, config, db)


async def test_tick_runs_a_due_once_task_and_completes_it(db):
    wf = await add_workflow(db)
    task_id = await add_task(db, wf)
    assert await scheduler_loop.tick(db) == 1
    await asyncio.gather(*_TASKS)
    run = await one_run(db)
    assert run["status"] == "completed" and run["trigger"] == "schedule" and run["simulate"] is True
    task = await db["scheduled_tasks"].find_one({"_id": ObjectId(task_id)})
    assert task["status"] == "completed" and task["run_count"] == 1
    assert await scheduler_loop.tick(db) == 0  # ya no vuelve a correr


async def test_tick_ignores_tasks_not_due_yet(db):
    wf = await add_workflow(db)
    await add_task(db, wf, run_at=datetime.now(UTC) + timedelta(hours=1))
    assert await scheduler_loop.tick(db) == 0
    assert await db["workflow_runs"].count_documents({}) == 0


@pytest.mark.parametrize("status", ["paused", "draft"])
async def test_tick_skips_and_pauses_tasks_of_inactive_workflows(db, status):
    wf = await add_workflow(db, status=status)
    task_id = await add_task(db, wf)
    assert await scheduler_loop.tick(db) == 1
    assert await db["workflow_runs"].count_documents({}) == 0
    assert (await db["scheduled_tasks"].find_one({"_id": ObjectId(task_id)}))["status"] == "paused"


async def test_tick_pauses_task_whose_workflow_was_deleted(db):
    task_id = await add_task(db, str(ObjectId()))
    await scheduler_loop.tick(db)
    assert (await db["scheduled_tasks"].find_one({"_id": ObjectId(task_id)}))["status"] == "paused"


async def test_an_error_in_one_task_does_not_stop_the_tick_and_the_cron_task_advances(db, monkeypatch):
    bad, good = await add_workflow(db, name="malo"), await add_workflow(db, name="bueno")
    bad_task = await add_task(db, bad, schedule_type="cron", cron_expression="0 9 * * 1")
    await db["scheduled_tasks"].update_one({"_id": ObjectId(bad_task)}, {"$set": {"next_run_at": datetime.now(UTC) - timedelta(minutes=5)}})
    good_task = await add_task(db, good)
    real = scheduler_loop.start_workflow_run

    async def flaky(db_, wf, **kw):
        if wf["_id"] == ObjectId(bad):
            raise RuntimeError("boom")
        return await real(db_, wf, **kw)

    monkeypatch.setattr(scheduler_loop, "start_workflow_run", flaky)
    assert await scheduler_loop.tick(db) == 2
    await asyncio.gather(*_TASKS)
    assert (await db["scheduled_tasks"].find_one({"_id": ObjectId(good_task)}))["status"] == "completed"
    # la que fallo no quedo en el futuro lejano: avanzo a su proxima ocurrencia
    nxt = (await db["scheduled_tasks"].find_one({"_id": ObjectId(bad_task)}))["next_run_at"].replace(tzinfo=UTC)
    assert nxt.year < 9999 and nxt > datetime.now(UTC)


async def test_plan_concurrency_limit_defers_the_task_instead_of_losing_it(db):
    wf = await add_workflow(db)
    task_id = await add_task(db, wf)
    await db["workflow_runs"].insert_one({"user_id": USER, "status": "running", "steps": []})  # plan free: 1 a la vez
    await scheduler_loop.tick(db)
    task = await db["scheduled_tasks"].find_one({"_id": ObjectId(task_id)})
    assert task["status"] == "active" and task["run_count"] == 0
    assert task["next_run_at"].replace(tzinfo=UTC) > datetime.now(UTC)
    assert await db["workflow_runs"].count_documents({"workflow_id": wf}) == 0


async def test_run_forever_survives_a_failing_tick_and_cancels_cleanly(db, monkeypatch):
    calls = []

    async def failing_tick(db_):
        calls.append(1)
        raise RuntimeError("mongo caido")

    monkeypatch.setattr(scheduler_loop, "tick", failing_tick)
    task = asyncio.create_task(scheduler_loop.run_forever(db, 0.01))
    await asyncio.sleep(0.1)
    assert not task.done() and len(calls) >= 2  # siguio intentando tras el error
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# --- {{trigger.campo}} -------------------------------------------------------------------------------

def test_trigger_templates_resolve_and_keep_type():
    ex = WorkflowExecutor.__new__(WorkflowExecutor)
    ex.run = {"trigger_payload": {"monto": 120, "cliente": {"nombre": "Ana"}, "tags": ["a", "b"]}}
    out = ex._substitute_vars(
        {"n": "{{trigger.monto}}", "msg": "Cobro de {{trigger.monto}} a {{trigger.cliente}}", "tags": "{{trigger.tags}}",
         "all": "{{trigger}}", "missing": "{{trigger.nada}}"}, {})
    assert out["n"] == 120 and out["tags"] == ["a", "b"] and out["all"]["monto"] == 120 and out["missing"] == ""
    assert out["msg"] == 'Cobro de 120 a {"nombre": "Ana"}'
    ex.run = {}  # corrida manual: sin payload, las plantillas quedan vacias en vez de romper
    assert ex._substitute_vars({"n": "{{trigger.monto}}", "t": "x{{trigger}}"}, {}) == {"n": "", "t": "x"}


# --- Webhook -----------------------------------------------------------------------------------------

TOKEN = "a" * 32


def make_app(db) -> FastAPI:
    app = FastAPI()
    app.state.db = db
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(webhook_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    return app


def client(db) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app(db)), base_url="http://test")


@pytest.fixture(autouse=True)
def _fresh_limiter(monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)  # el .env local puede traer RATE_LIMIT_ENABLED=false
    limiter.reset()
    yield
    limiter.reset()


async def test_unknown_or_malformed_token_is_a_generic_404(db):
    await add_workflow(db, webhook_token=TOKEN)
    async with client(db) as c:
        assert (await c.post("/api/v1/webhooks/" + "b" * 32, json={})).status_code == 404
        assert (await c.post("/api/v1/webhooks/corto", json={})).status_code == 404
        assert (await c.post("/api/v1/webhooks/" + TOKEN + "!", json={})).status_code == 404
    assert await db["workflow_runs"].count_documents({}) == 0


async def test_paused_workflow_is_409(db):
    await add_workflow(db, status="paused", webhook_token=TOKEN)
    async with client(db) as c:
        assert (await c.post(f"/api/v1/webhooks/{TOKEN}", json={"monto": 1})).status_code == 409
    assert await db["workflow_runs"].count_documents({}) == 0


async def test_body_over_64kb_is_413_by_header_and_by_stream(db):
    await add_workflow(db, webhook_token=TOKEN)
    big = json.dumps({"x": "y" * (webhook_routes.MAX_BODY_BYTES + 10)})
    async with client(db) as c:
        assert (await c.post(f"/api/v1/webhooks/{TOKEN}", content=big, headers={"content-type": "application/json"})).status_code == 413

        async def chunks():  # sin Content-Length: el corte lo hace la lectura del flujo
            for _ in range(3):
                yield b"x" * 30_000

        assert (await c.post(f"/api/v1/webhooks/{TOKEN}", content=chunks())).status_code == 413
    assert await db["workflow_runs"].count_documents({}) == 0


async def test_invalid_json_is_400(db):
    await add_workflow(db, webhook_token=TOKEN)
    async with client(db) as c:
        assert (await c.post(f"/api/v1/webhooks/{TOKEN}", content=b"{no json")).status_code == 400


def register_echo():
    register_app(AppSpec(app="echo", provider_keys=["echo"], auth=AuthSpec(type=AuthType.none)))

    class In(BaseModel):
        amount: int = Field(description="Amount received by the webhook, kept as a number when the template is the whole value")
        note: str = Field(default="", description="Free text note that may mix literal words with webhook data")

    class Out(BaseModel):
        amount: int = Field(description="The same amount that came in")

    @function(id="echo.things.get", version=1, verb=Verb.read, description=DESC,
              examples=[{"name": "default", "input": {"amount": 1}, "output": {"amount": 1}}])
    async def get(ctx, args: In) -> Out:
        return Out(amount=args.amount)


async def test_valid_call_is_202_and_the_run_resolves_trigger_fields(db, monkeypatch):
    from app.functions import runner

    seen = []
    real = runner.execute

    async def spy(fn, raw_input, **kw):
        seen.append(raw_input)
        return await real(fn, raw_input, **kw)

    monkeypatch.setattr(runner, "execute", spy)
    with isolated_registry():
        register_echo()
        res = await db["workflows"].insert_one({
            "user_id": USER, "name": "WF", "user_email": "a@b.test", "status": "active", "webhook_token": TOKEN,
            "steps": [{"order": 1, "name": "Eco", "app": "echo", "action": "get", "function_id": "echo.things.get",
                       "config": {"amount": "{{trigger.monto}}", "note": "Monto: {{trigger.monto}}"}}]})
        async with client(db) as c:
            r = await c.post(f"/api/v1/webhooks/{TOKEN}", json={"monto": 120})
            assert r.status_code == 202
            await asyncio.gather(*_TASKS)
    run = await db["workflow_runs"].find_one({"_id": ObjectId(r.json()["run_id"])})
    assert run["workflow_id"] == str(res.inserted_id) and run["trigger"] == "webhook" and run["trigger_payload"] == {"monto": 120}
    assert run["status"] == "completed"
    assert seen == [{"amount": 120, "note": "Monto: 120"}]  # amount llego como numero, no como "120"


async def test_empty_body_is_accepted_and_manual_runs_have_no_payload(db):
    await add_workflow(db, webhook_token=TOKEN)
    async with client(db) as c:
        assert (await c.post(f"/api/v1/webhooks/{TOKEN}")).status_code == 202
        await asyncio.gather(*_TASKS)
    run = await one_run(db)
    assert run["trigger"] == "webhook" and run["trigger_payload"] is None


async def test_webhook_rate_limit_is_429_after_30_calls_per_token(db):
    await add_workflow(db, webhook_token=TOKEN)
    async with client(db) as c:
        codes = [(await c.post(f"/api/v1/webhooks/{TOKEN}", json={})).status_code for _ in range(31)]
        await asyncio.gather(*_TASKS)
    assert codes[-1] == 429 and 404 not in codes
