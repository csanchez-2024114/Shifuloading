"""ClickUp: Chat (canales y mensajes), Docs, paginas y registro de auditoria. Todas usan la API v3 (Workspace en la ruta)."""
import time
from typing import Any, Literal, Optional

from pydantic import Field

from app.functions.apps.clickup._common import (
    V3, Cursor, Out, PathId, WorkspaceIn, get, items, obj, page_cursor, query, unwrap,
)
from app.functions.apps.clickup.app_spec import APP  # noqa: F401
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

ContentFormat = Literal["text/md", "text/plain"]


def _ws(workspace_id: str) -> str:
    return f"{V3}/workspaces/{workspace_id}"


# --- Canales ---------------------------------------------------------------------------------------

class ChannelsIn(WorkspaceIn, Cursor):
    is_follower: bool = Field(default=False, description="When true, returns only the channels the connected user follows (default false)")
    include_closed: bool = Field(default=False, description="When true, direct messages and group DMs that were closed are included too (default false)")


class ChannelsOut(Out):
    channels: list[dict] = Field(default_factory=list, description="Channels, each with id, name, description, topic, type, visibility, creator, dates and unread counts")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more channels")


@function(
    id="clickup.channels.list", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the Chat channels of a ClickUp Workspace that the connected user can see: channels, direct messages and channels attached to a Space, folder or "
        "list. Each channel has its id, name, description, topic, type, visibility, creator, creation date and unread counters. Use it when the user asks which "
        "chat channels exist or needs a channel id to read its messages. Requires workspace_id; optional is_follower, include_closed, limit (1 to 100, default 50) "
        "and cursor: pass the returned next_cursor to read the next page. Read-only. It does not return messages (use clickup.messages.list) and does not create channels."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {
        "channels": [{"id": "ch-1", "name": "general", "type": "CHANNEL", "visibility": "PUBLIC"}], "next_cursor": None}}],
)
async def channels_list(ctx: Context, args: ChannelsIn) -> ChannelsOut:
    params = query(cursor=args.cursor, limit=args.limit, is_follower=args.is_follower or None, include_closed=args.include_closed or None)
    body = await get(ctx, f"{_ws(args.workspace_id)}/chat/channels", params)
    return ChannelsOut(channels=items(body, "data"), next_cursor=page_cursor(body))


class ChannelIn(WorkspaceIn):
    channel_id: PathId = Field(description="Chat channel id, for example '4-abc123-8'. Get it from clickup.channels.list")


class ChannelOut(Out):
    channel: Optional[dict] = Field(default=None, description="The channel: id, name, description, topic, type, visibility, parent location, creator, dates, archived flag and unread counters")


@function(
    id="clickup.channels.get", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Returns the details of one ClickUp Chat channel: id, name, description, topic, type (channel, direct message or group DM), visibility, the Space, "
        "folder or list it is attached to, creator, creation and update dates, whether it is archived and the unread and mention counters for the connected user. "
        "Use it when the user asks about one channel. Requires workspace_id and channel_id (see clickup.channels.list). Read-only. It does not return the "
        "messages (clickup.messages.list), the people who follow it (clickup.channels.get_followers) or its members (clickup.channels.get_members)."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "channel_id": "ch-1"}, "output": {"channel": {
        "id": "ch-1", "name": "general", "type": "CHANNEL", "visibility": "PUBLIC"}}}],
)
async def channels_get(ctx: Context, args: ChannelIn) -> ChannelOut:
    return ChannelOut(channel=obj(unwrap(await get(ctx, f"{_ws(args.workspace_id)}/chat/channels/{args.channel_id}"))))


class ChannelPeopleIn(ChannelIn, Cursor):
    pass


class FollowersOut(Out):
    followers: list[dict] = Field(default_factory=list, description="People who follow the channel, each with id, name, username, email and initials")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more followers")


@function(
    id="clickup.channels.get_followers", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the people who follow one ClickUp Chat channel (and so get its notifications): id, name, username, email and initials of each. Use it when the "
        "user asks who follows a channel. Requires workspace_id and channel_id (see clickup.channels.list); optional limit (1 to 100, default 50) and cursor: "
        "pass the returned next_cursor to read the next page. Read-only. Followers are not always the same as members: for members use "
        "clickup.channels.get_members. It does not add or remove followers."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "channel_id": "ch-1"}, "output": {"followers": [
        {"id": "12", "name": "Ana", "username": "ana", "email": "ana@example.com"}], "next_cursor": None}}],
)
async def channels_get_followers(ctx: Context, args: ChannelPeopleIn) -> FollowersOut:
    body = await get(ctx, f"{_ws(args.workspace_id)}/chat/channels/{args.channel_id}/followers", query(cursor=args.cursor, limit=args.limit))
    return FollowersOut(followers=items(body, "data"), next_cursor=page_cursor(body))


class ChannelMembersOut(Out):
    members: list[dict] = Field(default_factory=list, description="Members of the channel, each with id, name, username, email and initials")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more members")


@function(
    id="clickup.channels.get_members", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the members of one ClickUp Chat channel, meaning the people who belong to it and can read and write there: id, name, username, email and initials "
        "of each. Use it when the user asks who is in a channel or in a direct message. Requires workspace_id and channel_id (see clickup.channels.list); "
        "optional limit (1 to 100, default 50) and cursor: pass the returned next_cursor to read the next page. Read-only. For the people who follow the channel "
        "use clickup.channels.get_followers. It does not invite or remove members."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "channel_id": "ch-1"}, "output": {"members": [
        {"id": "12", "name": "Ana", "username": "ana", "email": "ana@example.com"}], "next_cursor": None}}],
)
async def channels_get_members(ctx: Context, args: ChannelPeopleIn) -> ChannelMembersOut:
    body = await get(ctx, f"{_ws(args.workspace_id)}/chat/channels/{args.channel_id}/members", query(cursor=args.cursor, limit=args.limit))
    return ChannelMembersOut(members=items(body, "data"), next_cursor=page_cursor(body))


# --- Mensajes --------------------------------------------------------------------------------------

class MessagesIn(ChannelIn, Cursor):
    content_format: ContentFormat = Field(default="text/md", description="Format of the message text: 'text/md' for Markdown (default) or 'text/plain' for plain text")


class MessagesOut(Out):
    messages: list[dict] = Field(default_factory=list, description="Messages, each with id, content, user_id, date, type, resolved flag, replies_count and links")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more messages")


@function(
    id="clickup.messages.list", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the top-level messages of one ClickUp Chat channel: for each message its id, text, author user id, date (Unix milliseconds), type (message or "
        "post), resolved flag and the number of replies. Use it when the user asks what was said in a channel. Requires workspace_id and channel_id (see "
        "clickup.channels.list); optional content_format (text/md or text/plain), limit (1 to 100, default 50) and cursor: pass the returned next_cursor to read "
        "the next page. Read-only. Replies of a thread are read with clickup.messages.list_replies and reactions with clickup.messages.get_reactions. It does not send messages."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "channel_id": "ch-1"}, "output": {"messages": [
        {"id": "m1", "content": "Hello team", "user_id": "12", "date": 1767225600000, "type": "message", "replies_count": 2}], "next_cursor": None}}],
)
async def messages_list(ctx: Context, args: MessagesIn) -> MessagesOut:
    params = query(cursor=args.cursor, limit=args.limit, content_format=args.content_format)
    body = await get(ctx, f"{_ws(args.workspace_id)}/chat/channels/{args.channel_id}/messages", params)
    return MessagesOut(messages=items(body, "data"), next_cursor=page_cursor(body))


class MessageIn(WorkspaceIn):
    message_id: PathId = Field(description="Chat message id. Get it from clickup.messages.list")


class MessagePageIn(MessageIn, Cursor):
    pass


class ReactionsOut(Out):
    reactions: list[dict] = Field(default_factory=list, description="Reactions, each with the emoji name (reaction), user_id and date")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more reactions")


@function(
    id="clickup.messages.get_reactions", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the emoji reactions on one ClickUp Chat message: each reaction has the emoji name (lower case, like 'thumbsup'), the id of the user who reacted "
        "and the date. Use it when the user asks who reacted to a message or with what. Requires workspace_id and message_id (see clickup.messages.list); "
        "optional limit (1 to 100, default 50) and cursor: pass the returned next_cursor to read the next page. Read-only. It returns one row per user and emoji "
        "(not grouped by emoji), does not return the message text (use clickup.messages.list) and does not add or remove reactions."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "message_id": "m1"}, "output": {"reactions": [
        {"reaction": "thumbsup", "user_id": "12", "date": 1767225700000}], "next_cursor": None}}],
)
async def messages_get_reactions(ctx: Context, args: MessagePageIn) -> ReactionsOut:
    body = await get(ctx, f"{_ws(args.workspace_id)}/chat/messages/{args.message_id}/reactions", query(cursor=args.cursor, limit=args.limit))
    return ReactionsOut(reactions=items(body, "data"), next_cursor=page_cursor(body))


class RepliesIn(MessagePageIn):
    content_format: ContentFormat = Field(default="text/md", description="Format of the reply text: 'text/md' for Markdown (default) or 'text/plain' for plain text")


class MessageRepliesOut(Out):
    replies: list[dict] = Field(default_factory=list, description="Replies of the thread, each with id, content, user_id, date and the parent message id")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more replies")


@function(
    id="clickup.messages.list_replies", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the replies in the thread of one ClickUp Chat message: for each reply its id, text, author user id, date and the id of the parent message. Use it "
        "when a message shows replies_count above zero and the user wants to read the thread. Requires workspace_id and message_id (see clickup.messages.list); "
        "optional content_format (text/md or text/plain), limit (1 to 100, default 50) and cursor: pass the returned next_cursor to read the next page. "
        "Read-only. It does not return the parent message itself, does not read task comments (use clickup.comments.list_replies for those) and does not post replies."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "message_id": "m1"}, "output": {"replies": [
        {"id": "m2", "content": "Agreed", "user_id": "13", "date": 1767225800000, "parent_message": "m1"}], "next_cursor": None}}],
)
async def messages_list_replies(ctx: Context, args: RepliesIn) -> MessageRepliesOut:
    params = query(cursor=args.cursor, limit=args.limit, content_format=args.content_format)
    body = await get(ctx, f"{_ws(args.workspace_id)}/chat/messages/{args.message_id}/replies", params)
    return MessageRepliesOut(replies=items(body, "data"), next_cursor=page_cursor(body))


class TaggedUsersOut(Out):
    tagged_users: list[dict] = Field(default_factory=list, description="People mentioned in the message, each with id, name, username, email and initials")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more people")


@function(
    id="clickup.messages.get_tagged_users", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the people who are @mentioned in one ClickUp Chat message: id, name, username, email and initials of each. Use it when the user asks who was tagged "
        "or mentioned in a message. Requires workspace_id and message_id (see clickup.messages.list); optional limit (1 to 100, default 50) and cursor: pass the "
        "returned next_cursor to read the next page. Read-only. It does not return the message text (use clickup.messages.list), does not cover mentions in task "
        "comments and does not notify anyone."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "message_id": "m1"}, "output": {"tagged_users": [
        {"id": "12", "name": "Ana", "username": "ana", "email": "ana@example.com"}], "next_cursor": None}}],
)
async def messages_get_tagged_users(ctx: Context, args: MessagePageIn) -> TaggedUsersOut:
    body = await get(ctx, f"{_ws(args.workspace_id)}/chat/messages/{args.message_id}/tagged_users", query(cursor=args.cursor, limit=args.limit))
    return TaggedUsersOut(tagged_users=items(body, "data"), next_cursor=page_cursor(body))


# --- Docs y paginas --------------------------------------------------------------------------------

class DocIn(WorkspaceIn):
    doc_id: PathId = Field(description="ClickUp Doc id, for example '8cnn-1234'. It appears in the Doc URL and in Doc search results")


class DocPagesIn(DocIn):
    max_page_depth: int = Field(default=-1, ge=-1, le=20, description="How many levels of nested pages to include; -1 (default) means all levels, 0 only top-level pages")
    content_format: ContentFormat = Field(default="text/md", description="Format of the page content: 'text/md' for Markdown (default) or 'text/plain' for plain text")


class DocPagesOut(Out):
    pages: list[dict] = Field(default_factory=list, description="Pages of the Doc with id, name, sub_title, content, dates, creator and nested sub-pages in 'pages'")


@function(
    id="clickup.docs.get_pages", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Returns the pages of one ClickUp Doc together with their content: for each page its id, name, subtitle, text content, creation and update dates, creator "
        "and its nested sub-pages. Use it when the user wants to read a Doc or search inside it. Requires workspace_id and doc_id; optional max_page_depth (-1 for "
        "all levels, the default) and content_format (text/md or text/plain). Read-only. It can be large for long Docs: when only the outline is needed use "
        "clickup.docs.get_page_listing, and to read a single page use clickup.pages.get. It does not edit pages."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "doc_id": "8cnn-1234"}, "output": {"pages": [
        {"id": "8cnn-5678", "name": "Overview", "content": "# Overview", "pages": []}]}}],
)
async def docs_get_pages(ctx: Context, args: DocPagesIn) -> DocPagesOut:
    body = await get(ctx, f"{_ws(args.workspace_id)}/docs/{args.doc_id}/pages", query(max_page_depth=args.max_page_depth, content_format=args.content_format))
    return DocPagesOut(pages=[p for p in (body if isinstance(body, list) else items(body, "pages")) if isinstance(p, dict)])


class PageListingIn(DocIn):
    max_page_depth: int = Field(default=-1, ge=-1, le=20, description="How many levels of nested pages to include; -1 (default) means all levels, 0 only top-level pages")


class PageListingOut(Out):
    pages: list[dict] = Field(default_factory=list, description="Outline of the Doc: for each page its id, name, parent_page_id and the nested sub-pages in 'pages', without content")


@function(
    id="clickup.docs.get_page_listing", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Returns the outline of one ClickUp Doc as a tree: for each page its id, name, parent page id and its nested sub-pages, without the text content. Use it "
        "when the user asks what a Doc contains, how it is organized, or to find the page id of a section before reading it. Requires workspace_id and doc_id; "
        "optional max_page_depth (-1 for all levels, the default). Read-only and light compared with reading the content. To read the text of the pages use "
        "clickup.docs.get_pages for all of them or clickup.pages.get for one. It does not edit the Doc."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "doc_id": "8cnn-1234"}, "output": {"pages": [
        {"id": "8cnn-5678", "name": "Overview", "pages": [{"id": "8cnn-5680", "name": "Goals", "pages": []}]}]}}],
)
async def docs_get_page_listing(ctx: Context, args: PageListingIn) -> PageListingOut:
    body = await get(ctx, f"{_ws(args.workspace_id)}/docs/{args.doc_id}/page_listing", query(max_page_depth=args.max_page_depth))
    return PageListingOut(pages=[p for p in (body if isinstance(body, list) else items(body, "pages")) if isinstance(p, dict)])


class PageIn(DocIn):
    page_id: PathId = Field(description="Id of the page inside the Doc, for example '8cnn-5678'. Get it from clickup.docs.get_page_listing")
    content_format: ContentFormat = Field(default="text/md", description="Format of the page content: 'text/md' for Markdown (default) or 'text/plain' for plain text")


class PageOut(Out):
    page: Optional[dict] = Field(default=None, description="The page: id, doc_id, name, sub_title, content, dates, creator, authors and nested sub-pages")


@function(
    id="clickup.pages.get", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Returns one page of a ClickUp Doc with its text content: id, name, subtitle, content, creation and update dates, creator, authors, archived and protected "
        "flags, and any nested sub-pages. Use it when the user wants to read a specific page. Requires workspace_id, doc_id and page_id (find page ids with "
        "clickup.docs.get_page_listing); optional content_format (text/md or text/plain). Read-only. The page id alone is not enough, ClickUp also needs the Doc id. "
        "To read every page of a Doc at once use clickup.docs.get_pages. It does not edit or create pages."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "doc_id": "8cnn-1234", "page_id": "8cnn-5678"}, "output": {"page": {
        "id": "8cnn-5678", "name": "Overview", "content": "# Overview"}}}],
)
async def pages_get(ctx: Context, args: PageIn) -> PageOut:
    body = await get(ctx, f"{_ws(args.workspace_id)}/docs/{args.doc_id}/pages/{args.page_id}", query(content_format=args.content_format))
    return PageOut(page=obj(body))


# --- Registro de auditoria -------------------------------------------------------------------------

class AuditIn(WorkspaceIn):
    applicability: Literal["auth-and-security", "user-activity", "hierarchy-activity", "custom-fields", "agent-settings-activity", "other-activity"] = Field(
        default="auth-and-security", description="Kind of audit events to read: auth-and-security (default, logins and security changes), user-activity, hierarchy-activity, custom-fields, agent-settings-activity or other-activity")
    user_ids: list[str] = Field(default_factory=list, description="Only events caused by these user ids; empty means all users")
    user_emails: list[str] = Field(default_factory=list, description="Only events caused by users with these email addresses; empty means all users")
    event_type: Optional[str] = Field(default=None, description="Only this event type, for example USER_LOGIN, USER_LOGOUT, CHANGE_PASSWORD or ROLE_CHANGE; empty means all types")
    event_status: Optional[Literal["success", "failed", "warn", "skipped", "started", "completed", "error", "system_error"]] = Field(
        default=None, description="Only events with this status, for example success or failed; empty means any status")
    start_time: Optional[int] = Field(default=None, description="Only events after this Unix time in milliseconds")
    end_time: Optional[int] = Field(default=None, description="Only events before this Unix time in milliseconds")
    page_rows: int = Field(default=50, ge=1, le=100, description="Number of events to return, from 1 to 100 (default 50)")
    page_timestamp: Optional[int] = Field(default=None, description="Unix time in milliseconds to page from: the timestamp of the last event of the previous page; empty means now (first page)")
    page_direction: Literal["before", "after"] = Field(default="before", description="Paging direction relative to page_timestamp: 'before' (default) walks back in time, 'after' forwards")


class AuditOut(Out):
    logs: Optional[Any] = Field(default=None, description="Audit events exactly as ClickUp returns them, including the data needed to request the next page")


@function(
    id="clickup.audit_logs.create", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Queries the audit log of a ClickUp Workspace and returns the events that match: logins, logouts, password and 2FA changes, role changes, membership "
        "changes, hierarchy and custom-field activity, with the user, the status, the time and the details. Despite the ClickUp endpoint name ('create audit "
        "logs'), it only reads: it records nothing and changes nothing. Use it for security reviews such as 'who failed to log in this week?'. Requires "
        "workspace_id; filter by applicability, user, event type, status and time, and page with page_rows and page_timestamp. Only the Workspace owner can use it, "
        "and only on the Enterprise plan."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"logs": [
        {"eventType": "USER_LOGIN", "eventStatus": "success", "userEmail": "ana@example.com", "timestamp": 1767225600000}]}}],
)
async def audit_logs_create(ctx: Context, args: AuditIn) -> AuditOut:
    # POST /api/v3/workspaces/{workspace_id}/auditlogs es una CONSULTA (el nombre de ClickUp es engañoso): por eso verb=read.
    event_filter = {k: v for k, v in {
        "userId": args.user_ids, "userEmail": args.user_emails, "eventType": args.event_type, "eventStatus": args.event_status,
        "startTime": args.start_time, "endTime": args.end_time}.items() if v not in (None, [])}
    payload = {
        "filter": event_filter, "applicability": args.applicability,
        "pagination": {"pageRows": args.page_rows, "pageTimestamp": args.page_timestamp or int(time.time() * 1000), "pageDirection": args.page_direction},
    }
    resp = await ctx.conn.request("POST", f"{_ws(args.workspace_id)}/auditlogs", json=payload)
    try:
        return AuditOut(logs=resp.json())
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "ClickUp respondio algo que no es JSON.") from None
