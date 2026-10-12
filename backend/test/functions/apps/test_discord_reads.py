import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.functions.registry import get_app, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

GUILD = "80351110224678912"


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["discord_reads_test"]
    await d[Collections.USER_CONNECTED_ACCOUNTS].insert_one(connection_doc(account="1", provider="discord", token="tok-d", refresh="ref-d"))
    return d


def api(routes, status=200):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        path = req.url.path.removeprefix("/api/v10")
        return httpx.Response(status, json=routes[path]) if path in routes else httpx.Response(404, json={"message": "Unknown", "code": 10004})

    return httpx.MockTransport(handler), seen


async def run(fid, args, db, t):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t)


def test_app_requests_only_user_scopes_without_approval():
    assert get_app("discord").auth.scopes == ["identify", "guilds", "guilds.members.read", "connections"]


@pytest.mark.asyncio
async def test_list_user_guilds_with_counts(db):
    t, seen = api({"/users/@me/guilds": [{"id": GUILD, "name": "Comunidad", "owner": True, "permissions": "8", "features": ["COMMUNITY"],
                                         "approximate_member_count": 120}]})
    res = await run("discord.guild.list_user_guilds", {"with_counts": True, "limit": 50}, db, t)
    assert dict(seen[0].url.params) == {"limit": "50", "with_counts": "true"} and seen[0].headers["authorization"] == "Bearer tok-d"
    assert res.ok and res.data["guilds"][0] == {"id": GUILD, "name": "Comunidad", "icon": None, "owner": True, "permissions": "8",
                                                "features": ["COMMUNITY"], "approximate_member_count": 120, "approximate_presence_count": None}


@pytest.mark.asyncio
async def test_guild_member_maps_roles_and_timeout(db):
    t, seen = api({f"/users/@me/guilds/{GUILD}/member": {"nick": "Ana", "roles": ["41771983423143936"], "joined_at": "2025-05-01T10:00:00+00:00",
                                                         "communication_disabled_until": "2026-10-10T00:00:00+00:00", "deaf": False, "mute": True}})
    res = await run("discord.guild.get_user_guild_member", {"guild_id": GUILD}, db, t)
    assert res.ok and res.data["role_ids"] == ["41771983423143936"] and res.data["mute"] is True
    assert res.data["timed_out_until"] == "2026-10-10T00:00:00+00:00" and res.data["guild_id"] == GUILD


@pytest.mark.asyncio
async def test_guild_member_unknown_guild_is_not_found_and_bad_id_is_rejected(db):
    t, seen = api({})
    assert (await run("discord.guild.get_user_guild_member", {"guild_id": GUILD}, db, t)).error.code == ErrorCode.not_found
    assert (await run("discord.guild.get_user_guild_member", {"guild_id": "../users"}, db, t)).error.code == ErrorCode.invalid_input
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_connections_visibility(db):
    t, _ = api({"/users/@me/connections": [{"type": "twitch", "id": "123", "name": "demo", "verified": True, "visibility": 1},
                                           {"type": "steam", "id": "9", "name": "x", "visibility": 0, "revoked": True}]})
    res = await run("discord.user.get_connections", {}, db, t)
    assert [(c["type"], c["visible"], c["revoked"]) for c in res.data["connections"]] == [("twitch", True, False), ("steam", False, True)]


@pytest.mark.asyncio
async def test_authorization_lists_granted_scopes(db):
    t, _ = api({"/oauth2/@me": {"application": {"id": "1558119283014373406", "name": "BunnyDrop"}, "scopes": ["identify", "guilds"],
                                "expires": "2026-10-16T14:00:00+00:00", "user": {"id": "1"}}})
    res = await run("discord.authorization.get", {}, db, t)
    assert res.ok and res.data["scopes"] == ["identify", "guilds"] and res.data["user_id"] == "1" and res.data["application_name"] == "BunnyDrop"


@pytest.mark.asyncio
async def test_forbidden_is_missing_scope(db):
    t, _ = api({"/users/@me/connections": {"message": "Missing Access", "code": 50001}}, status=403)
    assert (await run("discord.user.get_connections", {}, db, t)).error.code == ErrorCode.missing_scope
