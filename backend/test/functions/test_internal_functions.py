import asyncio

import httpx
import pytest
from fastapi import FastAPI
from functions_helpers import DESC
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel, Field

from app.core.constants import Collections
from app.core.security import encrypt_data
from app.database import get_current_user, get_db
from app.functions import registry
from app.functions.context import Context
from app.functions.registry import function, isolated_registry, load_all, register_app
from app.functions.runner import execute as real_execute
from app.functions.spec import AppSpec, AuthSpec, AuthType, Verb
from app.routes.internal import functions as routes

COL = Collections.USER_CONNECTED_ACCOUNTS
BREVO = {"/v3/account": lambda req: httpx.Response(200, json={"email": "ana@empresa.test"})}


@pytest.fixture(scope="module", autouse=True)
def _loaded():
    load_all()


@pytest.fixture
def db():
    return AsyncMongoMockClient()["internal_test"]


@pytest.fixture
def external(monkeypatch):
    """Todo HTTP hacia las apps externas pasa por este transporte falso; guarda cada peticion."""
    state = {"routes": dict(BREVO), "seen": []}

    def handler(req: httpx.Request) -> httpx.Response:
        state["seen"].append(req)
        r = state["routes"].get(req.url.path, httpx.Response(404))
        return r(req) if callable(r) else r

    transport = httpx.MockTransport(handler)

    async def execute_with_transport(*a, **k):
        return await real_execute(*a, transport=transport, **k)

    monkeypatch.setattr(routes, "execute", execute_with_transport)
    return state


def make_app(db, user_id="u1", authenticated=True) -> FastAPI:
    app = FastAPI()
    app.state.db = db
    app.include_router(routes.router, prefix="/internal")
    app.dependency_overrides[get_db] = lambda: db
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: {"_id": user_id, "id": user_id}
    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def add_brevo(db, account="ana@empresa.test", key="KEY-1", user="u1"):
    await db[COL].insert_one({"user_id": user, "provider": "brevo", "account_id": account, "access_token": encrypt_data(key),
                              "refresh_token": "n/a", "status": "active"})


async def test_requires_authentication(db):
    async with client(make_app(db, authenticated=False)) as c:
        assert (await c.get("/internal/functions")).status_code == 401
        assert (await c.post("/internal/functions/brevo.account.get/test", json={})).status_code == 401


async def test_list_and_get(db):
    async with client(make_app(db)) as c:
        listing = (await c.get("/internal/functions")).json()["functions"]
        ids = {f["id"] for f in listing}
        assert {"brevo.account.get", "dropbox.files.list"} <= ids
        one = next(f for f in listing if f["id"] == "brevo.contacts.list")
        assert one["confirmation_policy"] == "assume" and one["verb"] == "read"
        detail = (await c.get("/internal/functions/dropbox.files.list")).json()
        assert detail["spec"]["input_schema"]["properties"]["limit"] and detail["app"]["auth"]["type"] == "oauth2_code"
        assert len(detail["spec_hash"]) == 64
        assert (await c.get("/internal/functions/nada.nada.nada")).status_code == 404


async def test_status_in_mongo_wins_over_the_code(db):
    await db[Collections.FUNCTIONS].insert_one({"id": "brevo.account.get", "version": 1, "status": "degraded"})
    async with client(make_app(db)) as c:
        st = {f["id"]: f["status"] for f in (await c.get("/internal/functions")).json()["functions"]}
        assert st["brevo.account.get"] == "degraded" and st["brevo.contacts.list"] == "draft"


async def test_test_uses_the_example_and_checks_identity(db, external):
    await add_brevo(db)
    async with client(make_app(db)) as c:
        r = (await c.post("/internal/functions/brevo.account.get/test", json={})).json()
    run = r["runs"][0]
    assert run["result"]["ok"] and run["identity"]["match"] is True and run["requested_account_id"] is None
    assert r["summary"] == {"runs": 1, "ok": 1, "failed": 0, "simulated": False, "identity_mismatches": 0}
    assert all(c["ok"] for c in r["function"]["spec_checks"])


async def test_several_accounts_one_result_each_and_no_crossing(db, external):
    await add_brevo(db, "ana@empresa.test", "KEY-A")
    await add_brevo(db, "bob@otra.test", "KEY-B")
    external["routes"]["/v3/account"] = lambda req: httpx.Response(200, json={"email": "ana@empresa.test" if req.headers["api-key"] == "KEY-A" else "bob@otra.test"})
    async with client(make_app(db)) as c:
        r = (await c.post("/internal/functions/brevo.account.get/test", json={"account_ids": ["ana@empresa.test", "bob@otra.test"]})).json()
    assert [x["result"]["meta"]["account_id"] for x in r["runs"]] == ["ana@empresa.test", "bob@otra.test"]
    assert [x["identity"]["match"] for x in r["runs"]] == [True, True] and r["summary"]["ok"] == 2
    assert [req.headers["api-key"] for req in external["seen"]] == ["KEY-A", "KEY-B"]


async def test_identity_mismatch_is_reported(db, external):
    await add_brevo(db, "ana@empresa.test")
    external["routes"]["/v3/account"] = httpx.Response(200, json={"email": "otra-persona@x.test"})  # respondio otra cuenta
    async with client(make_app(db)) as c:
        r = (await c.post("/internal/functions/brevo.account.get/test", json={})).json()
    assert r["runs"][0]["identity"]["match"] is False and r["summary"]["identity_mismatches"] == 1


async def test_without_connection_it_reports_the_error_not_a_crash(db, external):
    async with client(make_app(db)) as c:
        r = await c.post("/internal/functions/brevo.account.get/test", json={})
    assert r.status_code == 200 and r.json()["runs"][0]["result"]["error"]["code"] == "missing_connection"
    assert r.json()["summary"]["failed"] == 1


async def test_only_the_callers_own_connections_are_used(db, external):
    await add_brevo(db, user="u1")
    async with client(make_app(db, user_id="u2")) as c:
        r = (await c.post("/internal/functions/brevo.account.get/test", json={})).json()
    assert r["runs"][0]["result"]["error"]["code"] == "missing_connection" and external["seen"] == []


async def test_invalid_input_and_account_cap(db, external):
    await add_brevo(db)
    async with client(make_app(db)) as c:
        r = (await c.post("/internal/functions/brevo.contacts.list/test", json={"input": {"limit": 99999}})).json()
        assert r["runs"][0]["result"]["error"]["code"] == "invalid_input" and external["seen"] == []
        too_many = await c.post("/internal/functions/brevo.account.get/test", json={"account_ids": [str(i) for i in range(26)]})
        assert too_many.status_code == 422


async def test_kill_switch(db, monkeypatch):
    monkeypatch.setenv("FUNCTIONS_TEST_ENABLED", "false")
    async with client(make_app(db)) as c:
        assert (await c.get("/internal/functions")).status_code == 404
        assert (await c.post("/internal/functions/brevo.account.get/test", json={})).status_code == 404


async def test_each_test_is_audited(db, external):
    await add_brevo(db)
    async with client(make_app(db)) as c:
        await c.post("/internal/functions/brevo.account.get/test", json={})
    await asyncio.sleep(0.05)  # log_event es "dispara y olvida"
    ev = await db["audit_events"].find_one({"action": "function_tested"})
    assert ev and ev["resource"] == "brevo.account.get" and ev["user_id"] == "u1" and ev["extra"]["accounts"] == 1


class WIn(BaseModel):
    text: str = Field(default="hola", description="Text of the demo message to create")


class WOut(BaseModel):
    sent: bool


def with_write_function(monkeypatch):
    calls = []
    with isolated_registry():
        register_app(AppSpec(app="demo", provider_keys=["demo"], auth=AuthSpec(type=AuthType.none)))

        @function(id="demo.msg.create", version=1, verb=Verb.create, exits_outside=True, description=DESC,
                  examples=[{"input": {}, "output": {"sent": True}}])
        async def send(ctx: Context, args: WIn) -> WOut:
            calls.append(args.text)
            return WOut(sent=True)

        extra_apps, extra_funcs = dict(registry._APPS), dict(registry._FUNCS)
    for k, v in extra_apps.items():
        monkeypatch.setitem(registry._APPS, k, v)
    for k, v in extra_funcs.items():
        monkeypatch.setitem(registry._FUNCS, k, v)
    return calls


async def test_non_read_functions_are_simulated_unless_allowed(db, external, monkeypatch):
    calls = with_write_function(monkeypatch)
    async with client(make_app(db)) as c:
        sim = (await c.post("/internal/functions/demo.msg.create/test", json={})).json()
        assert sim["summary"]["simulated"] is True and sim["runs"][0]["result"]["meta"]["simulated"] is True and calls == []
        assert sim["runs"][0]["result"]["data"] == {"sent": True}
        real = (await c.post("/internal/functions/demo.msg.create/test", json={"allow_write": True, "input": {"text": "x"}})).json()
        assert real["summary"]["simulated"] is False and calls == ["x"]
