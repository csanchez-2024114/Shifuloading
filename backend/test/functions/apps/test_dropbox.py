import json

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from functions_helpers import unseal
from functions_helpers import connection_doc
from app.functions.registry import get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode

COL = Collections.USER_CONNECTED_ACCOUNTS
FILE = {".tag": "file", "name": "nota.txt", "path_display": "/nota.txt", "id": "id:1", "size": 12, "server_modified": "2026-01-01T00:00:00Z"}
FOLDER = {".tag": "folder", "name": "Fotos", "path_display": "/Fotos", "id": "id:2"}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["dropbox_test"]
    await d[COL].insert_one(connection_doc(account="dbid:AAA", provider="dropbox", token="old-token", refresh="rt-1"))
    return d


def api(routes):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        r = routes.get(req.url.path, httpx.Response(404))
        return r(req) if callable(r) else r

    return httpx.MockTransport(handler), seen


async def run(fid, args, db, t, **kw):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t, **kw)


@pytest.mark.asyncio
async def test_account_get_posts_without_body_and_matches_stored_account(db):
    t, seen = api({"/2/users/get_current_account": httpx.Response(200, json={
        "account_id": "dbid:AAA", "email": "ana@empresa.test", "name": {"display_name": "Ana Perez"}})})
    res = await run("dropbox.account.get", {}, db, t)
    assert res.ok and res.data == {"account_id": "dbid:AAA", "email": "ana@empresa.test", "display_name": "Ana Perez"}
    assert seen[0].method == "POST" and seen[0].content == b"" and seen[0].headers["authorization"] == "Bearer old-token"
    assert res.data["account_id"] == res.meta.account_id


@pytest.mark.asyncio
async def test_list_normalizes_paths_and_parses_entries(db):
    t, seen = api({"/2/files/list_folder": httpx.Response(200, json={"entries": [FOLDER, FILE], "has_more": True, "cursor": "CUR"})})
    res = await run("dropbox.files.list", {"path": "/", "limit": 5}, db, t)
    assert json.loads(seen[0].content) == {"path": "", "limit": 5, "recursive": False}
    assert res.ok and res.data["has_more"] is True and res.data["cursor"] == "CUR"
    assert [e["type"] for e in res.data["entries"]] == ["folder", "file"] and res.data["entries"][1]["size"] == 12
    await run("dropbox.files.list", {"path": "Docs/2026"}, db, t)
    assert json.loads(seen[1].content)["path"] == "/Docs/2026"


@pytest.mark.asyncio
async def test_list_path_not_found_comes_as_409(db):
    t, _ = api({"/2/files/list_folder": httpx.Response(409, json={"error_summary": "path/not_found/..", "error": {".tag": "path"}})})
    res = await run("dropbox.files.list", {"path": "/nada"}, db, t)
    assert res.error.code == ErrorCode.not_found


@pytest.mark.asyncio
async def test_list_malformed_path_is_invalid_input(db):
    t, _ = api({"/2/files/list_folder": httpx.Response(409, json={"error_summary": "path/malformed_path/.."})})
    assert (await run("dropbox.files.list", {"path": "/x"}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_search_builds_options_and_unwraps_matches(db):
    match = {"metadata": {".tag": "metadata", "metadata": FILE}}
    t, seen = api({"/2/files/search_v2": httpx.Response(200, json={"matches": [match], "has_more": False})})
    res = await run("dropbox.files.search", {"query": "nota", "max_results": 3}, db, t)
    assert json.loads(seen[0].content) == {"query": "nota", "options": {"max_results": 3}}   # sin path: no se manda
    assert res.ok and res.data["matches"][0]["name"] == "nota.txt"
    await run("dropbox.files.search", {"query": "nota", "path": "Docs"}, db, t)
    assert json.loads(seen[1].content)["options"]["path"] == "/Docs"


@pytest.mark.asyncio
async def test_search_rejects_empty_query(db):
    assert (await run("dropbox.files.search", {"query": ""}, db, api({})[0])).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_retried(db, monkeypatch):
    monkeypatch.setenv("DROPBOX_CLIENT_ID", "cid")
    monkeypatch.setenv("DROPBOX_CLIENT_SECRET", "csecret")

    def listing(req):
        if req.headers["authorization"] == "Bearer fresh-token":
            return httpx.Response(200, json={"entries": [FILE], "has_more": False})
        return httpx.Response(401, json={"error": {".tag": "expired_access_token"}, "error_summary": "expired_access_token/.."})

    t, seen = api({"/2/files/list_folder": listing, "/oauth2/token": httpx.Response(200, json={"access_token": "fresh-token"})})
    res = await run("dropbox.files.list", {}, db, t)
    assert res.ok and len(seen) == 3  # 401, refresco, reintento
    doc = await db[COL].find_one({"account_id": "dbid:AAA"})
    assert unseal(doc["credentials_enc"]) == {"token": "fresh-token", "refresh_token": "rt-1"}


@pytest.mark.asyncio
async def test_missing_scope_is_not_confused_with_an_expired_token(db):
    body = {"error": {".tag": "missing_scope", "required_scope": "files.metadata.read"}, "error_summary": "missing_scope/.."}
    t, seen = api({"/2/files/list_folder": httpx.Response(401, json=body)})
    res = await run("dropbox.files.list", {}, db, t)
    assert res.error.code == ErrorCode.missing_scope and res.error.user_action == "grant_scopes"
    assert len(seen) == 1 and (await db[COL].find_one({"account_id": "dbid:AAA"}))["status"] == "active"


@pytest.mark.asyncio
async def test_unexpected_response_shape_is_upstream_changed(db):
    t, _ = api({"/2/files/list_folder": httpx.Response(200, json={"entries": [{"name": "sin-tag"}], "has_more": False})})
    assert (await run("dropbox.files.list", {}, db, t)).error.code == ErrorCode.upstream_changed
