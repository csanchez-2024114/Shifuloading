import json

import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from functions_helpers import connection_doc
from app.functions.registry import get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode

COL = Collections.USER_CONNECTED_ACCOUNTS
ITEM = {"id": "987", "name": "Cliente Demo", "state": "active", "created_at": "2026-02-01T10:00:00Z", "updated_at": "2026-03-01T09:00:00Z",
        "group": {"id": "topics", "title": "Nuevos"}, "column_values": [{"id": "status", "type": "status", "text": "Working on it"}]}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["monday_test"]
    await d[COL].insert_one(connection_doc(account="4012689", provider="monday", token="tok-m"))
    return d


def api(responses):
    """Todo va a POST /v2: `responses` es una respuesta fija o una funcion del cuerpo GraphQL."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path != "/v2":
            return httpx.Response(404)
        return responses(json.loads(req.content)) if callable(responses) else responses

    return httpx.MockTransport(handler), seen


def gql(data):
    return httpx.Response(200, json={"data": data, "account_id": 18888528})


async def run(fid, args, db, t):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t)


@pytest.mark.asyncio
async def test_user_get_sends_raw_token_and_version_and_returns_user_id(db):
    t, seen = api(gql({"me": {"id": 4012689, "name": "Ana Perez", "email": "ana@empresa.test", "title": None, "status": "ACTIVE",
                              "account": {"id": 18888528, "name": "Empresa Demo", "slug": "empresademo"}}}))
    res = await run("monday.user.get", {}, db, t)
    assert res.ok and res.data["account_id"] == "4012689" and res.data["display_name"] == "Ana Perez" and res.data["status"] == "ACTIVE"
    assert res.data["monday_account_id"] == "18888528" and res.data["monday_account_slug"] == "empresademo"
    assert res.data["account_id"] == res.meta.account_id
    req = seen[0]
    assert req.method == "POST" and req.headers["authorization"] == "tok-m" and req.headers["api-version"] == "2026-10"
    query = json.loads(req.content)["query"]
    assert "me {" in query and "is_admin" not in query and "is_guest" not in query


@pytest.mark.asyncio
async def test_account_get_flattens_plan(db):
    t, _ = api(gql({"account": {"id": "18888528", "name": "Empresa Demo", "slug": "empresademo", "country_code": "GT",
                                "active_members_count": 3, "plan": {"tier": "free", "max_users": 2, "period": None}}}))
    res = await run("monday.account.get", {}, db, t)
    assert res.ok and res.data["plan_tier"] == "free" and res.data["plan_max_users"] == 2 and res.data["active_members_count"] == 3


@pytest.mark.asyncio
async def test_account_get_without_plan(db):
    t, _ = api(gql({"account": {"id": "1", "name": "X", "plan": None}}))
    res = await run("monday.account.get", {}, db, t)
    assert res.ok and res.data["plan_tier"] is None


@pytest.mark.asyncio
async def test_user_list_passes_filters_as_variables(db):
    t, seen = api(gql({"users": [{"id": 1, "name": "Ana", "email": "ana@empresa.test", "status": "PENDING", "user_config": {"kind": "guest"}}]}))
    res = await run("monday.user.list", {"emails": ["ana@empresa.test"], "kind": "guests", "limit": 10, "page": 2}, db, t)
    body = json.loads(seen[0].content)
    assert body["variables"] == {"limit": 10, "page": 2, "kind": "guests", "emails": ["ana@empresa.test"], "name": None}
    assert "$emails: [String!]" in body["query"] and "enabled" not in body["query"] and "is_admin" not in body["query"]
    assert res.ok and res.data["users"][0] == {"id": "1", "name": "Ana", "email": "ana@empresa.test", "title": None,
                                               "kind": "guest", "status": "PENDING"}


@pytest.mark.asyncio
async def test_workspace_list_defaults_to_active(db):
    t, seen = api(gql({"workspaces": [{"id": 551234, "name": "Ventas", "kind": "open", "state": "active"}]}))
    res = await run("monday.workspace.list", {}, db, t)
    assert json.loads(seen[0].content)["variables"] == {"limit": 25, "page": 1, "state": "active"}
    assert res.ok and res.data["workspaces"][0]["id"] == "551234"


@pytest.mark.asyncio
async def test_board_list_filters_by_workspace_and_maps_type(db):
    t, seen = api(gql({"boards": [{"id": "123", "name": "Pipeline", "state": "active", "board_kind": "public", "type": "board",
                                   "workspace_id": 551234, "items_count": 12, "url": "https://x.monday.com/boards/123"}]}))
    res = await run("monday.board.list", {"workspace_ids": ["551234"]}, db, t)
    variables = json.loads(seen[0].content)["variables"]
    assert variables["workspace_ids"] == ["551234"] and variables["order_by"] == "used_at"
    assert res.ok and res.data["boards"][0]["board_type"] == "board" and res.data["boards"][0]["workspace_id"] == "551234"


@pytest.mark.asyncio
async def test_item_list_first_page_then_cursor(db):
    def respond(body):
        if "next_items_page" in body["query"]:
            return gql({"next_items_page": {"cursor": None, "items": [ITEM]}})
        return gql({"boards": [{"items_page": {"cursor": "CUR1", "items": [ITEM]}}]})

    t, seen = api(respond)
    first = await run("monday.item.list", {"board_id": "123", "limit": 1}, db, t)
    assert json.loads(seen[0].content)["variables"] == {"ids": ["123"], "limit": 1}
    assert first.ok and first.data["cursor"] == "CUR1" and first.data["items"][0]["group_title"] == "Nuevos"
    assert first.data["items"][0]["column_values"] == [{"id": "status", "type": "status", "text": "Working on it"}]
    second = await run("monday.item.list", {"board_id": "123", "cursor": "CUR1"}, db, t)
    assert json.loads(seen[1].content)["variables"] == {"cursor": "CUR1", "limit": 25}
    assert second.ok and second.data["cursor"] is None


@pytest.mark.asyncio
async def test_item_list_unknown_board_is_not_found(db):
    t, _ = api(gql({"boards": []}))
    assert (await run("monday.item.list", {"board_id": "999"}, db, t)).error.code == ErrorCode.not_found


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [{"board_id": "abc"}, {"board_id": "1", "limit": 501}, {}])
async def test_item_list_rejects_invalid_input(db, args):
    t, seen = api(gql({}))
    assert (await run("monday.item.list", args, db, t)).error.code == ErrorCode.invalid_input
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected", [
    ("missingRequiredPermissions", ErrorCode.missing_scope),
    ("ResourceNotFoundException", ErrorCode.not_found),
    ("InvalidArgumentException", ErrorCode.invalid_input),
    ("COMPLEXITY_BUDGET_EXHAUSTED", ErrorCode.rate_limited),
])
async def test_graphql_errors_with_http_200_are_translated(db, code, expected):
    t, _ = api(httpx.Response(200, json={"data": None, "errors": [{"message": "nope", "extensions": {"code": code}}], "account_id": 1}))
    res = await run("monday.board.list", {}, db, t)
    assert res.error.code == expected
    assert (await db[COL].find_one({"account_id": "4012689"}))["status"] == "active"


@pytest.mark.asyncio
async def test_unauthorized_without_refresh_token_expires_the_account(db):
    t, seen = api(httpx.Response(401, json={"errors": [{"message": "Not Authenticated", "extensions": {"code": "UNAUTHENTICATED"}}]}))
    res = await run("monday.user.get", {}, db, t)
    assert res.error.code == ErrorCode.auth_expired and len(seen) == 1  # no hay refresh_token: no se intenta refrescar
    assert (await db[COL].find_one({"account_id": "4012689"}))["status"] == "expired"


@pytest.mark.asyncio
async def test_unexpected_response_shape_is_upstream_changed(db):
    t, _ = api(gql({"boards": [{"name": "sin id"}]}))
    assert (await run("monday.board.list", {}, db, t)).error.code == ErrorCode.upstream_changed
