"""whoami y conexion de las apps que por ahora solo tienen identidad: Jira, Facebook, Instagram, Threads, Kick y Discord."""
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.functions.registry import get_app, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS

# app -> (ruta llamada, respuesta de la plataforma, account_id esperado, display_name esperado)
CASES = {
    "jira": ("/me", {"account_id": "5b10ac8d82e05b22cc7d4ef5", "name": "Ana Perez", "email": "ana@empresa.test", "account_status": "active"},
             "5b10ac8d82e05b22cc7d4ef5", "Ana Perez"),
    "facebook": ("/v26.0/me", {"id": "10224567890123456", "name": "Ana Perez"}, "10224567890123456", "Ana Perez"),
    "instagram": ("/v26.0/me", {"data": [{"user_id": "17841400123456789", "username": "empresademo", "account_type": "Business"}]},
                  "17841400123456789", "empresademo"),
    "threads": ("/v1.0/me", {"id": "1234567890123456", "username": "empresademo", "name": "Empresa Demo"}, "1234567890123456", "empresademo"),
    "kick": ("/public/v1/users", {"data": [{"user_id": 123456, "name": "empresademo", "email": "ana@empresa.test"}], "message": "OK"},
             "123456", "empresademo"),
    "discord": ("/api/v10/users/@me", {"id": "80351110224678912", "username": "anaperez", "global_name": "Ana Perez"},
                "80351110224678912", "Ana Perez"),
}
ENVS = {
    "jira": ("JIRA_CLIENT_ID", "JIRA_CLIENT_SECRET"),
    "facebook": ("META_LOGIN_APP_ID", "META_LOGIN_APP_SECRET"),
    "instagram": ("META_INSTAGRAM_LOGIN_APP_ID", "META_INSTAGRAM_LOGIN_APP_SECRET"),
    "threads": ("THREADS_CLIENT_ID", "THREADS_CLIENT_SECRET"),
    "kick": ("KICK_CLIENT_ID", "KICK_CLIENT_SECRET"),
    "discord": ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET"),
}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    return AsyncMongoMockClient()["whoami_apps_test"]


def api(path, payload, status=200):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(status, json=payload) if req.url.path == path else httpx.Response(404)

    return httpx.MockTransport(handler), seen


@pytest.mark.asyncio
@pytest.mark.parametrize("app", sorted(CASES))
async def test_whoami_returns_the_stored_account_id(db, app):
    path, payload, account_id, name = CASES[app]
    await db[COL].insert_one(connection_doc(account=account_id, provider=app, token="tok-1"))
    t, seen = api(path, payload)
    res = await execute(get_function(get_app(app).whoami), {}, db=db, user_id="u1", transport=t)
    assert res.ok, res.error
    assert res.data["account_id"] == account_id == res.meta.account_id and res.data["display_name"] == name
    assert seen[0].method == "GET" and seen[0].headers["authorization"] == "Bearer tok-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("app", sorted(CASES))
async def test_whoami_rejected_token_expires_the_account(db, app):
    path, _, account_id, _ = CASES[app]
    await db[COL].insert_one(connection_doc(account=account_id, provider=app, token="tok-1"))
    t, _ = api(path, {"message": "401: Unauthorized"}, status=401)
    res = await execute(get_function(get_app(app).whoami), {}, db=db, user_id="u1", transport=t)
    assert res.error.code == ErrorCode.auth_expired
    assert (await db[COL].find_one({"account_id": account_id}))["status"] == "expired"


@pytest.mark.asyncio
async def test_kick_without_user_is_upstream_changed(db):
    await db[COL].insert_one(connection_doc(account="123456", provider="kick", token="tok-1"))
    t, _ = api("/public/v1/users", {"data": [], "message": "OK"})
    res = await execute(get_function("kick.user.get"), {}, db=db, user_id="u1", transport=t)
    assert res.error.code == ErrorCode.upstream_changed
