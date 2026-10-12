"""Disparador de correo nuevo: tick, deduplicacion, limite del plan y desactivacion. Mongomock; sin Gmail ni red."""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.functions.registry import load_all
from app.functions.spec import ErrorCode, Result
from app.services.workflow_run_service import ConcurrentRunLimitExceededError
from app.workers import email_trigger_loop as etl

USER = str(ObjectId())
UTC = timezone.utc


@pytest.fixture(scope="module", autouse=True)
def _loaded():
    load_all()


@pytest.fixture
def db():
    return AsyncMongoMockClient()["email_trigger_test"]


def msg(i: str) -> dict:
    return {"id": i, "thread_id": "t" + i, "sender": "ana@x.test", "to": "yo@x.test", "subject": "Hola " + i,
            "date": "Mon, 5 Oct 2026 09:30:00 -0500", "snippet": "texto", "label_ids": ["INBOX"], "unread": True}


class Fake:
    """Reemplaza execute y start_workflow_run dentro del modulo y recuerda como los llamaron."""

    def __init__(self, monkeypatch, messages=None, result=None, limit_on=None):
        self.messages = messages or []
        self.result = result
        self.limit_on = limit_on  # ids para los que el plan no deja otra corrida
        self.searches: list[dict] = []
        self.launches: list[dict] = []
        monkeypatch.setattr(etl, "execute", self.execute)
        monkeypatch.setattr(etl, "start_workflow_run", self.start)

    async def execute(self, fn, raw_input, **kw):
        self.searches.append({"input": raw_input, **kw})
        return self.result or Result.success({"messages": self.messages, "count": len(self.messages)})

    async def start(self, db, wf, **kw):
        if kw["payload"]["id"] in (self.limit_on or ()):
            raise ConcurrentRunLimitExceededError(1)
        self.launches.append(kw)
        return "run-" + kw["payload"]["id"]


SINCE = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


async def add_wf(db, status="active", **trig):
    email_trigger = {"q": "from:ana@x.test", "account_id": None, "since": SINCE, "seen_ids": [],
                     "next_poll_at": datetime.now(UTC) - timedelta(seconds=1), **trig}
    res = await db["workflows"].insert_one({
        "user_id": USER, "user_email": "a@b.test", "name": "WF", "status": status, "trigger_type": "email",
        "steps": [{"order": 1}], "email_trigger": email_trigger})
    return res.inserted_id


async def get_trig(db, wf_id) -> dict:
    return (await db["workflows"].find_one({"_id": wf_id}))["email_trigger"]


async def force_due(db, wf_id):
    await db["workflows"].update_one({"_id": wf_id}, {"$set": {"email_trigger.next_poll_at": datetime.now(UTC) - timedelta(seconds=1)}})


async def test_one_new_email_launches_one_run_and_is_remembered(db, monkeypatch):
    fake = Fake(monkeypatch, messages=[msg("a")])
    wf = await add_wf(db)
    assert await etl.tick(db) == 1
    assert len(fake.launches) == 1
    assert fake.launches[0]["trigger"] == "email" and fake.launches[0]["payload"] == msg("a")
    trig = await get_trig(db, wf)
    assert trig["seen_ids"] == ["a"]
    assert _utc(trig["since"]) > SINCE
    assert _utc(trig["next_poll_at"]) > datetime.now(UTC)


async def test_same_email_on_a_second_poll_does_not_launch_again(db, monkeypatch):
    fake = Fake(monkeypatch, messages=[msg("a")])
    wf = await add_wf(db)
    await etl.tick(db)
    await force_due(db, wf)
    assert await etl.tick(db) == 1  # se consulto otra vez...
    assert len(fake.searches) == 2 and len(fake.launches) == 1  # ...pero no se relanzo
    assert (await get_trig(db, wf))["seen_ids"] == ["a"]


async def test_not_polled_when_paused_not_due_or_disabled(db, monkeypatch):
    fake = Fake(monkeypatch, messages=[msg("a")])
    await add_wf(db, status="paused")
    await add_wf(db, next_poll_at=datetime.now(UTC) + timedelta(hours=1))
    await add_wf(db, disabled=True)
    assert await etl.tick(db) == 0
    assert fake.searches == [] and fake.launches == []


async def test_auth_expired_disables_the_trigger_for_good(db, monkeypatch):
    fake = Fake(monkeypatch, result=Result.failure(ErrorCode.auth_expired, "token vencido"))
    wf = await add_wf(db)
    assert await etl.tick(db) == 1
    trig = await get_trig(db, wf)
    assert trig["disabled"] is True and trig["last_error"] == "auth_expired"
    await force_due(db, wf)
    assert await etl.tick(db) == 0
    assert len(fake.searches) == 1 and fake.launches == []


async def test_other_errors_only_record_last_error_and_retry(db, monkeypatch):
    fake = Fake(monkeypatch, result=Result.failure(ErrorCode.upstream_down, "gmail caido"))
    wf = await add_wf(db)
    await etl.tick(db)
    trig = await get_trig(db, wf)
    assert trig["last_error"] == "upstream_down" and not trig.get("disabled")
    await force_due(db, wf)
    assert await etl.tick(db) == 1 and len(fake.searches) == 2


async def test_plan_limit_stops_the_loop_and_keeps_the_emails_for_the_next_poll(db, monkeypatch):
    fake = Fake(monkeypatch, messages=[msg("new"), msg("old")], limit_on={"old"})  # llega newest first
    wf = await add_wf(db)
    await etl.tick(db)
    trig = await get_trig(db, wf)
    assert fake.launches == [] and trig["seen_ids"] == []
    assert _utc(trig["since"]) == SINCE


async def test_two_new_emails_are_launched_oldest_first(db, monkeypatch):
    fake = Fake(monkeypatch, messages=[msg("nuevo"), msg("viejo")])
    wf = await add_wf(db)
    await etl.tick(db)
    assert [k["payload"]["id"] for k in fake.launches] == ["viejo", "nuevo"]
    assert (await get_trig(db, wf))["seen_ids"] == ["viejo", "nuevo"]


async def test_query_has_the_filter_inbox_and_the_since_epoch(db, monkeypatch):
    fake = Fake(monkeypatch)
    await add_wf(db)
    await etl.tick(db)
    q = fake.searches[0]["input"]["q"]
    assert q == f"from:ana@x.test in:inbox after:{int(SINCE.timestamp())}"
    assert fake.searches[0]["user_id"] == USER


async def test_an_exception_in_one_workflow_does_not_stop_the_tick(db, monkeypatch):
    fake = Fake(monkeypatch, messages=[msg("a")])
    await add_wf(db, q="malo")
    await add_wf(db, q="bueno")
    real = fake.execute

    async def flaky(fn, raw_input, **kw):
        if "malo" in raw_input["q"]:
            raise RuntimeError("boom")
        return await real(fn, raw_input, **kw)

    monkeypatch.setattr(etl, "execute", flaky)
    assert await etl.tick(db) == 2
    assert len(fake.launches) == 1


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
