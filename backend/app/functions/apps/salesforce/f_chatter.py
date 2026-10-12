"""Lecturas de Chatter en Salesforce: noticias del usuario (feeds), grupos y detalle de un grupo.

Verificado con la API real (2026-10-09), v62.0:
- GET /chatter/feeds/news NO existe (404). El feed de noticias del usuario conectado es GET /chatter/feeds/news/me/feed-elements
  (`pageSize`, `page` con el token de la pagina) y responde {elements[], nextPageToken, nextPageUrl, currentPageUrl, updatesToken}.
- GET /chatter/groups -> {groups[], nextPageUrl, previousPageUrl, currentPageUrl}; acepta `pageSize`, `page` (numero desde 0) y `q`.
- GET /chatter/groups/{id} -> el grupo (id, name, description, visibility, memberCount, owner, isArchived).
POR COMPROBAR con datos reales: la org de desarrollo no tiene publicaciones ni grupos de Chatter (las listas vuelven vacias), asi que el
mapeo de cada elemento sigue la documentacion y las pruebas simuladas, no una respuesta real con datos. Todas piden el permiso `api`.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito.
"""
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.functions.apps.salesforce._common import ID_PATTERN, UPSTREAM_API, get_json
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb


def _page_total(raw: dict[str, Any], capability: str) -> Optional[int]:
    total = (((raw.get("capabilities") or {}).get(capability) or {}).get("page") or {}).get("total")
    return int(total) if isinstance(total, (int, float)) else None


# --- salesforce.chatter.feeds --------------------------------------------------------------------

class FeedElement(BaseModel):
    id: str = Field(description="Salesforce id of the feed element (post), for example '0D5fj00000AbCdEAAZ'")
    type: Optional[str] = Field(default=None, description="Kind of feed element, for example 'TextPost', 'LinkPost', 'ContentPost' or 'TrackedChange'")
    text: Optional[str] = Field(default=None, description="Text of the post, or the generated header text for automatic updates such as field changes")
    actor_id: Optional[str] = Field(default=None, description="Salesforce id of the user who wrote the post")
    actor_name: Optional[str] = Field(default=None, description="Name of the user who wrote the post")
    created_date: Optional[str] = Field(default=None, description="Date and time when the post was created, in ISO 8601 format")
    parent_id: Optional[str] = Field(default=None, description="Salesforce id of the record, group or user whose feed the post belongs to")
    parent_name: Optional[str] = Field(default=None, description="Name of the record, group or user whose feed the post belongs to")
    comment_count: Optional[int] = Field(default=None, description="Number of comments on the post")
    like_count: Optional[int] = Field(default=None, description="Number of likes on the post")


def _feed_element(raw: dict[str, Any]) -> FeedElement:
    actor, parent = raw.get("actor") or {}, raw.get("parent") or {}
    text = (raw.get("body") or {}).get("text") or (raw.get("header") or {}).get("text")
    return FeedElement(id=raw["id"], type=raw.get("type") or raw.get("feedElementType"), text=text, actor_id=actor.get("id"),
                       actor_name=actor.get("displayName") or actor.get("name"), created_date=raw.get("createdDate"), parent_id=parent.get("id"),
                       parent_name=parent.get("displayName") or parent.get("name"), comment_count=_page_total(raw, "comments"),
                       like_count=_page_total(raw, "chatterLikes"))


class FeedsIn(BaseModel):
    page_size: int = Field(default=25, ge=1, le=100, description="How many posts to return in this page, from 1 to 100 (default 25)")
    page_token: Optional[str] = Field(default=None, max_length=200, description="Token returned as next_page_token by a previous call, to continue with the next page of posts")


class FeedsOut(BaseModel):
    elements: list[FeedElement] = Field(description="The posts of the news feed in this page, most recent first")
    has_more: bool = Field(description="True when there are more posts than were returned and a next page can be requested")
    next_page_token: Optional[str] = Field(default=None, description="Token to pass as page_token to get the next page of posts; empty when there is no next page")


@function(
    id="salesforce.chatter.feeds", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the Chatter news feed of the connected Salesforce user: the most recent posts and automatic updates from the people, groups and records the "
        "user follows, each with its id, kind, text, author, date, the place it was posted in, and the number of comments and likes. Use it when the user "
        "asks what is new in Salesforce, what colleagues posted, or wants a summary of recent Chatter activity. It returns up to 100 posts per page and "
        "continues with next_page_token. The list is empty when Chatter is off or the user follows nothing. Read-only: it does not post, comment or like. "
        "For the groups use salesforce.chatter.groups."
    ),
    examples=[{"name": "default", "input": {"page_size": 1}, "output": {"elements": [
        {"id": "0D5fj00000AbCdEAAZ", "type": "TextPost", "text": "Quarter closed above target!", "actor_id": "005fj000009fDddAAE", "actor_name": "Ana Perez",
         "created_date": "2026-10-08T14:30:00.000Z", "parent_id": "005fj000009fDddAAE", "parent_name": "Ana Perez", "comment_count": 2, "like_count": 5}],
        "has_more": False}}],
)
async def chatter_feeds(ctx: Context, args: FeedsIn) -> FeedsOut:
    params: dict[str, Any] = {"pageSize": args.page_size}
    if args.page_token:
        params["page"] = args.page_token
    body = await get_json(ctx, "/chatter/feeds/news/me/feed-elements", params=params)
    token = body.get("nextPageToken") if body.get("nextPageUrl") else None
    return FeedsOut(elements=[_feed_element(e) for e in body.get("elements", []) if e.get("id")], has_more=token is not None,
                    next_page_token=str(token) if token is not None else None)


# --- salesforce.chatter.groups -------------------------------------------------------------------

class Group(BaseModel):
    id: str = Field(description="Salesforce id of the Chatter group, usually starting with 0F9")
    name: Optional[str] = Field(default=None, description="Name of the Chatter group")
    description: Optional[str] = Field(default=None, description="Description of the Chatter group")
    visibility: Optional[str] = Field(default=None, description="Who can see the group: 'PublicAccess' or 'PrivateAccess'")
    member_count: Optional[int] = Field(default=None, description="Number of members of the group")
    owner_id: Optional[str] = Field(default=None, description="Salesforce user id of the owner of the group")
    owner_name: Optional[str] = Field(default=None, description="Name of the owner of the group")
    is_archived: Optional[bool] = Field(default=None, description="True when the group is archived and no longer active")


def _group(raw: dict[str, Any]) -> Group:
    owner = raw.get("owner") or {}
    return Group(id=raw["id"], name=raw.get("name"), description=raw.get("description"), visibility=raw.get("visibility"), member_count=raw.get("memberCount"),
                 owner_id=owner.get("id"), owner_name=owner.get("displayName") or owner.get("name"), is_archived=raw.get("isArchived"))


class GroupsIn(BaseModel):
    search_term: Optional[str] = Field(default=None, min_length=2, max_length=100, description="Optional text to look for in the group names, at least 2 characters; leave empty to list all groups")
    page_size: int = Field(default=25, ge=1, le=250, description="How many groups to return in this page, from 1 to 250 (default 25)")
    page: int = Field(default=0, ge=0, description="Page number to return, starting at 0; use the next_page value of a previous result to continue")


class GroupsOut(BaseModel):
    groups: list[Group] = Field(description="The Chatter groups returned in this page")
    has_more: bool = Field(description="True when there are more groups than were returned and a next page can be requested")
    next_page: Optional[int] = Field(default=None, description="Page number to pass as input to get the next page of groups; empty when there is no next page")


@function(
    id="salesforce.chatter.groups", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the Chatter groups of the connected Salesforce org that the user can see, each with its id, name, description, visibility (public or "
        "private), number of members, owner and whether it is archived. Use it when the user asks which Chatter groups or communities of colleagues exist, "
        "or needs a group id for the detail. It can filter by text in the name (at least 2 characters) and returns up to 250 groups per page, continuing "
        "with next_page. Read-only: it does not create groups or change membership. The list is empty when Chatter is off or no group exists. For one "
        "group use salesforce.chatter.group_get."
    ),
    examples=[{"name": "default", "input": {"search_term": "sales"}, "output": {"groups": [
        {"id": "0F9fj00000AbCdECAV", "name": "Sales Team", "description": "Daily sales updates", "visibility": "PublicAccess", "member_count": 12,
         "owner_id": "005fj000009fDddAAE", "owner_name": "Ana Perez", "is_archived": False}], "has_more": False}}],
)
async def chatter_groups(ctx: Context, args: GroupsIn) -> GroupsOut:
    params: dict[str, Any] = {"pageSize": args.page_size, "page": args.page}
    if args.search_term:
        params["q"] = args.search_term
    body = await get_json(ctx, "/chatter/groups", params=params)
    nxt = None
    if body.get("nextPageUrl"):  # el token de la pagina siguiente es su numero; si no llega, es la actual + 1
        token = body.get("nextPageToken")
        nxt = int(token) if isinstance(token, int) or (isinstance(token, str) and token.isdigit()) else args.page + 1
    return GroupsOut(groups=[_group(g) for g in body.get("groups", []) if g.get("id")], has_more=nxt is not None, next_page=nxt)


# --- salesforce.chatter.group_get ----------------------------------------------------------------

class GroupGetIn(BaseModel):
    group_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the Chatter group, 15 or 18 letters and digits, usually starting with 0F9")


@function(
    id="salesforce.chatter.group_get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the detail of one Chatter group given its id: name, description, visibility (public or private), number of members, owner and whether it is "
        "archived. Use it when the user asks about a specific Chatter group, for example how many people are in it or who owns it. Read-only: it does not "
        "change the group or its members. It fails with not_found when the id does not exist or the group is private and the connected user cannot see it. "
        "To find the id of a group use salesforce.chatter.groups."
    ),
    examples=[{"name": "default", "input": {"group_id": "0F9fj00000AbCdECAV"}, "output": {
        "id": "0F9fj00000AbCdECAV", "name": "Sales Team", "description": "Daily sales updates", "visibility": "PublicAccess", "member_count": 12,
        "owner_id": "005fj000009fDddAAE", "owner_name": "Ana Perez", "is_archived": False}}],
)
async def chatter_group_get(ctx: Context, args: GroupGetIn) -> Group:
    return _group(await get_json(ctx, f"/chatter/groups/{args.group_id}"))
