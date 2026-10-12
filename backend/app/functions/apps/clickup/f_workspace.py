"""ClickUp: grupos, roles, invitados, jerarquia compartida, webhooks y tipos de post (lecturas a nivel Workspace)."""
from typing import Any, Optional

from pydantic import Field

from app.functions.apps.clickup._common import V2, V3, Out, PathId, WorkspaceIn, get, items, obj, query
from app.functions.apps.clickup.app_spec import APP  # noqa: F401
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb


# --- clickup.workspace.get_groups ------------------------------------------------------------------

class GroupsOut(Out):
    groups: list[dict] = Field(default_factory=list, description="User groups of the Workspace, each with id, name, handle and its members")


@function(
    id="clickup.workspace.get_groups", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the user groups (teams of people) of a ClickUp Workspace. Each group has its id, name, handle, creation date, avatar and the list of members with id, "
        "username and email. Use it when the user asks 'which groups exist?' or 'who is in the design group?', or to find the group id to mention or assign work to a "
        "group. Requires workspace_id (see clickup.workspaces.list). Read-only. In the ClickUp API a 'team' is a Workspace and these are 'user groups': this does not "
        "return Workspace roles (use clickup.workspace.get_roles) or the members of one list (use clickup.lists.get_members)."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"groups": [
        {"id": "g-1", "name": "Design", "handle": "design", "members": [{"id": 12, "username": "ana", "email": "ana@example.com"}]}]}}],
)
async def workspace_get_groups(ctx: Context, args: WorkspaceIn) -> GroupsOut:
    # GET /group?team_id=  (la ruta del catalogo /team/{id}/group no existe)
    return GroupsOut(groups=items(await get(ctx, f"{V2}/group", query(team_id=args.workspace_id)), "groups"))


# --- clickup.workspace.get_roles -------------------------------------------------------------------

class RolesOut(Out):
    custom_roles: list[dict] = Field(default_factory=list, description="Custom roles of the Workspace, each with id, name, inherited_role and member ids")


class RolesIn(WorkspaceIn):
    include_members: bool = Field(default=False, description="When true, each role also lists the ids of the members that hold it (default false)")


@function(
    id="clickup.workspace.get_roles", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the custom roles of a ClickUp Workspace. Each role has its id, name, the built-in role it inherits from (inherited_role), its creation date and, when "
        "include_members is true, the ids of the members that hold it. Use it when the user asks 'which custom roles exist?' or 'what role does this person have?'. "
        "Requires workspace_id (see clickup.workspaces.list). Read-only. Custom roles are an Enterprise-plan feature, so other plans may get an error or an empty "
        "list. It does not describe permissions in detail and does not list user groups (use clickup.workspace.get_groups)."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "include_members": True}, "output": {"custom_roles": [
        {"id": 77, "name": "Contractor", "inherited_role": 3, "members": [12]}]}}],
)
async def workspace_get_roles(ctx: Context, args: RolesIn) -> RolesOut:
    body = await get(ctx, f"{V2}/team/{args.workspace_id}/customroles", query(include_members=args.include_members or None))
    return RolesOut(custom_roles=items(body, "custom_roles"))


# --- clickup.guests.get ----------------------------------------------------------------------------

class GuestIn(WorkspaceIn):
    guest_id: PathId = Field(description="Numeric id of the guest user. Guest ids appear in task, list and folder sharing information")


class GuestOut(Out):
    guest: Optional[dict] = Field(default=None, description="The guest: user details (id, username, email, role, last_active, date_joined) and what is shared with them")


@function(
    id="clickup.guests.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the details of one guest of a ClickUp Workspace: the user data (id, username, email, role, last active and join dates) and the tasks, lists and "
        "folders that are shared with that guest, with the permission level of each. Use it when the user asks what a guest can see or when they were invited. Requires "
        "workspace_id and guest_id. Read-only. Guests are an Enterprise-plan feature in this endpoint, so other plans may get an error. It does not invite, edit or "
        "remove guests and it does not list all guests: members are listed by clickup.lists.get_members and clickup.task_members.list."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "guest_id": "555"}, "output": {"guest": {
        "user": {"id": 555, "email": "guest@example.com", "role": 4}, "shared": {"tasks": [], "lists": [], "folders": []}}}}],
)
async def guests_get(ctx: Context, args: GuestIn) -> GuestOut:
    # GET /team/{team_id}/guest/{guest_id}  (la ruta del catalogo /guest/{id} no existe)
    body = obj(await get(ctx, f"{V2}/team/{args.workspace_id}/guest/{args.guest_id}"))
    return GuestOut(guest=obj(body.get("guest")) or body)


# --- clickup.workspace.get_shared_hierarchy --------------------------------------------------------

class SharedOut(Out):
    tasks: list[Any] = Field(default_factory=list, description="Tasks shared with the connected user that live outside the hierarchy they can browse")
    lists: list[dict] = Field(default_factory=list, description="Lists shared with the connected user, each with id, name and task count")
    folders: list[dict] = Field(default_factory=list, description="Folders shared with the connected user, each with id, name and its lists")


@function(
    id="clickup.workspace.get_shared_hierarchy", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the tasks, lists and folders of a ClickUp Workspace that were shared directly with the connected user, even when the user cannot browse the Spaces "
        "that contain them (typical for guests). Use it when the user asks 'what has been shared with me?' or cannot find an item through the normal hierarchy. "
        "Requires workspace_id (see clickup.workspaces.list). Read-only. It lists only shared items, not the whole hierarchy: use clickup.spaces.list, "
        "clickup.folders.list and clickup.lists.list to browse everything the user has access to."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {
        "tasks": ["86abc12"], "lists": [{"id": "901", "name": "Shared list"}], "folders": []}}],
)
async def workspace_get_shared_hierarchy(ctx: Context, args: WorkspaceIn) -> SharedOut:
    # GET /team/{team_id}/shared  (la ruta del catalogo /shared_hierarchy no existe)
    shared = obj(obj(await get(ctx, f"{V2}/team/{args.workspace_id}/shared")).get("shared"))
    return SharedOut(tasks=items(shared, "tasks"), lists=items(shared, "lists"), folders=items(shared, "folders"))


# --- clickup.webhooks.list -------------------------------------------------------------------------

class WebhooksOut(Out):
    webhooks: list[dict] = Field(default_factory=list, description="Webhooks of the Workspace created by the connected user or app: id, endpoint, events, scope ids and health")


@function(
    id="clickup.webhooks.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the webhooks registered in a ClickUp Workspace by the connected user (Workspace owners and admins also see those created by other users of the same "
        "app). Each webhook has its id, endpoint URL, subscribed events, the space, folder, list or task it is limited to, and a health status with the failure count. "
        "Use it when the user asks 'which webhooks do I have?' or why events stopped arriving. Requires workspace_id (see clickup.workspaces.list). Read-only: the "
        "signing secret of each webhook is removed from the result, and nothing is created, changed or deleted."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"webhooks": [
        {"id": "wh-1", "endpoint": "https://example.com/hook", "events": ["taskCreated"], "health": {"status": "active", "fail_count": 0}}]}}],
)
async def webhooks_list(ctx: Context, args: WorkspaceIn) -> WebhooksOut:
    hooks = [{k: v for k, v in obj(h).items() if k != "secret"} for h in items(await get(ctx, f"{V2}/team/{args.workspace_id}/webhook"), "webhooks")]
    return WebhooksOut(webhooks=hooks)


# --- clickup.workspace.get_post_types --------------------------------------------------------------

class PostTypesOut(Out):
    subtypes: Optional[Any] = Field(default=None, description="Post subtype ids of the Workspace (Announcement, Discussion, Idea and Update) exactly as ClickUp returns them")


@function(
    id="clickup.workspace.get_post_types", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Returns the ids of the post subtypes (Announcement, Discussion, Idea and Update) of a ClickUp Workspace. Chat posts are sent with a subtype id and these ids "
        "are different in every Workspace, so this is how to learn them. Use it when the user asks which kinds of post exist in Chat, or before preparing a post. "
        "Requires workspace_id (see clickup.workspaces.list). Read-only: it does not read or send messages. To read the messages of a channel use "
        "clickup.messages.list. This function uses the ClickUp v3 API and reads the subtypes of the 'post' comment type."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"subtypes": {"Announcement": "sub-1", "Discussion": "sub-2"}}}],
)
async def workspace_get_post_types(ctx: Context, args: WorkspaceIn) -> PostTypesOut:
    return PostTypesOut(subtypes=await get(ctx, f"{V3}/workspaces/{args.workspace_id}/comments/types/post/subtypes"))


# --- Plantillas (tarea 6) --------------------------------------------------------------------------

class TaskTemplatesIn(WorkspaceIn):
    page: int = Field(default=0, ge=0, description="Page number to read, starting at 0 (default 0)")


class TaskTemplatesOut(Out):
    templates: list[Any] = Field(default_factory=list, description="Task templates of the Workspace, each with its id and name")


@function(
    id="clickup.task_templates.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the task templates available in a ClickUp Workspace: the id and name of each template. Use it when the user asks which task templates exist, or "
        "to find the template id needed to create a task from a template. Requires workspace_id (see clickup.workspaces.list) and optionally page, starting at 0. "
        "Read-only: it does not create tasks, does not return the contents of a template (checklists, subtasks, description) and does not edit templates. "
        "For list and folder templates use clickup.list_templates.list and clickup.folder_templates.list."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"templates": [{"id": "t-1234", "name": "Bug report"}]}}],
)
async def task_templates_list(ctx: Context, args: TaskTemplatesIn) -> TaskTemplatesOut:
    # GET /team/{team_id}/taskTemplate  (la ruta del catalogo /task_template no existe)
    return TaskTemplatesOut(templates=items(await get(ctx, f"{V2}/team/{args.workspace_id}/taskTemplate", query(page=args.page)), "templates"))


class TemplatesOut(Out):
    templates: list[dict] = Field(default_factory=list, description="Templates of the Workspace, each with its id and name")


@function(
    id="clickup.list_templates.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the List templates available in a ClickUp Workspace: the id and name of each template. Use it when the user asks which List templates exist, or "
        "to find the template id needed to create a List from a template. Requires workspace_id (see clickup.workspaces.list). Read-only and not paginated: it "
        "does not create lists, does not show what a template contains and does not edit templates. For task and folder templates use "
        "clickup.task_templates.list and clickup.folder_templates.list."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"templates": [{"id": "lt-1", "name": "Sprint list"}]}}],
)
async def list_templates_list(ctx: Context, args: WorkspaceIn) -> TemplatesOut:
    return TemplatesOut(templates=items(await get(ctx, f"{V2}/team/{args.workspace_id}/list_template"), "templates"))


@function(
    id="clickup.folder_templates.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the Folder templates available in a ClickUp Workspace: the id and name of each template. Use it when the user asks which Folder templates exist, or "
        "to find the template id needed to create a Folder from a template. Requires workspace_id (see clickup.workspaces.list). Read-only and not paginated: it "
        "does not create folders, does not show what a template contains and does not edit templates. For task and list templates use "
        "clickup.task_templates.list and clickup.list_templates.list."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"templates": [{"id": "ft-1", "name": "Client onboarding"}]}}],
)
async def folder_templates_list(ctx: Context, args: WorkspaceIn) -> TemplatesOut:
    return TemplatesOut(templates=items(await get(ctx, f"{V2}/team/{args.workspace_id}/folder_template"), "templates"))
