"""Lecturas de Discord con el token OAuth del USUARIO (servidores, miembro, conexiones y autorizacion). Las importa functions.py al final.

Verificado en discord.com/developers/docs (2026-10-09): resources/user y topics/oauth2.
- `/users/@me/guilds` pide `guilds`; `/users/@me/guilds/{id}/member` pide `guilds.members.read`; `/users/@me/connections` pide
  `connections`; `/oauth2/@me` funciona con cualquier token bearer.
- El resto del catalogo (canales, mensajes, miembros, roles, webhooks, invitaciones, auditoria, comandos, stickers, voz...) pide el token del
  BOT, que el sistema de cuentas no maneja (POR DECIDIR con Alan). No se implementa: con el token de usuario Discord responde 401 y la cuenta
  quedaria marcada como expirada.
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.discord.functions import API_URL, NoArgs
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

SNOWFLAKE = r"^\d{15,25}$"


# --- discord.guild.list_user_guilds --------------------------------------------------------------

class ListGuildsIn(BaseModel):
    limit: int = Field(default=200, ge=1, le=200, description="How many servers to return, from 1 to 200 (default 200, the most a user can join)")
    after: Optional[str] = Field(default=None, pattern=SNOWFLAKE, description="Only servers with an id greater than this server id")
    before: Optional[str] = Field(default=None, pattern=SNOWFLAKE, description="Only servers with an id lower than this server id")
    with_counts: bool = Field(default=False, description="True to include the approximate member and online counts of each server")


class Guild(BaseModel):
    id: str = Field(description="Server (guild) id")
    name: str = Field(description="Name of the server")
    icon: Optional[str] = Field(default=None, description="Icon hash of the server, used to build the icon image link")
    owner: bool = Field(default=False, description="True if the connected user owns the server")
    permissions: Optional[str] = Field(default=None, description="Permission bit set of the connected user in the server, as a number in text")
    features: list[str] = Field(default_factory=list, description="Enabled server features, for example COMMUNITY or NEWS")
    approximate_member_count: Optional[int] = Field(default=None, description="Approximate number of members, only with with_counts")
    approximate_presence_count: Optional[int] = Field(default=None, description="Approximate number of online members, only with with_counts")


class ListGuildsOut(BaseModel):
    guilds: list[Guild] = Field(description="Servers the connected user belongs to")


@function(
    id="discord.guild.list_user_guilds", version=1, verb=Verb.read, upstream_api="v10", scopes=["guilds"],
    description=(
        "Lists the Discord servers (guilds) the connected user belongs to: id, name, icon, whether the user owns it, the user's permission bit set "
        "and the server features, optionally with approximate member and online counts. Use it when the user asks which Discord servers they are in "
        "or own, or needs a server id for another step. Up to 200 per call, which covers every server a normal user can join. Read-only: it does "
        "not join or leave servers."
    ),
    examples=[{"name": "default", "input": {"with_counts": True}, "output": {"guilds": [
        {"id": "80351110224678912", "name": "Comunidad Demo", "icon": None, "owner": True, "permissions": "2251799813685247",
         "features": ["COMMUNITY"], "approximate_member_count": 120, "approximate_presence_count": 15}]}}],
)
async def guild_list_user_guilds(ctx: Context, args: ListGuildsIn) -> ListGuildsOut:
    params = {"limit": args.limit, "after": args.after, "before": args.before, "with_counts": "true" if args.with_counts else None}
    rows = (await ctx.conn.request("GET", f"{API_URL}/users/@me/guilds", params={k: v for k, v in params.items() if v is not None})).json()
    return ListGuildsOut(guilds=[
        Guild(id=str(g["id"]), name=g["name"], icon=g.get("icon"), owner=bool(g.get("owner")), permissions=g.get("permissions"),
              features=g.get("features") or [], approximate_member_count=g.get("approximate_member_count"),
              approximate_presence_count=g.get("approximate_presence_count"))
        for g in rows or []])


# --- discord.guild.get_user_guild_member ---------------------------------------------------------

class GuildMemberIn(BaseModel):
    guild_id: str = Field(pattern=SNOWFLAKE, description="Id of the server, as returned by discord.guild.list_user_guilds")


class GuildMemberOut(BaseModel):
    guild_id: str = Field(description="Id of the server that was read")
    nick: Optional[str] = Field(default=None, description="Nickname of the user in that server, if set")
    role_ids: list[str] = Field(default_factory=list, description="Ids of the roles the user has in that server")
    joined_at: Optional[str] = Field(default=None, description="When the user joined the server")
    premium_since: Optional[str] = Field(default=None, description="Since when the user boosts the server, if they do")
    pending: bool = Field(default=False, description="True if the user has not passed the membership screening yet")
    deaf: bool = Field(default=False, description="True if the user is deafened in voice channels of the server")
    mute: bool = Field(default=False, description="True if the user is muted in voice channels of the server")
    timed_out_until: Optional[str] = Field(default=None, description="Until when the user is timed out, if they are")


@function(
    id="discord.guild.get_user_guild_member", version=1, verb=Verb.read, upstream_api="v10", scopes=["guilds.members.read"],
    description=(
        "Returns the membership of the connected user in one Discord server: nickname, role ids, when they joined, since when they boost it, whether "
        "they are still pending screening, muted, deafened or timed out. Use it when the user asks what roles or nickname they have in a server or "
        "since when they are a member. Get the server id first with discord.guild.list_user_guilds. Read-only: it does not change roles or nickname."
    ),
    examples=[{"name": "default", "input": {"guild_id": "80351110224678912"}, "output": {
        "guild_id": "80351110224678912", "nick": "Ana", "role_ids": ["41771983423143936"], "joined_at": "2025-05-01T10:00:00.000000+00:00",
        "premium_since": None, "pending": False, "deaf": False, "mute": False, "timed_out_until": None}}],
)
async def guild_get_user_guild_member(ctx: Context, args: GuildMemberIn) -> GuildMemberOut:
    m = (await ctx.conn.request("GET", f"{API_URL}/users/@me/guilds/{args.guild_id}/member")).json()
    return GuildMemberOut(guild_id=args.guild_id, nick=m.get("nick"), role_ids=[str(r) for r in m.get("roles") or []], joined_at=m.get("joined_at"),
                          premium_since=m.get("premium_since"), pending=bool(m.get("pending")), deaf=bool(m.get("deaf")), mute=bool(m.get("mute")),
                          timed_out_until=m.get("communication_disabled_until"))


# --- discord.user.get_connections ----------------------------------------------------------------

class Connection(BaseModel):
    type: str = Field(description="Linked service, for example twitch, youtube, steam, github or spotify")
    id: str = Field(description="Account id on that service")
    name: str = Field(description="Username on that service")
    verified: bool = Field(default=False, description="True if Discord verified the linked account")
    revoked: bool = Field(default=False, description="True if the link was revoked")
    visible: bool = Field(default=False, description="True if the link is shown on the public Discord profile")
    show_activity: bool = Field(default=False, description="True if activity from that service is shown in Discord")


class ConnectionsOut(BaseModel):
    connections: list[Connection] = Field(description="Third party accounts linked to the Discord account")


@function(
    id="discord.user.get_connections", version=1, verb=Verb.read, upstream_api="v10", scopes=["connections"],
    description=(
        "Lists the third party accounts linked to the connected Discord account, such as Twitch, YouTube, Steam, GitHub, Spotify or X: service, account "
        "id, username, whether it is verified, revoked or visible on the profile and whether its activity is shown. Use it when the user asks which "
        "accounts they linked to Discord, or to find their Twitch or YouTube handle. Read-only: it does not add or remove links."
    ),
    examples=[{"name": "default", "input": {}, "output": {"connections": [
        {"type": "twitch", "id": "123456789", "name": "empresademo", "verified": True, "revoked": False, "visible": True, "show_activity": True}]}}],
)
async def user_get_connections(ctx: Context, args: NoArgs) -> ConnectionsOut:
    rows = (await ctx.conn.request("GET", f"{API_URL}/users/@me/connections")).json()
    return ConnectionsOut(connections=[
        Connection(type=c["type"], id=str(c["id"]), name=c["name"], verified=bool(c.get("verified")), revoked=bool(c.get("revoked")),
                   visible=c.get("visibility") == 1, show_activity=bool(c.get("show_activity")))
        for c in rows or []])


# --- discord.authorization.get -------------------------------------------------------------------

class AuthorizationOut(BaseModel):
    application_id: str = Field(description="Id of the Discord app the user authorized (BunnyDrop)")
    application_name: Optional[str] = Field(default=None, description="Name of that Discord app")
    scopes: list[str] = Field(description="Permissions (OAuth scopes) the user granted to the app")
    expires: Optional[str] = Field(default=None, description="When the current access token expires; it is renewed automatically")
    user_id: Optional[str] = Field(default=None, description="Discord user id who authorized the app")


@function(
    id="discord.authorization.get", version=1, verb=Verb.read, upstream_api="v10", scopes=[],
    description=(
        "Returns what the connected Discord account authorized: the Discord app id and name, the permissions (OAuth scopes) the user granted, when "
        "the current access token expires and the user id. Use it to check which Discord permissions are available before reading servers or "
        "linked accounts, or to explain why a Discord read fails with a missing permission. Read-only: it takes no parameters and changes nothing."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "application_id": "1558119283014373406", "application_name": "BunnyDrop", "scopes": ["identify", "guilds"],
        "expires": "2026-10-16T14:00:00.000000+00:00", "user_id": "80351110224678912"}}],
)
async def authorization_get(ctx: Context, args: NoArgs) -> AuthorizationOut:
    body = (await ctx.conn.request("GET", f"{API_URL}/oauth2/@me")).json()
    app = body.get("application") or {}
    return AuthorizationOut(application_id=str(app["id"]), application_name=app.get("name"), scopes=body.get("scopes") or [],
                            expires=body.get("expires"), user_id=str((body.get("user") or {}).get("id")) if (body.get("user") or {}).get("id") else None)
