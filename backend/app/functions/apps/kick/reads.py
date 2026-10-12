"""Lecturas de Kick (canales, livestreams, categorias, recompensas, KICKs, anuncios, eventos y llave publica). Las importa functions.py al final.

Verificado en docs.kick.com (OpenAPI de cada pagina, 2026-10-07). Diferencias con el catalogo generado por IA:
- `GET /public/v1/livestreams`, `GET /public/v1/categories` y `GET /public/v1/categories/{id}` estan marcados deprecated: se usan
  `/public/v2/livestreams` y `/public/v2/categories` (paginados con cursor). No se implementan las versiones viejas.
- Los arreglos de `/channels`, `/v2/livestreams` y `/users/livestreams` van repetidos (`?slug=a&slug=b`); los de `/v2/categories` van
  separados por comas (`explode: false`).
- `GET /public/v1/drops/claims` pide un token de app de una ORGANIZACION (client credentials), no el token del usuario: no encaja en una
  cuenta conectada. Pendiente de decidir con Alan; no se implementa.
- La respuesta de canal puede traer `stream.key` y `stream.url` (con streamkey:read): nunca se devuelven.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.kick.functions import API_URL
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

API_V2 = "https://api.kick.com/public/v2"


async def _data(ctx: Context, url: str, params: Optional[dict[str, Any]] = None) -> Any:
    body = (await ctx.conn.request("GET", url, params={k: v for k, v in (params or {}).items() if v not in (None, [])})).json()
    if not isinstance(body, dict) or "data" not in body:
        raise FunctionError(ErrorCode.upstream_changed, "Kick respondio sin el campo data.")
    return body


def _sid(value: Any) -> Optional[str]:
    return str(value) if value is not None else None


class NoArgs(BaseModel):
    pass


class Category(BaseModel):
    id: str = Field(description="Kick category id")
    name: Optional[str] = Field(default=None, description="Name of the category, for example Just Chatting")
    thumbnail: Optional[str] = Field(default=None, description="Link to the thumbnail image of the category")


def _category(raw: Optional[dict[str, Any]]) -> Optional[Category]:
    return Category(id=str(raw["id"]), name=raw.get("name"), thumbnail=raw.get("thumbnail")) if raw and raw.get("id") is not None else None


# --- kick.channel.get ----------------------------------------------------------------------------

class ChannelGetIn(BaseModel):
    slugs: list[str] = Field(default_factory=list, max_length=50, description="Channel slugs (names in the channel link), up to 50; leave empty for your own channel")
    broadcaster_user_ids: list[str] = Field(default_factory=list, max_length=50, description="Broadcaster user ids, up to 50; cannot be combined with slugs")

    @model_validator(mode="after")
    def _not_both(self) -> "ChannelGetIn":
        if self.slugs and self.broadcaster_user_ids:
            raise ValueError("give slugs or broadcaster_user_ids, not both")
        if any(len(s) > 25 or not s for s in self.slugs):
            raise ValueError("each slug must have 1 to 25 characters")
        if any(not s.isdigit() for s in self.broadcaster_user_ids):
            raise ValueError("broadcaster_user_ids must be digits")
        return self


class Channel(BaseModel):
    broadcaster_user_id: str = Field(description="User id of the channel owner")
    slug: str = Field(description="Channel slug, the name used in the channel link")
    stream_title: Optional[str] = Field(default=None, description="Current or last title of the stream")
    description: Optional[str] = Field(default=None, description="Description of the channel")
    banner_picture: Optional[str] = Field(default=None, description="Link to the banner image of the channel")
    category: Optional[Category] = Field(default=None, description="Category the channel is set to")
    is_live: bool = Field(default=False, description="True if the channel is streaming right now")
    viewer_count: Optional[int] = Field(default=None, description="Current viewers when live")
    language: Optional[str] = Field(default=None, description="Language of the stream")
    is_mature: bool = Field(default=False, description="True if the stream is marked for mature audiences")
    started_at: Optional[str] = Field(default=None, description="When the current stream started, if live")
    custom_tags: list[str] = Field(default_factory=list, description="Custom tags of the stream")
    active_subscribers_count: Optional[int] = Field(default=None, description="Active paid subscribers, only for your own channel")
    active_gifted_subscribers_count: Optional[int] = Field(default=None, description="Active gifted subscribers, only for your own channel")
    canceled_subscribers_count: Optional[int] = Field(default=None, description="Canceled subscribers, only for your own channel")


class ChannelGetOut(BaseModel):
    channels: list[Channel] = Field(description="Channels found; unknown slugs or ids are simply missing")


@function(
    id="kick.channel.get", version=1, verb=Verb.read, upstream_api="public/v1", scopes=["channel:read"],
    description=(
        "Returns Kick channel information: by default the channel of the connected account, or up to 50 channels by slug or by broadcaster user id. "
        "Each channel has its owner id, slug, stream title, description, banner, category, whether it is live with viewers, language, tags and, for "
        "your own channel, subscriber counts. Use it when the user asks about their Kick channel, whether a streamer is live, or what category they "
        "stream. The stream key is never returned. Read-only: it does not change the channel."
    ),
    examples=[{"name": "default", "input": {}, "output": {"channels": [
        {"broadcaster_user_id": "123456", "slug": "empresademo", "stream_title": "Hablando con la comunidad", "description": None,
         "banner_picture": None, "category": {"id": "15", "name": "Just Chatting", "thumbnail": None}, "is_live": False, "viewer_count": 0,
         "language": "es", "is_mature": False, "started_at": None, "custom_tags": [], "active_subscribers_count": 3,
         "active_gifted_subscribers_count": 0, "canceled_subscribers_count": 1}]}}],
)
async def channel_get(ctx: Context, args: ChannelGetIn) -> ChannelGetOut:
    body = await _data(ctx, f"{API_URL}/channels", {"slug": args.slugs, "broadcaster_user_id": args.broadcaster_user_ids})
    channels = []
    for c in body["data"] or []:
        stream = c.get("stream") or {}
        channels.append(Channel(
            broadcaster_user_id=str(c["broadcaster_user_id"]), slug=c["slug"], stream_title=c.get("stream_title"),
            description=c.get("channel_description"), banner_picture=c.get("banner_picture"), category=_category(c.get("category")),
            is_live=bool(stream.get("is_live")), viewer_count=stream.get("viewer_count"), language=stream.get("language"),
            is_mature=bool(stream.get("is_mature")), started_at=stream.get("start_time"), custom_tags=stream.get("custom_tags") or [],
            active_subscribers_count=c.get("active_subscribers_count"), active_gifted_subscribers_count=c.get("active_gifted_subscribers_count"),
            canceled_subscribers_count=c.get("canceled_subscribers_count")))
    return ChannelGetOut(channels=channels)


# --- kick.livestream.list / kick.livestream.list_user --------------------------------------------

class Livestream(BaseModel):
    id: str = Field(description="Livestream id")
    title: Optional[str] = Field(default=None, description="Title of the livestream")
    broadcaster_user_id: Optional[str] = Field(default=None, description="User id of the streamer")
    username: Optional[str] = Field(default=None, description="Username of the streamer")
    slug: Optional[str] = Field(default=None, description="Channel slug of the streamer")
    category: Optional[Category] = Field(default=None, description="Category being streamed")
    viewer_count: Optional[int] = Field(default=None, description="Current number of viewers")
    language_code: Optional[str] = Field(default=None, description="Language of the livestream as a BCP 47 tag, for example es or en")
    started_at: Optional[str] = Field(default=None, description="When the livestream started")
    has_mature_content: bool = Field(default=False, description="True if marked for mature audiences")
    tags: list[str] = Field(default_factory=list, description="Tags of the livestream")
    thumbnail: Optional[str] = Field(default=None, description="Link to the current thumbnail of the livestream")


def _livestream(raw: dict[str, Any]) -> Livestream:
    user = raw.get("broadcaster_user") or {}
    return Livestream(id=str(raw["id"]), title=raw.get("title"), broadcaster_user_id=_sid(user.get("id")), username=user.get("username"),
                      slug=(raw.get("channel") or {}).get("slug"), category=_category(raw.get("category")), viewer_count=raw.get("viewer_count"),
                      language_code=raw.get("language_code"), started_at=raw.get("started_at"), has_mature_content=bool(raw.get("has_mature_content")),
                      tags=raw.get("tags") or [], thumbnail=raw.get("thumbnail"))


class ListLivestreamsIn(BaseModel):
    category_ids: list[str] = Field(default_factory=list, max_length=25, description="Only livestreams in these category ids, up to 25; leave empty for all")
    language_codes: list[str] = Field(default_factory=list, max_length=25, description="Only livestreams in these languages (BCP 47, for example es), up to 25")
    limit: int = Field(default=25, ge=1, le=100, description="How many livestreams to return, from 1 to 100 (default 25)")
    cursor: Optional[str] = Field(default=None, description="Cursor returned by the previous page, to read the next page")


class ListLivestreamsOut(BaseModel):
    livestreams: list[Livestream] = Field(description="Active livestreams of this page, oldest first")
    next_cursor: Optional[str] = Field(default=None, description="Pass it as cursor to read the next page; empty on the last page")


@function(
    id="kick.livestream.list", version=1, verb=Verb.read, upstream_api="public/v2", scopes=[],
    description=(
        "Lists livestreams that are live on Kick right now, optionally only in some categories or languages, with cursor pagination. Each livestream "
        "has its id, title, streamer id, username and slug, category, viewer count, language, start time, tags and thumbnail. Use it when the user "
        "asks who is streaming a game or category, or wants to scout live channels in a language. Results are sorted oldest first. Read-only. For "
        "specific streamers use kick.livestream.list_user."
    ),
    examples=[{"name": "default", "input": {"language_codes": ["es"], "limit": 1}, "output": {"livestreams": [
        {"id": "0b4f8e2a-0000-0000-0000-000000000000", "title": "Jugando con subs", "broadcaster_user_id": "123456", "username": "empresademo",
         "slug": "empresademo", "category": {"id": "15", "name": "Just Chatting", "thumbnail": None}, "viewer_count": 42, "language_code": "es",
         "started_at": "2026-10-07T18:00:00Z", "has_mature_content": False, "tags": ["espanol"], "thumbnail": None}], "next_cursor": "abc123"}}],
)
async def livestream_list(ctx: Context, args: ListLivestreamsIn) -> ListLivestreamsOut:
    body = await _data(ctx, f"{API_V2}/livestreams", {"category_id": args.category_ids, "language_code": args.language_codes,
                                                     "limit": args.limit, "cursor": args.cursor})
    return ListLivestreamsOut(livestreams=[_livestream(s) for s in body["data"] or []],
                              next_cursor=(body.get("pagination") or {}).get("next_cursor") or None)


class ListUserLivestreamsIn(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=100, description="Broadcaster user ids to check, from 1 to 100")

    @model_validator(mode="after")
    def _digits(self) -> "ListUserLivestreamsIn":
        if any(not u.isdigit() for u in self.user_ids):
            raise ValueError("user_ids must be digits")
        return self


class ListUserLivestreamsOut(BaseModel):
    livestreams: list[Livestream] = Field(description="Active livestreams of those users; users who are offline are missing")


@function(
    id="kick.livestream.list_user", version=1, verb=Verb.read, upstream_api="public/v1", scopes=[],
    description=(
        "Returns the active Kick livestreams of up to 100 given broadcaster user ids: users who are offline are simply missing from the result. Each "
        "livestream has its id, title, streamer, category, viewer count, language, start time, tags and thumbnail. Use it when the user asks whether "
        "some specific streamers are live right now and what they are streaming. Get user ids with kick.channel.get. Read-only."
    ),
    examples=[{"name": "default", "input": {"user_ids": ["123456"]}, "output": {"livestreams": []}}],
)
async def livestream_list_user(ctx: Context, args: ListUserLivestreamsIn) -> ListUserLivestreamsOut:
    body = await _data(ctx, f"{API_URL}/users/livestreams", {"user_id": args.user_ids})
    return ListUserLivestreamsOut(livestreams=[_livestream(s) for s in body["data"] or []])


# --- kick.livestream.get_stats -------------------------------------------------------------------

class LivestreamStatsOut(BaseModel):
    total_count: int = Field(description="Number of livestreams that are live on Kick right now")


@function(
    id="kick.livestream.get_stats", version=1, verb=Verb.read, upstream_api="public/v1", scopes=[],
    description=(
        "Returns how many livestreams are live on the whole Kick platform right now. Use it when the user asks how busy Kick is, or to give context "
        "next to their own viewer numbers, for example before deciding when to go live. It takes no parameters and only returns the total count; to "
        "see which streams are live use kick.livestream.list. Read-only: it does not change anything on Kick."
    ),
    examples=[{"name": "default", "input": {}, "output": {"total_count": 15234}}],
)
async def livestream_get_stats(ctx: Context, args: NoArgs) -> LivestreamStatsOut:
    data = (await _data(ctx, f"{API_URL}/livestreams/stats"))["data"] or {}
    if "total_count" not in data:
        raise FunctionError(ErrorCode.upstream_changed, "Kick no devolvio total_count.")
    return LivestreamStatsOut(total_count=data["total_count"])


# --- kick.category.list --------------------------------------------------------------------------

class ListCategoriesIn(BaseModel):
    names: list[str] = Field(default_factory=list, max_length=20, description="Search categories by these names (3 to 100 characters each)")
    tags: list[str] = Field(default_factory=list, max_length=20, description="Only categories with these tags (3 to 100 characters each)")
    ids: list[str] = Field(default_factory=list, max_length=100, description="Return only these category ids")
    limit: int = Field(default=25, ge=1, le=100, description="How many categories to return, from 1 to 100 (default 25)")
    cursor: Optional[str] = Field(default=None, min_length=4, max_length=28, description="Cursor returned by the previous page, to read the next page")

    @model_validator(mode="after")
    def _check(self) -> "ListCategoriesIn":
        if any(not 3 <= len(v) <= 100 or "," in v for v in self.names + self.tags):
            raise ValueError("names and tags need 3 to 100 characters and no commas")
        if any(not i.isdigit() for i in self.ids):
            raise ValueError("ids must be digits")
        return self


class CategoryWithTags(Category):
    tags: list[str] = Field(default_factory=list, description="Tags of the category")


class ListCategoriesOut(BaseModel):
    categories: list[CategoryWithTags] = Field(description="Categories of this page")
    next_cursor: Optional[str] = Field(default=None, description="Pass it as cursor to read the next page; empty on the last page")


@function(
    id="kick.category.list", version=1, verb=Verb.read, upstream_api="public/v2", scopes=[],
    description=(
        "Lists Kick categories (games and topics such as Just Chatting), optionally searched by name, filtered by tag or limited to some category ids, "
        "with cursor pagination. Each category has its id, name, thumbnail and tags. Use it when the user mentions a game or topic and you need its "
        "Kick category id, for example to list livestreams in it or to set the category of a stream. Read-only: it does not change anything."
    ),
    examples=[{"name": "default", "input": {"names": ["Just Chatting"], "limit": 1}, "output": {"categories": [
        {"id": "15", "name": "Just Chatting", "thumbnail": None, "tags": ["IRL"]}], "next_cursor": None}}],
)
async def category_list(ctx: Context, args: ListCategoriesIn) -> ListCategoriesOut:
    params = {"name": ",".join(args.names) or None, "tag": ",".join(args.tags) or None, "id": ",".join(args.ids) or None,
              "limit": args.limit, "cursor": args.cursor}
    body = await _data(ctx, f"{API_V2}/categories", params)
    return ListCategoriesOut(
        categories=[CategoryWithTags(id=str(c["id"]), name=c.get("name"), thumbnail=c.get("thumbnail"), tags=c.get("tags") or [])
                    for c in body["data"] or []],
        next_cursor=(body.get("pagination") or {}).get("next_cursor") or None)


# --- kick.channel_reward.list --------------------------------------------------------------------

class Reward(BaseModel):
    id: str = Field(description="Reward id")
    title: str = Field(description="Title of the reward shown to viewers")
    description: Optional[str] = Field(default=None, description="Description of the reward")
    cost: Optional[int] = Field(default=None, description="Cost of the reward in channel points")
    background_color: Optional[str] = Field(default=None, description="Background color as a HEX code")
    is_enabled: bool = Field(default=False, description="True if the reward is enabled")
    is_paused: bool = Field(default=False, description="True if redemptions are paused")
    is_user_input_required: bool = Field(default=False, description="True if viewers must type a message when redeeming")
    skips_request_queue: bool = Field(default=False, description="True if redemptions are accepted automatically without the queue")


class ListRewardsOut(BaseModel):
    rewards: list[Reward] = Field(description="Channel point rewards of your channel")


@function(
    id="kick.channel_reward.list", version=1, verb=Verb.read, upstream_api="public/v1", scopes=["channel:rewards:read"],
    description=(
        "Lists the channel point rewards of the connected Kick channel (at most 50): id, title, description, cost in points, color and whether each "
        "reward is enabled, paused, asks viewers for a message or skips the request queue. Use it when the user asks which rewards their viewers can "
        "redeem, or needs a reward id to read its redemptions with kick.channel_reward.redemption_list. Read-only: it does not create, change or "
        "delete rewards."
    ),
    examples=[{"name": "default", "input": {}, "output": {"rewards": [
        {"id": "01JAXK8N4QWRTY5PM7ZEBVJDS8", "title": "Saludo en stream", "description": None, "cost": 500, "background_color": "#00e701",
         "is_enabled": True, "is_paused": False, "is_user_input_required": True, "skips_request_queue": False}]}}],
)
async def channel_reward_list(ctx: Context, args: NoArgs) -> ListRewardsOut:
    body = await _data(ctx, f"{API_URL}/channels/rewards")
    return ListRewardsOut(rewards=[
        Reward(id=str(r["id"]), title=r["title"], description=r.get("description"), cost=r.get("cost"), background_color=r.get("background_color"),
               is_enabled=bool(r.get("is_enabled")), is_paused=bool(r.get("is_paused")), is_user_input_required=bool(r.get("is_user_input_required")),
               skips_request_queue=bool(r.get("should_redemptions_skip_request_queue")))
        for r in body["data"] or []])


# --- kick.channel_reward.redemption_list ---------------------------------------------------------

class ListRedemptionsIn(BaseModel):
    reward_id: Optional[str] = Field(default=None, pattern=r"^[0-9A-Za-z]{26}$", description="Only redemptions of this reward id (from kick.channel_reward.list)")
    status: Literal["pending", "accepted", "rejected"] = Field(default="pending", description="Only redemptions in this state: pending (default), accepted or rejected")
    ids: list[str] = Field(default_factory=list, max_length=25, description="Only these redemption ids; cannot be combined with the other filters")
    cursor: Optional[str] = Field(default=None, description="Cursor returned by the previous page, to read the next page")


class Redemption(BaseModel):
    id: str = Field(description="Redemption id")
    reward_id: Optional[str] = Field(default=None, description="Id of the redeemed reward")
    reward_title: Optional[str] = Field(default=None, description="Title of the redeemed reward")
    status: Optional[str] = Field(default=None, description="pending, accepted or rejected")
    redeemer_user_id: Optional[str] = Field(default=None, description="User id of the viewer who redeemed it")
    user_input: Optional[str] = Field(default=None, description="Message typed by the viewer, if the reward asks for one")
    redeemed_at: Optional[str] = Field(default=None, description="When the reward was redeemed")


class ListRedemptionsOut(BaseModel):
    redemptions: list[Redemption] = Field(description="Redemptions of this page")
    next_cursor: Optional[str] = Field(default=None, description="Pass it as cursor to read the next page; empty on the last page")


@function(
    id="kick.channel_reward.redemption_list", version=1, verb=Verb.read, upstream_api="public/v1", scopes=["channel:rewards:read"],
    description=(
        "Lists channel point redemptions of the connected Kick channel, pending by default or accepted or rejected, optionally only for one reward or "
        "for some redemption ids, with cursor pagination. Each redemption has its id, reward, status, the viewer user id, the message the viewer typed "
        "and when it was redeemed. Use it when the user asks which rewards are waiting in the queue or who redeemed something. Read-only: it does not "
        "accept or reject redemptions."
    ),
    examples=[{"name": "default", "input": {}, "output": {"redemptions": [
        {"id": "01KAAFHJ2PNXS48NG8XXPGWKCZ", "reward_id": "01JAXK8N4QWRTY5PM7ZEBVJDS8", "reward_title": "Saludo en stream", "status": "pending",
         "redeemer_user_id": "778899", "user_input": "Saludos desde Guatemala", "redeemed_at": "2026-10-07T19:00:00Z"}], "next_cursor": None}}],
)
async def channel_reward_redemption_list(ctx: Context, args: ListRedemptionsIn) -> ListRedemptionsOut:
    params: dict[str, Any] = {"id": args.ids, "cursor": args.cursor} if args.ids else {
        "reward_id": args.reward_id, "status": args.status, "cursor": args.cursor}
    body = await _data(ctx, f"{API_URL}/channels/rewards/redemptions", params)
    redemptions = []
    for group in body["data"] or []:
        reward = group.get("reward") or {}
        for r in group.get("redemptions") or []:
            redemptions.append(Redemption(id=str(r["id"]), reward_id=_sid(reward.get("id")), reward_title=reward.get("title"), status=r.get("status"),
                                          redeemer_user_id=_sid((r.get("redeemer") or {}).get("user_id")), user_input=r.get("user_input"),
                                          redeemed_at=r.get("redeemed_at")))
    return ListRedemptionsOut(redemptions=redemptions, next_cursor=(body.get("pagination") or {}).get("next_cursor") or None)


# --- kick.kicks.leaderboard ----------------------------------------------------------------------

class LeaderboardIn(BaseModel):
    top: int = Field(default=10, ge=1, le=100, description="How many entries from the top of each leaderboard, from 1 to 100 (default 10)")


class LeaderboardEntry(BaseModel):
    rank: Optional[int] = Field(default=None, description="Position in the leaderboard, 1 is the top gifter")
    user_id: Optional[str] = Field(default=None, description="User id of the gifter")
    username: Optional[str] = Field(default=None, description="Username of the gifter")
    gifted_amount: Optional[int] = Field(default=None, description="KICKs gifted in that period")


class LeaderboardOut(BaseModel):
    week: list[LeaderboardEntry] = Field(default_factory=list, description="Top gifters of this week")
    month: list[LeaderboardEntry] = Field(default_factory=list, description="Top gifters of this month")
    lifetime: list[LeaderboardEntry] = Field(default_factory=list, description="Top gifters of all time")


@function(
    id="kick.kicks.leaderboard", version=1, verb=Verb.read, upstream_api="public/v1", scopes=["kicks:read"],
    description=(
        "Returns the KICKs gifting leaderboards of the connected Kick channel for this week, this month and all time: rank, user id, username and "
        "amount of KICKs gifted by each top supporter, up to 100 entries per period. Use it when the user asks who their biggest supporters are, wants "
        "to thank top gifters on stream, or compares support across periods. Read-only: it does not send or change KICKs."
    ),
    examples=[{"name": "default", "input": {"top": 1}, "output": {
        "week": [{"rank": 1, "user_id": "778899", "username": "fan_uno", "gifted_amount": 250}], "month": [], "lifetime": []}}],
)
async def kicks_leaderboard(ctx: Context, args: LeaderboardIn) -> LeaderboardOut:
    data = (await _data(ctx, f"{API_URL}/kicks/leaderboard", {"top": args.top}))["data"] or {}

    def entries(rows: Optional[list[dict[str, Any]]]) -> list[LeaderboardEntry]:
        return [LeaderboardEntry(rank=e.get("rank"), user_id=_sid(e.get("user_id")), username=e.get("username"), gifted_amount=e.get("gifted_amount"))
                for e in rows or []]

    return LeaderboardOut(week=entries(data.get("week")), month=entries(data.get("month")), lifetime=entries(data.get("lifetime")))


# --- kick.ads.ad_break_status --------------------------------------------------------------------

class AdBreak(BaseModel):
    id: Optional[str] = Field(default=None, description="Ad break id")
    status: Optional[str] = Field(default=None, description="State of the ad break")
    source: Optional[str] = Field(default=None, description="Who started it, for example manual or automatic")
    duration_seconds: Optional[int] = Field(default=None, description="Length of the ad break in seconds")
    created_at: Optional[str] = Field(default=None, description="When the ad break was created")


class AdBreakStatusOut(BaseModel):
    opted_in: bool = Field(description="True if the channel is enrolled in Kick ads")
    ads_blocked: bool = Field(description="True if ads are blocked for the channel")
    auto_ads_active: bool = Field(description="True if automatic ads are running")
    remaining_ad_breaks: Optional[int] = Field(default=None, description="Ad breaks that can still be started in the current period")
    limit_max: Optional[int] = Field(default=None, description="Maximum ad breaks allowed per period")
    limit_period_seconds: Optional[int] = Field(default=None, description="Length of that period in seconds")
    ad_breaks: list[AdBreak] = Field(default_factory=list, description="Recent ad breaks of the channel")


@function(
    id="kick.ads.ad_break_status", version=1, verb=Verb.read, upstream_api="public/v1", scopes=["ads:read"],
    description=(
        "Returns the ads state of the connected Kick channel: whether it is enrolled in ads, whether ads are blocked or automatic ads are running, how "
        "many ad breaks remain in the current period and the limits, plus the recent ad breaks with their status, source, duration and date. Use it "
        "when the user asks about ads on their channel or before starting an ad break. Read-only: it does not start ad breaks or enroll the channel."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "opted_in": True, "ads_blocked": False, "auto_ads_active": False, "remaining_ad_breaks": 3, "limit_max": 4, "limit_period_seconds": 3600,
        "ad_breaks": [{"id": "3f2a0000-0000-0000-0000-000000000000", "status": "completed", "source": "manual", "duration_seconds": 30,
                       "created_at": "2026-10-07T18:30:00Z"}]}}],
)
async def ads_ad_break_status(ctx: Context, args: NoArgs) -> AdBreakStatusOut:
    data = (await _data(ctx, f"{API_URL}/ads/ad-break-status"))["data"] or {}
    limits = data.get("limits") or {}
    return AdBreakStatusOut(
        opted_in=bool(data.get("opted_in")), ads_blocked=bool(data.get("ads_blocked")), auto_ads_active=bool(data.get("auto_ads_active")),
        remaining_ad_breaks=data.get("remaining_ad_breaks"), limit_max=limits.get("max"), limit_period_seconds=limits.get("period_seconds"),
        ad_breaks=[AdBreak(id=_sid(b.get("id")), status=b.get("status"), source=b.get("source"), duration_seconds=b.get("break_duration_seconds"),
                           created_at=b.get("created_at")) for b in data.get("ad_breaks") or []])


# --- kick.public_key.get -------------------------------------------------------------------------

class PublicKeyOut(BaseModel):
    public_key: str = Field(description="PEM encoded public key Kick uses to sign webhook requests")


@function(
    id="kick.public_key.get", version=1, verb=Verb.read, upstream_api="public/v1", scopes=[],
    description=(
        "Returns the public key Kick uses to sign its webhook requests, in PEM format. Use it to verify that an incoming Kick event notification "
        "really comes from Kick, or when the user asks how webhook signatures are checked. The key is public and the same for every account, so it "
        "is safe to show. It takes no parameters. Read-only: it does not change anything on Kick."
    ),
    examples=[{"name": "default", "input": {}, "output": {"public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkq...\n-----END PUBLIC KEY-----"}}],
)
async def public_key_get(ctx: Context, args: NoArgs) -> PublicKeyOut:
    key = ((await _data(ctx, f"{API_URL}/public-key"))["data"] or {}).get("public_key")
    if not key:
        raise FunctionError(ErrorCode.upstream_changed, "Kick no devolvio public_key.")
    return PublicKeyOut(public_key=key)


# --- kick.event.subscription_list ----------------------------------------------------------------

class ListSubscriptionsIn(BaseModel):
    broadcaster_user_id: Optional[str] = Field(default=None, pattern=r"^\d+$", description="Only subscriptions of this broadcaster user id; leave empty for all")


class EventSubscription(BaseModel):
    id: str = Field(description="Subscription id")
    event: str = Field(description="Event name, for example chat.message.sent or channel.followed")
    version: Optional[int] = Field(default=None, description="Version of the event payload")
    method: Optional[str] = Field(default=None, description="Delivery method, currently webhook")
    broadcaster_user_id: Optional[str] = Field(default=None, description="Channel owner the subscription listens to")
    app_id: Optional[str] = Field(default=None, description="Id of the Kick app that owns the subscription")
    created_at: Optional[str] = Field(default=None, description="When the subscription was created")
    updated_at: Optional[str] = Field(default=None, description="When the subscription last changed")


class ListSubscriptionsOut(BaseModel):
    subscriptions: list[EventSubscription] = Field(description="Event subscriptions of this app")


@function(
    id="kick.event.subscription_list", version=1, verb=Verb.read, upstream_api="public/v1", scopes=[],
    description=(
        "Lists the Kick event subscriptions (webhooks) that this app has, optionally only for one broadcaster user id. Each subscription has its id, "
        "event name (for example chat.message.sent, channel.followed or livestream.status.updated), payload version, delivery method, channel, app "
        "and dates. Use it to check which channel events BunnyDrop is listening to, or to find a subscription id. Read-only: it does not subscribe "
        "or unsubscribe."
    ),
    examples=[{"name": "default", "input": {}, "output": {"subscriptions": [
        {"id": "01KAAFHJ2PNXS48NG8XXPGWK00", "event": "chat.message.sent", "version": 1, "method": "webhook", "broadcaster_user_id": "123456",
         "app_id": "01JAXK8N4QWRTY5PM7ZEBVJ000", "created_at": "2026-10-07T18:00:00Z", "updated_at": "2026-10-07T18:00:00Z"}]}}],
)
async def event_subscription_list(ctx: Context, args: ListSubscriptionsIn) -> ListSubscriptionsOut:
    body = await _data(ctx, f"{API_URL}/events/subscriptions", {"broadcaster_user_id": args.broadcaster_user_id})
    return ListSubscriptionsOut(subscriptions=[
        EventSubscription(id=str(s["id"]), event=s["event"], version=s.get("version"), method=s.get("method"),
                          broadcaster_user_id=_sid(s.get("broadcaster_user_id")), app_id=_sid(s.get("app_id")), created_at=s.get("created_at"),
                          updated_at=s.get("updated_at"))
        for s in body["data"] or []])
