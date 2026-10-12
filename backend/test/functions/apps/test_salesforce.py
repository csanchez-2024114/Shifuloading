"""Salesforce: conexion (AuthSpec) y whoami (salesforce.user.get, via /services/oauth2/userinfo)."""
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from functions_helpers import unseal
from app.functions.registry import get_app, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

COL = Collections.USER_CONNECTED_ACCOUNTS
USER_ID = "005xx000001SvogAAC"
USERINFO = {"sub": f"https://login.salesforce.com/id/00Dxx0000001gPLEAY/{USER_ID}", "user_id": USER_ID, "organization_id": "00Dxx0000001gPLEAY",
            "name": "Ana Perez", "email": "ana@empresa.test", "preferred_username": "ana@empresa.test", "zoneinfo": "America/Guatemala"}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["salesforce_test"]
    await d[COL].insert_one(connection_doc(account=USER_ID, provider="salesforce", token="tok-1"))
    return d


def api(status=200, payload=None):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "login.salesforce.com" and req.url.path == "/services/oauth2/userinfo":
            return httpx.Response(status, json=payload if payload is not None else USERINFO)
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


async def run(db, t):
    return await execute(get_function(get_app("salesforce").whoami), {}, db=db, user_id="u1", transport=t)


@pytest.mark.asyncio
async def test_whoami_returns_the_stored_account_id(db):
    t, seen = api()
    res = await run(db, t)
    assert res.ok, res.error
    assert res.data["account_id"] == USER_ID == res.meta.account_id and res.data["display_name"] == "Ana Perez"
    assert res.data["organization_id"] == "00Dxx0000001gPLEAY" and res.data["username"] == "ana@empresa.test"
    assert seen[0].method == "GET" and seen[0].headers["authorization"] == "Bearer tok-1"


@pytest.mark.asyncio
async def test_whoami_rejected_token_expires_the_account(db):
    t, _ = api(401, {"error": "invalid_token", "error_description": "expired access/refresh token"})
    res = await run(db, t)
    assert res.error.code == ErrorCode.auth_expired
    assert (await db[COL].find_one({"account_id": USER_ID}))["status"] == "expired"


@pytest.mark.asyncio
async def test_whoami_without_user_id_is_an_error(db):
    t, _ = api(200, {"name": "Ana Perez"})
    res = await run(db, t)
    assert not res.ok


@pytest.mark.asyncio
async def test_whoami_missing_scope_is_403_and_does_not_expire_the_account(db):
    t, seen = api(403, {"error": "insufficient_scope"})
    res = await run(db, t)
    assert res.error.code == ErrorCode.missing_scope and res.error.user_action == "grant_scopes"
    assert len(seen) == 1 and (await db[COL].find_one({"account_id": USER_ID}))["status"] == "active"


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_retried(monkeypatch):
    monkeypatch.setenv("SALESFORCE_CLIENT_ID", "cid")
    monkeypatch.setenv("SALESFORCE_CLIENT_SECRET", "csecret")
    d = AsyncMongoMockClient()["salesforce_refresh_test"]
    await d[COL].insert_one(connection_doc(account=USER_ID, provider="salesforce", token="old-token", refresh="rt-1"))
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/services/oauth2/token":  # Salesforce no manda un refresh_token nuevo al renovar
            return httpx.Response(200, json={"access_token": "fresh-token", "instance_url": "https://acme.my.salesforce.com"})
        if req.headers["authorization"] == "Bearer fresh-token":
            return httpx.Response(200, json=USERINFO)
        return httpx.Response(401, json={"error": "invalid_token"})

    res = await run(d, httpx.MockTransport(handler))
    assert res.ok and len(seen) == 3  # 401, refresco, reintento
    assert unseal((await d[COL].find_one({"account_id": USER_ID}))["credentials_enc"]) == {"token": "fresh-token", "refresh_token": "rt-1"}
