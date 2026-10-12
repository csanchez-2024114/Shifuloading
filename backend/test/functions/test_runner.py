import asyncio

import httpx
import pytest
from functions_helpers import DESC
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel, Field

from app.core.constants import Collections
from app.core.security import encrypt_data
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function, get_function, isolated_registry, register_app
from app.functions.runner import execute
from app.functions.spec import AppSpec, AuthSpec, AuthType, ErrorCode, Verb

API = "https://api.example.test/v1/n"


class In(BaseModel):
    n: int = Field(default=1, description="A number used by the demo counter functions")


class Out(BaseModel):
    n: int


@pytest.fixture
def db():
    return AsyncMongoMockClient()["runner_test"]


async def add_account(db, account="A", token="tok-A", user="u1"):
    await db[Collections.USER_CONNECTED_ACCOUNTS].insert_one({
        "user_id": user, "provider": "demo", "account_id": account, "access_token": encrypt_data(token),
        "refresh_token": "n/a", "status": "active"})


def transport(status=200, body=None):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(status, json=body if body is not None else {"n": 7})

    return httpx.MockTransport(handler), seen


@pytest.fixture
def registry():
    with isolated_registry():
        register_app(AppSpec(app="demo", provider_keys=["demo"], auth=AuthSpec(type=AuthType.bearer)))

        @function(id="demo.counter.get", version=1, verb=Verb.read, description=DESC, examples=[{"input": {"n": 1}, "output": {"n": 5}}])
        async def counter_get(ctx: Context, args: In) -> Out:
            resp = await ctx.conn.request("GET", API)
            return Out(n=resp.json()["n"])

        @function(id="demo.counter.boom", version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])
        async def counter_boom(ctx: Context, args: In) -> Out:
            return Out(n=(await ctx.conn.request("GET", API)).json()["falta_este_campo"])

        @function(id="demo.counter.bad", version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])
        async def counter_bad(ctx: Context, args: In) -> Out:
            return Out.model_construct(n="no-es-int")  # el handler devuelve algo que no cumple output_schema

        @function(id="demo.counter.raise", version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])
        async def counter_raise(ctx: Context, args: In) -> Out:
            raise FunctionError(ErrorCode.not_found, "no existe")

        @function(id="demo.counter.slow", version=1, verb=Verb.read, description=DESC, examples=[{"input": {}}])
        async def counter_slow(ctx: Context, args: In) -> Out:
            await asyncio.sleep(1)
            return Out(n=1)

        yield


async def test_success_returns_data_and_meta(db, registry):
    await add_account(db)
    t, seen = transport()
    res = await execute(get_function("demo.counter.get"), {"n": 3}, db=db, user_id="u1", transport=t)
    assert res.ok and res.data == {"n": 7}
    assert res.meta.function_id == "demo.counter.get" and res.meta.version == 1
    assert res.meta.account_id == "A" and res.meta.simulated is False and res.meta.duration_ms >= 0
    assert seen[0].headers["authorization"] == "Bearer tok-A"


async def test_invalid_input_never_reaches_the_connection(registry):
    res = await execute(get_function("demo.counter.get"), {"n": "abc"}, db=None, user_id="u1")
    assert not res.ok and res.error.code == ErrorCode.invalid_input and "n" in res.error.message


async def test_connection_errors_become_results(db, registry):
    res = await execute(get_function("demo.counter.get"), {}, db=db, user_id="u1")
    assert res.error.code == ErrorCode.missing_connection and res.error.user_action == "connect_app"
    await add_account(db, "A")
    await add_account(db, "B", "tok-B")
    res = await execute(get_function("demo.counter.get"), {}, db=db, user_id="u1")
    assert res.error.code == ErrorCode.account_selection_required


async def test_account_id_is_passed_by_the_caller(db, registry):
    await add_account(db, "A", "tok-A")
    await add_account(db, "B", "tok-B")
    t, seen = transport()
    res = await execute(get_function("demo.counter.get"), {}, db=db, user_id="u1", account_id="B", transport=t)
    assert res.ok and res.meta.account_id == "B" and seen[0].headers["authorization"] == "Bearer tok-B"


async def test_handler_function_error_is_mapped(db, registry):
    await add_account(db)
    res = await execute(get_function("demo.counter.raise"), {}, db=db, user_id="u1")
    assert res.error.code == ErrorCode.not_found and res.error.message == "no existe"


async def test_unexpected_exception_is_upstream_changed_not_hidden(db, registry, caplog):
    await add_account(db)
    t, _ = transport()
    with caplog.at_level("ERROR", logger="functions.runner"):
        res = await execute(get_function("demo.counter.boom"), {}, db=db, user_id="u1", transport=t)
    assert res.error.code == ErrorCode.upstream_changed and "KeyError" in res.error.message
    assert any("demo.counter.boom" in r.getMessage() for r in caplog.records)  # quedo en el log


async def test_output_not_matching_schema_is_upstream_changed(db, registry):
    await add_account(db)
    res = await execute(get_function("demo.counter.bad"), {}, db=db, user_id="u1")
    assert res.error.code == ErrorCode.upstream_changed


async def test_timeout_is_upstream_down(db, registry):
    await add_account(db)
    res = await execute(get_function("demo.counter.slow"), {}, db=db, user_id="u1", timeout=0.05)
    assert res.error.code == ErrorCode.upstream_down


async def test_simulate_uses_the_example_and_needs_no_db_or_network(registry):
    res = await execute(get_function("demo.counter.get"), {}, db=None, user_id="u1", simulate=True)
    assert res.ok and res.data == {"n": 5} and res.meta.simulated is True
    still_validates = await execute(get_function("demo.counter.get"), {"n": "x"}, db=None, user_id="u1", simulate=True)
    assert still_validates.error.code == ErrorCode.invalid_input
