"""Herramientas de workflow_manager (administrar workflows desde el chat). Mongomock; sin red ni OpenAI."""
import os
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")  # req_nodes crea un ChatOpenAI al importarse

from app.agent.shared.nodes import workflow_manager as wm  # noqa: E402
from app.services.workflow_run_service import ConcurrentRunLimitExceededError  # noqa: E402

USER = str(ObjectId())
OTHER = str(ObjectId())
UTC = timezone.utc


@pytest.fixture
def db():
    return AsyncMongoMockClient()["workflow_manager_test"]


def ctx(db, tz="America/Mexico_City"):
    return {"db": db, "user_id": USER, "timezone": tz}


async def add_wf(db, user=USER, status="active", name="Reporte", **extra):
    res = await db["workflows"].insert_one({
        "user_id": user, "user_email": "a@b.test", "name": name, "status": status, "updated_at": datetime.now(UTC),
        "steps": [{"order": 2, "app": "gmail", "name": "Enviar correo"},
                  {"order": 1, "app": "sheets", "name": "Leer hoja", "description": "Lee las ventas de la hoja"}], **extra})
    return str(res.inserted_id)


async def add_task(db, wf_id, status="active", cron="0 9 * * 1", user=USER):
    res = await db["scheduled_tasks"].insert_one({
        "workflow_id": wf_id, "user_id": user, "name": "scheduled_workflow", "schedule_type": "cron", "status": status,
        "schedule_config": {"cron_expression": cron, "timezone": "America/Mexico_City"},
        "next_run_at": datetime.now(UTC) + timedelta(days=3), "created_at": datetime.now(UTC)})
    return res.inserted_id


async def add_run(db, wf_id, status="completed", user=USER, steps=None, **extra):
    await db["workflow_runs"].insert_one({
        "workflow_id": wf_id, "user_id": user, "status": status, "trigger": "manual", "steps": steps or [],
        "created_at": datetime.now(UTC), **extra})


async def status_of(db, wf_id):
    return (await db["workflows"].find_one({"_id": ObjectId(wf_id)}))["status"]


# --- Lectura -----------------------------------------------------------------------------------------

async def test_list_excludes_other_users_drafts_and_archived(db):
    mine = await add_wf(db, name="Mio")
    await add_wf(db, user=OTHER, name="Ajeno")
    await add_wf(db, status="creating", name="Borrador")
    await add_wf(db, status="archived", name="Borrado")
    await add_task(db, mine)
    await add_run(db, mine, status="failed")
    out = await wm.list_workflows(ctx(db), {})
    rows = out["data"]["workflows"]
    assert [r["name"] for r in rows] == ["Mio"] and out["data"]["count"] == 1
    assert rows[0]["id"] == mine and rows[0]["status"] == "active"
    assert "lunes" in rows[0]["starts"] and "America/Mexico_City" in rows[0]["starts"]
    assert rows[0]["last_run"]["status"] == "failed"


async def test_list_says_how_email_webhook_and_manual_workflows_start(db):
    await add_wf(db, name="Correo", trigger_type="email", email_trigger={"q": "from:ana@x.test"})
    await add_wf(db, name="Hook", trigger_type="webhook", webhook_token="tok123secret")
    await add_wf(db, name="Manual")
    out = await wm.list_workflows(ctx(db), {})
    by_name = {r["name"]: r["starts"] for r in out["data"]["workflows"]}
    assert "correo nuevo" in by_name["Correo"] and "ana@x.test" in by_name["Correo"]
    assert "webhook" in by_name["Hook"] and "a mano" in by_name["Manual"]
    assert "tok123secret" not in str(out)  # el token es la autenticacion: nunca sale en el chat


async def test_get_workflow_returns_steps_and_the_failing_step_of_the_last_failed_run(db):
    wf = await add_wf(db)
    await add_run(db, wf, status="completed")
    await add_run(db, wf, status="failed", steps=[
        {"order": 1, "name": "Leer hoja", "status": "completed"},
        {"order": 2, "name": "Enviar correo", "status": "failed", "error": "auth_failed: token vencido"}])
    data = (await wm.get_workflow(ctx(db), {"workflow_id": wf}))["data"]
    assert [s["order"] for s in data["steps"]] == [1, 2]
    assert data["steps"][0]["what"] == "Lee las ventas de la hoja" and data["steps"][1]["what"] == "Enviar correo"
    failed = next(r for r in data["last_runs"] if r["status"] == "failed")
    assert failed["failed_step"] == {"order": 2, "name": "Enviar correo", "error": "auth_failed: token vencido"}
    assert failed["trigger"] == "manual" and len(data["last_runs"]) == 2


async def test_get_workflow_reports_a_disabled_email_trigger_and_keeps_only_3_runs(db):
    wf = await add_wf(db, trigger_type="email", email_trigger={"q": "", "disabled": True, "last_error": "auth_failed"})
    for _ in range(5):
        await add_run(db, wf)
    data = (await wm.get_workflow(ctx(db), {"workflow_id": wf}))["data"]
    assert data["email_trigger"] == {"disabled": True, "reason": "auth_failed"} and len(data["last_runs"]) == 3


# --- Pausar y reanudar -----------------------------------------------------------------------------------

async def test_pause_and_resume_flip_the_status_and_the_scheduled_task(db):
    wf = await add_wf(db)
    task = await add_task(db, wf)
    await wm.pause_workflow(ctx(db), {"workflow_id": wf})
    assert await status_of(db, wf) == "paused"
    assert (await db["scheduled_tasks"].find_one({"_id": task}))["status"] == "paused"
    await wm.resume_workflow(ctx(db), {"workflow_id": wf})
    assert await status_of(db, wf) == "active"
    t = await db["scheduled_tasks"].find_one({"_id": task})
    assert t["status"] == "active"
    # resume_task deja next_run_at = ahora (correria de inmediato); aqui vuelve a su proxima hora de cron
    assert t["next_run_at"].replace(tzinfo=UTC) > datetime.now(UTC) + timedelta(minutes=1)


async def test_resume_of_an_email_workflow_clears_the_error_and_moves_since_forward(db):
    old = datetime(2026, 10, 1, tzinfo=UTC)
    wf = await add_wf(db, status="paused", trigger_type="email", email_trigger={
        "q": "x", "since": old, "seen_ids": ["a"], "next_poll_at": old, "disabled": True, "last_error": "auth_failed"})
    before = datetime.now(UTC) - timedelta(seconds=5)  # Mongo guarda milisegundos: margen
    await wm.resume_workflow(ctx(db), {"workflow_id": wf})
    trig = (await db["workflows"].find_one({"_id": ObjectId(wf)}))["email_trigger"]
    assert "disabled" not in trig and "last_error" not in trig and trig["seen_ids"] == ["a"]
    assert trig["since"].replace(tzinfo=UTC) >= before and trig["next_poll_at"].replace(tzinfo=UTC) >= before


# --- Horario ---------------------------------------------------------------------------------------------

async def test_set_schedule_stores_the_cron_in_the_user_zone_and_replaces_the_old_task(db):
    wf = await add_wf(db, trigger_type="webhook", webhook_token="tok")
    old = await add_task(db, wf, cron="0 9 * * 1")
    out = await wm.set_schedule(ctx(db), {"workflow_id": wf, "when": "cada martes a las 8"})
    assert out["ok"] and "martes" in out["data"]["schedule"] and out["data"]["timezone"] == "America/Mexico_City"
    tasks = await db["scheduled_tasks"].find({"workflow_id": wf}).to_list(10)
    assert len(tasks) == 1 and tasks[0]["_id"] != old  # la vieja ya no esta
    assert tasks[0]["schedule_type"] == "cron" and tasks[0]["status"] == "active"
    assert tasks[0]["schedule_config"] == {"cron_expression": "0 8 * * 2", "timezone": "America/Mexico_City"}
    doc = await db["workflows"].find_one({"_id": ObjectId(wf)})
    assert doc["trigger_type"] == "schedule" and "webhook_token" not in doc


async def test_set_schedule_on_a_paused_workflow_leaves_the_task_paused(db):
    wf = await add_wf(db, status="paused")
    await wm.set_schedule(ctx(db), {"workflow_id": wf, "when": "todos los dias a las 18:30"})
    task = await db["scheduled_tasks"].find_one({"workflow_id": wf})
    assert task["schedule_config"]["cron_expression"] == "30 18 * * *" and task["status"] == "paused"


@pytest.mark.parametrize("when", ["cuando se pueda", "", "cada lunes"])  # la ultima no trae hora: correria a medianoche
async def test_set_schedule_with_garbage_changes_nothing_and_errors(db, when):
    wf = await add_wf(db, trigger_type="email", email_trigger={"q": ""})
    old = await add_task(db, wf)
    out = await wm.set_schedule(ctx(db), {"workflow_id": wf, "when": when})
    assert out["ok"] is False and out["error"]["code"] == "invalid_input" and "day and time" in out["error"]["message"]
    tasks = await db["scheduled_tasks"].find({"workflow_id": wf}).to_list(10)
    assert [t["_id"] for t in tasks] == [old]
    assert (await db["workflows"].find_one({"_id": ObjectId(wf)}))["trigger_type"] == "email"


# --- Ejecutar ahora -------------------------------------------------------------------------------------

class Launcher:
    def __init__(self, monkeypatch, raises=None):
        self.calls, self.raises = [], raises
        monkeypatch.setattr(wm, "start_workflow_run", self.start)

    async def start(self, db, workflow, **kw):
        if self.raises:
            raise self.raises
        self.calls.append((workflow, kw))
        return "run-1"


async def test_run_now_launches_an_active_workflow_manually(db, monkeypatch):
    monkeypatch.setenv("SHIFU_FUNCTIONS_SIMULATE", "1")
    launcher = Launcher(monkeypatch)
    wf = await add_wf(db)
    out = await wm.run_now(ctx(db), {"workflow_id": wf})
    assert out["data"]["run_id"] == "run-1" and out["data"]["simulated"] is True
    assert launcher.calls[0][1] == {"trigger": "manual", "simulate": True} and str(launcher.calls[0][0]["_id"]) == wf


async def test_run_now_does_not_launch_a_paused_workflow(db, monkeypatch):
    launcher = Launcher(monkeypatch)
    wf = await add_wf(db, status="paused")
    out = await wm.run_now(ctx(db), {"workflow_id": wf})
    assert out["ok"] is False and "resume" in out["error"]["message"] and launcher.calls == []


async def test_run_now_turns_the_plan_limit_into_an_error(db, monkeypatch):
    Launcher(monkeypatch, raises=ConcurrentRunLimitExceededError(1))
    out = await wm.run_now(ctx(db), {"workflow_id": await add_wf(db)})
    assert out["ok"] is False and "simultaneas" in out["error"]["message"]


# --- Borrar (suave) ------------------------------------------------------------------------------------

async def test_delete_archives_and_pauses_and_resume_restores(db):
    wf = await add_wf(db)
    task = await add_task(db, wf)
    out = await wm.delete_workflow(ctx(db), {"workflow_id": wf})
    assert out["data"]["recoverable"] is True and await status_of(db, wf) == "archived"
    assert await db["workflows"].count_documents({"_id": ObjectId(wf)}) == 1  # nada se borra fisicamente
    assert (await db["scheduled_tasks"].find_one({"_id": task}))["status"] == "paused"
    assert (await wm.list_workflows(ctx(db), {}))["data"]["count"] == 0
    await wm.resume_workflow(ctx(db), {"workflow_id": wf})
    assert await status_of(db, wf) == "active"
    assert (await wm.list_workflows(ctx(db), {}))["data"]["count"] == 1


# --- Un usuario nunca toca el workflow de otro ------------------------------------------------------------

@pytest.mark.parametrize("tool", ["get_workflow", "pause_workflow", "resume_workflow", "set_schedule", "run_now",
                                  "delete_workflow"])
async def test_every_tool_refuses_another_users_workflow(db, monkeypatch, tool):
    launcher = Launcher(monkeypatch)
    foreign = await add_wf(db, user=OTHER, name="Ajeno")
    task = await add_task(db, foreign, user=OTHER)
    before = await db["workflows"].find_one({"_id": ObjectId(foreign)})
    out = await wm._TOOLS[tool](ctx(db), {"workflow_id": foreign, "when": "cada martes a las 8"})
    assert out["ok"] is False and out["error"]["code"] == "not_found"
    assert await db["workflows"].find_one({"_id": ObjectId(foreign)}) == before
    assert (await db["scheduled_tasks"].find_one({"_id": task}))["status"] == "active"
    assert launcher.calls == [] and await db["scheduled_tasks"].count_documents({}) == 1


@pytest.mark.parametrize("bad", ["", "no-es-un-id", str(ObjectId()), None])
async def test_unknown_or_malformed_ids_are_not_found(db, bad):
    assert (await wm.get_workflow(ctx(db), {"workflow_id": bad}))["error"]["code"] == "not_found"


async def test_a_draft_cannot_be_managed(db):
    draft = await add_wf(db, status="creating")
    assert (await wm.delete_workflow(ctx(db), {"workflow_id": draft}))["error"]["code"] == "not_found"
    assert await status_of(db, draft) == "creating"
