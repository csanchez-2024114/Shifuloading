"""Activar (_finalize): lo que se programa es el horario que se le MOSTRO al usuario en CONFIRM (req_schedule), con respaldo
en el plan. El turno de confirmacion ("si") nunca trae horario propio."""
import os
from types import SimpleNamespace

import pytest
from bson import ObjectId
from langchain_core.messages import HumanMessage
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("OPENAI_API_KEY", "sk-fake")  # ChatOpenAI se crea al importar el modulo; no hay llamadas

from app.agent.shifu_base_v1.graph import req_nodes  # noqa: E402

USER = str(ObjectId())


@pytest.fixture
def db(monkeypatch):
    db = AsyncMongoMockClient()["finalize_test"]
    monkeypatch.setattr(req_nodes, "mongo_manager", SimpleNamespace(db=db))
    return db


async def make_workflow(db):
    res = await db["workflows"].insert_one({"user_id": USER, "name": "WF", "status": "creating", "steps": []})
    return str(res.inserted_id)


def state(wf_id, **kw):
    return {"user_id": USER, "user_email": "a@b.test", "req_workflow_id": wf_id, "req_trigger_type": "schedule",
            "req_trigger_event": "cada lunes a las 9", "messages": [HumanMessage(content="sí")], **kw}


async def test_shown_schedule_is_the_one_scheduled_in_the_user_zone(db):
    wf = await make_workflow(db)
    out = await req_nodes._finalize(state(wf, req_schedule={"cron": "0 9 * * 1", "human": "Every Monday at 09:00"},
                                          user_timezone="America/Mexico_City"))
    task = await db["scheduled_tasks"].find_one({})
    assert task["schedule_type"] == "cron" and task["schedule_config"] == {"cron_expression": "0 9 * * 1", "timezone": "America/Mexico_City"}
    assert task["workflow_id"] == wf and task["next_run_at"].hour == 15  # 9:00 de Mexico = 15:00 UTC
    assert (await db["workflows"].find_one({"_id": ObjectId(wf)}))["status"] == "active"
    assert out["req_deployed"] is True and out["req_level"] is None
    assert "cada lunes a las 9:00" in out["structured_prompt"] and "America/Mexico_City" in out["structured_prompt"]


async def test_without_a_stored_schedule_the_plan_trigger_is_parsed(db):
    wf = await make_workflow(db)
    await req_nodes._finalize(state(wf, user_timezone="America/Mexico_City"))
    task = await db["scheduled_tasks"].find_one({})
    assert task["schedule_config"]["cron_expression"] == "0 9 * * 1"


async def test_no_zone_means_utc(db):
    wf = await make_workflow(db)
    await req_nodes._finalize(state(wf, req_schedule={"cron": "30 8 * * *", "human": "Every day at 08:30"}))
    task = await db["scheduled_tasks"].find_one({})
    assert task["schedule_config"] == {"cron_expression": "30 8 * * *"}


async def test_unparseable_schedule_activates_for_manual_runs_and_says_so(db):
    wf = await make_workflow(db)
    out = await req_nodes._finalize(state(wf, req_trigger_event="cuando pueda", messages=[HumanMessage(content="no sé")]))
    assert await db["scheduled_tasks"].count_documents({}) == 0
    assert out["req_deployed"] is True and out["req_level"] is None
    assert "NO correrá solo" in out["structured_prompt"]
    assert (await db["workflows"].find_one({"_id": ObjectId(wf)}))["status"] == "active"


async def test_webhook_gets_a_token_and_the_message_carries_the_url(db):
    wf = await make_workflow(db)
    out = await req_nodes._finalize(state(wf, req_trigger_type="webhook"))
    assert out["req_webhook_url"] and "/api/v1/webhooks/" in out["req_webhook_url"]
    assert out["req_webhook_url"] in out["structured_prompt"]
    assert await db["scheduled_tasks"].count_documents({}) == 0


def test_cron_is_described_in_spanish():
    assert req_nodes._cron_es("0 9 * * 1") == "cada lunes a las 9:00"
    assert req_nodes._cron_es("30 18 * * *") == "todos los días a las 18:30"
    assert req_nodes._cron_es("0 * * * *") == "cada hora"
    assert req_nodes._cron_es("*/5 * * * *", "Scheduled") == "Scheduled"
