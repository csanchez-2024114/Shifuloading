"""La plantilla tambien es el ejemplo de prueba que los juniors copian: se prueba con HTTP simulado."""
import importlib
import sys

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.core.security import encrypt_data
from app.functions.registry import get_function, isolated_registry, list_functions, validate_registry
from app.functions.runner import execute
from app.functions.spec import ErrorCode


@pytest.fixture
def template():
    with isolated_registry():
        for name in ("app.functions.apps._template.app_spec", "app.functions.apps._template.functions"):
            sys.modules.pop(name, None)  # forzar que el import registre de nuevo, ahora en el registro aislado
        importlib.import_module("app.functions.apps._template.functions")  # importa app_spec primero y registra la app
        validate_registry()
        yield


@pytest.fixture
async def db():
    d = AsyncMongoMockClient()["template_test"]
    await d[Collections.USER_CONNECTED_ACCOUNTS].insert_one({
        "user_id": "u1", "provider": "example", "account_id": "acc_1", "access_token": encrypt_data("tok"),
        "refresh_token": "n/a", "status": "active"})
    return d


def api(routes):
    def handler(req: httpx.Request) -> httpx.Response:
        return routes.get(req.url.path, httpx.Response(404))
    return httpx.MockTransport(handler)


def test_template_registers_two_valid_functions(template):
    assert [f.spec.id for f in list_functions()] == ["example.account.get", "example.items.list"]


async def test_items_list_normal_case(template, db):
    t = api({"/v1/items": httpx.Response(200, json={"items": [{"id": 1, "name": "Uno"}]})})
    res = await execute(get_function("example.items.list"), {"limit": 5}, db=db, user_id="u1", transport=t)
    assert res.ok and res.data == {"items": [{"id": "1", "name": "Uno"}]}


async def test_items_list_error_case(template, db):
    t = api({})  # la app responde 404
    res = await execute(get_function("example.items.list"), {}, db=db, user_id="u1", transport=t)
    assert res.error.code == ErrorCode.not_found


async def test_items_list_rejects_bad_input(template, db):
    res = await execute(get_function("example.items.list"), {"limit": 1000}, db=db, user_id="u1")
    assert res.error.code == ErrorCode.invalid_input


async def test_whoami(template, db):
    t = api({"/v1/me": httpx.Response(200, json={"id": "acc_1", "email": "ana@example.test"})})
    res = await execute(get_function("example.account.get"), {}, db=db, user_id="u1", transport=t)
    assert res.ok and res.data["account_id"] == "acc_1" and res.meta.account_id == "acc_1"
