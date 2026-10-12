import httpx
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.core.constants import Collections
from app.functions.registry import get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from functions_helpers import connection_doc

STREAM = {"id": "0b4f8e2a-0000-0000-0000-000000000000", "title": "En vivo", "broadcaster_user": {"id": 123456, "username": "empresademo"},
          "channel": {"slug": "empresademo"}, "category": {"id": 15, "name": "Just Chatting"}, "viewer_count": 42, "language_code": "es",
          "started_at": "2026-10-07T18:00:00Z", "has_mature_content": False, "tags": ["espanol"], "thumbnail": None}


@pytest.fixture(autouse=True, scope="module")
def _registry():
    load_all()


@pytest_asyncio.fixture
async def db():
    d = AsyncMongoMockClient()["kick_reads_test"]
    await d[Collections.USER_CONNECTED_ACCOUNTS].insert_one(connection_doc(account="123456", provider="kick", token="tok-k", refresh="ref-k"))
    return d


def api(routes):
    """`routes`: ruta -> cuerpo JSON (200). Cualquier otra ruta responde 404."""
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=routes[req.url.path]) if req.url.path in routes else httpx.Response(404, json={"message": "Not Found"})

    return httpx.MockTransport(handler), seen


async def run(fid, args, db, t):
    return await execute(get_function(fid), args, db=db, user_id="u1", transport=t)


@pytest.mark.asyncio
async def test_channel_get_by_slugs_repeats_param_and_hides_stream_key(db):
    t, seen = api({"/public/v1/channels": {"data": [{"broadcaster_user_id": 123456, "slug": "empresademo", "stream_title": "Hola",
                                                     "category": {"id": 15, "name": "Just Chatting"},
                                                     "stream": {"is_live": True, "viewer_count": 10, "key": "SECRET-KEY", "url": "rtmps://x"}}],
                                           "message": "OK"}})
    res = await run("kick.channel.get", {"slugs": ["empresademo", "otro"]}, db, t)
    assert seen[0].url.params.get_list("slug") == ["empresademo", "otro"] and "broadcaster_user_id" not in seen[0].url.params
    assert seen[0].headers["authorization"] == "Bearer tok-k"
    ch = res.data["channels"][0]
    assert res.ok and ch["is_live"] is True and ch["viewer_count"] == 10 and ch["category"]["id"] == "15"
    assert "SECRET-KEY" not in str(res.data) and "rtmps" not in str(res.data)


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [{"slugs": ["a"], "broadcaster_user_ids": ["1"]}, {"slugs": ["x" * 26]}, {"broadcaster_user_ids": ["abc"]}])
async def test_channel_get_rejects_invalid_input(db, args):
    t, seen = api({})
    assert (await run("kick.channel.get", args, db, t)).error.code == ErrorCode.invalid_input
    assert seen == []


@pytest.mark.asyncio
async def test_livestream_list_v2_with_filters_and_cursor(db):
    t, seen = api({"/public/v2/livestreams": {"data": [STREAM], "message": "OK", "pagination": {"next_cursor": "CUR2"}}})
    res = await run("kick.livestream.list", {"category_ids": ["15", "16"], "language_codes": ["es"], "limit": 5, "cursor": "CUR1"}, db, t)
    params = seen[0].url.params
    assert params.get_list("category_id") == ["15", "16"] and params["language_code"] == "es" and params["limit"] == "5" and params["cursor"] == "CUR1"
    assert res.ok and res.data["next_cursor"] == "CUR2"
    assert res.data["livestreams"][0] == {"id": STREAM["id"], "title": "En vivo", "broadcaster_user_id": "123456", "username": "empresademo",
                                          "slug": "empresademo", "category": {"id": "15", "name": "Just Chatting", "thumbnail": None},
                                          "viewer_count": 42, "language_code": "es", "started_at": "2026-10-07T18:00:00Z",
                                          "has_mature_content": False, "tags": ["espanol"], "thumbnail": None}


@pytest.mark.asyncio
async def test_livestream_list_last_page_has_no_cursor(db):
    t, _ = api({"/public/v2/livestreams": {"data": [], "message": "OK", "pagination": {"next_cursor": ""}}})
    res = await run("kick.livestream.list", {}, db, t)
    assert res.ok and res.data == {"livestreams": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_livestream_list_user_and_stats(db):
    t, seen = api({"/public/v1/users/livestreams": {"data": [STREAM], "message": "OK"},
                   "/public/v1/livestreams/stats": {"data": {"total_count": 15234}, "message": "OK"}})
    res = await run("kick.livestream.list_user", {"user_ids": ["123456", "7"]}, db, t)
    assert seen[0].url.params.get_list("user_id") == ["123456", "7"] and res.data["livestreams"][0]["slug"] == "empresademo"
    assert (await run("kick.livestream.get_stats", {}, db, t)).data == {"total_count": 15234}
    assert (await run("kick.livestream.list_user", {"user_ids": []}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_category_list_joins_arrays_with_commas(db):
    t, seen = api({"/public/v2/categories": {"data": [{"id": 15, "name": "Just Chatting", "tags": ["IRL"]}], "message": "OK",
                                             "pagination": {"next_cursor": None}}})
    res = await run("kick.category.list", {"names": ["Just Chatting", "Fortnite"], "ids": ["15", "16"]}, db, t)
    params = seen[0].url.params
    assert params["name"] == "Just Chatting,Fortnite" and params["id"] == "15,16" and "tag" not in params
    assert res.ok and res.data["categories"] == [{"id": "15", "name": "Just Chatting", "thumbnail": None, "tags": ["IRL"]}]
    assert (await run("kick.category.list", {"names": ["ab"]}, db, t)).error.code == ErrorCode.invalid_input


@pytest.mark.asyncio
async def test_rewards_and_redemptions(db):
    reward = {"id": "01JAXK8N4QWRTY5PM7ZEBVJDS8", "title": "Saludo", "cost": 500}
    t, seen = api({"/public/v1/channels/rewards": {"data": [{**reward, "is_enabled": True, "should_redemptions_skip_request_queue": True}],
                                                   "message": "OK"},
                   "/public/v1/channels/rewards/redemptions": {"data": [{"reward": reward, "redemptions": [
                       {"id": "01KAAFHJ2PNXS48NG8XXPGWKCZ", "status": "pending", "redeemer": {"user_id": 778899}, "user_input": "Hola"}]}],
                       "message": "OK", "pagination": {"next_cursor": "N"}}})
    rewards = await run("kick.channel_reward.list", {}, db, t)
    assert rewards.ok and rewards.data["rewards"][0]["skips_request_queue"] is True and rewards.data["rewards"][0]["is_enabled"] is True
    red = await run("kick.channel_reward.redemption_list", {"reward_id": reward["id"]}, db, t)
    assert dict(seen[1].url.params) == {"reward_id": reward["id"], "status": "pending"}
    assert red.data["next_cursor"] == "N" and red.data["redemptions"][0] == {
        "id": "01KAAFHJ2PNXS48NG8XXPGWKCZ", "reward_id": reward["id"], "reward_title": "Saludo", "status": "pending",
        "redeemer_user_id": "778899", "user_input": "Hola", "redeemed_at": None}
    await run("kick.channel_reward.redemption_list", {"ids": ["a", "b"], "status": "accepted"}, db, t)
    assert seen[2].url.params.get_list("id") == ["a", "b"] and "status" not in seen[2].url.params


@pytest.mark.asyncio
async def test_leaderboard_ads_public_key_and_subscriptions(db):
    t, seen = api({
        "/public/v1/kicks/leaderboard": {"data": {"week": [{"rank": 1, "user_id": 778899, "username": "fan", "gifted_amount": 250}],
                                                  "month": [], "lifetime": None}, "message": "OK"},
        "/public/v1/ads/ad-break-status": {"data": {"opted_in": True, "remaining_ad_breaks": 3, "limits": {"max": 4, "period_seconds": 3600},
                                                    "ad_breaks": [{"id": "x", "break_duration_seconds": 30}]}, "message": "OK"},
        "/public/v1/public-key": {"data": {"public_key": "-----BEGIN PUBLIC KEY-----"}, "message": "OK"},
        "/public/v1/events/subscriptions": {"data": [{"id": "s1", "event": "chat.message.sent", "version": 1, "broadcaster_user_id": 123456}],
                                            "message": "OK"},
    })
    board = await run("kick.kicks.leaderboard", {"top": 3}, db, t)
    assert seen[0].url.params["top"] == "3" and board.data["week"][0]["user_id"] == "778899" and board.data["lifetime"] == []
    ads = await run("kick.ads.ad_break_status", {}, db, t)
    assert ads.data["limit_max"] == 4 and ads.data["ad_breaks"][0]["duration_seconds"] == 30 and ads.data["ads_blocked"] is False
    assert (await run("kick.public_key.get", {}, db, t)).data["public_key"].startswith("-----BEGIN")
    subs = await run("kick.event.subscription_list", {"broadcaster_user_id": "123456"}, db, t)
    assert seen[3].url.params["broadcaster_user_id"] == "123456" and subs.data["subscriptions"][0]["broadcaster_user_id"] == "123456"


@pytest.mark.asyncio
async def test_response_without_data_is_upstream_changed(db):
    t, _ = api({"/public/v1/livestreams/stats": {"message": "OK"}})
    assert (await run("kick.livestream.get_stats", {}, db, t)).error.code == ErrorCode.upstream_changed


@pytest.mark.asyncio
async def test_forbidden_is_missing_scope(db):
    def handler(req):
        return httpx.Response(403, json={"message": "Forbidden"})

    res = await run("kick.kicks.leaderboard", {}, db, httpx.MockTransport(handler))
    assert res.error.code == ErrorCode.missing_scope
