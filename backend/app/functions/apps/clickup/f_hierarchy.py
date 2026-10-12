"""ClickUp: Spaces, carpetas, listas, etiquetas, campos personalizados, tipos de tarea personalizados y vistas (lecturas)."""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.clickup._common import (
    V2, FolderIn, Ident, ListIn, Out, SpaceIn, ViewIn, WorkspaceIn, get, items, obj, query,
)
from app.functions.apps.clickup.app_spec import APP  # noqa: F401
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

COMMENT_PAGE_SIZE = 25  # ClickUp devuelve los comentarios de 25 en 25 (docs/task-comments-pagination)


# --- Spaces ----------------------------------------------------------------------------------------

class SpaceOut(Out):
    id: Ident = Field(default=None, description="Space id")
    name: Optional[str] = Field(default=None, description="Name of the Space")
    private: Optional[bool] = Field(default=None, description="True when the Space is private")
    statuses: list[dict] = Field(default_factory=list, description="Task statuses defined at Space level")
    features: Optional[dict] = Field(default=None, description="Features enabled in the Space: due dates, time tracking, tags, checklists, custom fields...")


@function(
    id="clickup.spaces.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the details of one ClickUp Space: its id, name, whether it is private, the task statuses defined for the Space, whether several people can be "
        "assigned to a task, and which features are enabled (due dates, time tracking, tags, time estimates, checklists, custom fields, dependencies, portfolios). "
        "Use it when the user asks about the configuration of a Space. Requires space_id (see clickup.spaces.list). Read-only. It does not list the folders or "
        "lists inside the Space (use clickup.folders.list and clickup.lists.list_folderless), the members, or the views (use clickup.spaces.get_views)."
    ),
    examples=[{"name": "default", "input": {"space_id": "321"}, "output": {
        "id": "321", "name": "Engineering", "private": False, "statuses": [{"status": "to do", "type": "open"}], "features": {"tags": {"enabled": True}}}}],
)
async def spaces_get(ctx: Context, args: SpaceIn) -> SpaceOut:
    return SpaceOut(**obj(await get(ctx, f"{V2}/space/{args.space_id}")))


class ViewsOut(Out):
    views: list[dict] = Field(default_factory=list, description="Views found, each with id, name, type (list, board, calendar, table, gantt...), filters, grouping and sorting")


@function(
    id="clickup.spaces.get_views", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the views (List, Board, Calendar, Table, Gantt...) created at the level of one ClickUp Space. Each view has its id, name, type, grouping, sorting, "
        "filters and visible columns. Use it when the user asks 'which views does this Space have?' or needs a view id to read its tasks with clickup.views.get_tasks. "
        "Requires space_id (see clickup.spaces.list). Read-only. It returns only views defined directly on the Space: for folder, list or Workspace-level views use "
        "clickup.folders.get_views, clickup.lists.get_views or clickup.views.list_workspace. It does not return tasks."
    ),
    examples=[{"name": "default", "input": {"space_id": "321"}, "output": {"views": [{"id": "3c-106", "name": "Board", "type": "board"}]}}],
)
async def spaces_get_views(ctx: Context, args: SpaceIn) -> ViewsOut:
    return ViewsOut(views=items(await get(ctx, f"{V2}/space/{args.space_id}/view"), "views"))


# --- Carpetas --------------------------------------------------------------------------------------

class FolderOut(Out):
    id: Ident = Field(default=None, description="Folder id")
    name: Optional[str] = Field(default=None, description="Name of the folder")
    task_count: Ident = Field(default=None, description="Number of tasks in the folder, as text")
    archived: Optional[bool] = Field(default=None, description="True when the folder is archived")
    lists: list[dict] = Field(default_factory=list, description="Lists inside the folder with id, name and task count")


@function(
    id="clickup.folders.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the details of one ClickUp folder: id, name, the Space it belongs to, whether it is archived, its task count, the statuses it overrides and the "
        "lists it contains (id, name, task count, due dates). Use it when the user asks what is inside a folder or to confirm the name of a folder. Requires "
        "folder_id (see clickup.folders.list). Read-only. It does not list the tasks of those lists (use clickup.tasks.list), the folder views "
        "(clickup.folders.get_views) or the custom fields (clickup.custom_fields.list_folder). ClickUp has no comments on folders."
    ),
    examples=[{"name": "default", "input": {"folder_id": "456"}, "output": {
        "id": "456", "name": "Backlog", "task_count": "12", "archived": False, "lists": [{"id": "901", "name": "Sprint 1"}]}}],
)
async def folders_get(ctx: Context, args: FolderIn) -> FolderOut:
    body = obj(await get(ctx, f"{V2}/folder/{args.folder_id}"))
    return FolderOut(**{**body, "lists": [x for x in body.get("lists", []) if isinstance(x, dict)]})


@function(
    id="clickup.folders.get_views", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the views (List, Board, Calendar, Table, Gantt...) created at the level of one ClickUp folder. Each view has its id, name, type, grouping, sorting and "
        "filters. Use it when the user asks which views a folder has or needs a view id to read its tasks with clickup.views.get_tasks. Requires folder_id "
        "(see clickup.folders.list). Read-only. It returns only views defined directly on the folder: for Space, list or Workspace-level views use "
        "clickup.spaces.get_views, clickup.lists.get_views or clickup.views.list_workspace. It does not return tasks."
    ),
    examples=[{"name": "default", "input": {"folder_id": "456"}, "output": {"views": [{"id": "5d-22", "name": "Overview", "type": "list"}]}}],
)
async def folders_get_views(ctx: Context, args: FolderIn) -> ViewsOut:
    return ViewsOut(views=items(await get(ctx, f"{V2}/folder/{args.folder_id}/view"), "views"))


# --- Listas ----------------------------------------------------------------------------------------

class FolderlessIn(SpaceIn):
    archived: bool = Field(default=False, description="When true, returns archived lists instead of active ones (default false)")


class ListsOut(Out):
    lists: list[dict] = Field(default_factory=list, description="Lists found, each with id, name, task count, status, priority, due date and the Space or folder it belongs to")


@function(
    id="clickup.lists.list_folderless", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the ClickUp lists of a Space that are not inside any folder (folderless lists). Each list has its id, name, task count, content, status, priority, "
        "assignee, due and start dates and whether it is archived. Use it when the user asks for the lists of a Space that sit directly in the Space, or when "
        "clickup.folders.list shows no folder for them. Requires space_id; set archived to true to see archived lists. Read-only and not paginated. It does not "
        "return lists inside folders (use clickup.lists.list) or tasks (use clickup.tasks.list)."
    ),
    examples=[{"name": "default", "input": {"space_id": "321"}, "output": {"lists": [{"id": "901", "name": "Inbox", "task_count": 5}]}}],
)
async def lists_list_folderless(ctx: Context, args: FolderlessIn) -> ListsOut:
    return ListsOut(lists=items(await get(ctx, f"{V2}/space/{args.space_id}/list", query(archived=args.archived or None)), "lists"))


class ListOut(Out):
    id: Ident = Field(default=None, description="List id")
    name: Optional[str] = Field(default=None, description="Name of the list")
    task_count: Ident = Field(default=None, description="Number of tasks in the list")
    archived: Optional[bool] = Field(default=None, description="True when the list is archived")
    statuses: list[dict] = Field(default_factory=list, description="Task statuses available in the list")


@function(
    id="clickup.lists.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the details of one ClickUp list: id, name, description (content), task count, due and start dates, priority, status, the folder and Space it "
        "belongs to, whether it is archived, its statuses and the email address that creates tasks in it. Use it when the user asks about a specific list or to "
        "learn which statuses its tasks can have. Requires list_id (see clickup.lists.list). Read-only. It does not return the tasks (use clickup.tasks.list), the "
        "members (clickup.lists.get_members), the comments (clickup.lists.get_comments) or the views (clickup.lists.get_views)."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {
        "id": "901", "name": "Sprint 1", "task_count": "10", "archived": False, "statuses": [{"status": "to do", "type": "open"}]}}],
)
async def lists_get(ctx: Context, args: ListIn) -> ListOut:
    return ListOut(**obj(await get(ctx, f"{V2}/list/{args.list_id}")))


class MembersOut(Out):
    members: list[dict] = Field(default_factory=list, description="People found, each with id, username, email, initials and profile picture")


@function(
    id="clickup.lists.get_members", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the people who have access to one ClickUp list: id, username, email, initials and profile picture of each. Use it when the user asks 'who can see or "
        "work on this list?' or needs a user id to filter tasks by assignee. Requires list_id (see clickup.lists.list). Read-only. ClickUp returns the people "
        "with explicit access to the list, not necessarily every member of the Workspace; for tasks use clickup.task_members.list and for user groups use "
        "clickup.workspace.get_groups. It does not change permissions."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {"members": [{"id": 12, "username": "ana", "email": "ana@example.com"}]}}],
)
async def lists_get_members(ctx: Context, args: ListIn) -> MembersOut:
    return MembersOut(members=items(await get(ctx, f"{V2}/list/{args.list_id}/member"), "members"))


class CommentsIn(BaseModel):
    start: Optional[int] = Field(default=None, description="Unix time in milliseconds of the last comment of the previous page (its date); use together with start_id, leave empty for the first page")
    start_id: Optional[str] = Field(default=None, description="Id of the last comment of the previous page; use together with start, leave empty for the first page")


class ListCommentsIn(ListIn, CommentsIn):
    pass


class CommentsOut(Out):
    comments: list[dict] = Field(default_factory=list, description="Comments newest first, each with id, comment_text, user, date, resolved, assignee and reply_count")
    next_start: Optional[int] = Field(default=None, description="Pass as start to get the next (older) page; empty when there are no more comments")
    next_start_id: Optional[str] = Field(default=None, description="Pass as start_id to get the next (older) page; empty when there are no more comments")


def comments_page(body: object) -> CommentsOut:
    """Los comentarios vienen del mas nuevo al mas viejo, 25 por pagina; la siguiente pagina se pide con el id y la fecha del ultimo."""
    comments = items(body, "comments")
    nxt = obj(comments[-1]) if len(comments) >= COMMENT_PAGE_SIZE else {}
    start = nxt.get("date")
    return CommentsOut(comments=comments, next_start=int(start) if str(start).isdigit() else None,
                       next_start_id=str(nxt["id"]) if nxt.get("id") is not None else None)


@function(
    id="clickup.lists.get_comments", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the comments written on a ClickUp list (not on its tasks), newest first, 25 per page. Each comment has its id, text, author, date, whether it is "
        "resolved, the assignee and the number of replies. Use it when the user asks what has been discussed on a list. Requires list_id (see clickup.lists.list). "
        "To get older comments pass the returned next_start and next_start_id as start and start_id. Read-only. It does not return task comments (use "
        "clickup.comments.list) or replies (clickup.comments.list_replies). ClickUp has no comments on folders."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {"comments": [
        {"id": "c1", "comment_text": "Kick-off done", "user": {"id": 12, "username": "ana"}, "date": "1767225600000"}]}}],
)
async def lists_get_comments(ctx: Context, args: ListCommentsIn) -> CommentsOut:
    body = await get(ctx, f"{V2}/list/{args.list_id}/comment", query(start=args.start, start_id=args.start_id))
    return comments_page(body)


@function(
    id="clickup.lists.get_views", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the views (List, Board, Calendar, Table, Gantt...) created at the level of one ClickUp list. Each view has its id, name, type, grouping, sorting and "
        "filters. Use it when the user asks which views a list has or needs a view id to read its tasks with clickup.views.get_tasks. Requires list_id "
        "(see clickup.lists.list). Read-only. It returns only views defined directly on the list: for Space, folder or Workspace-level views use "
        "clickup.spaces.get_views, clickup.folders.get_views or clickup.views.list_workspace. It does not return tasks."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {"views": [{"id": "7e-9", "name": "List", "type": "list"}]}}],
)
async def lists_get_views(ctx: Context, args: ListIn) -> ViewsOut:
    return ViewsOut(views=items(await get(ctx, f"{V2}/list/{args.list_id}/view"), "views"))


# --- Etiquetas -------------------------------------------------------------------------------------

class TagsOut(Out):
    tags: list[dict] = Field(default_factory=list, description="Tags of the Space, each with name, foreground color (tag_fg) and background color (tag_bg)")


@function(
    id="clickup.tags.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the task tags defined in one ClickUp Space: the name and the foreground and background colors of each. Use it when the user asks which tags exist, or "
        "to learn the exact tag names before filtering tasks with clickup.tasks.list_workspace or clickup.tasks.search. Requires space_id (see clickup.spaces.list). "
        "Read-only. Tags belong to a Space, so a Workspace-wide view needs one call per Space. It does not list the tasks that carry a tag and does not create or "
        "delete tags. Tags of time entries are returned by clickup.time_entries.list_tags."
    ),
    examples=[{"name": "default", "input": {"space_id": "321"}, "output": {"tags": [{"name": "bug", "tag_fg": "#fff", "tag_bg": "#f00"}]}}],
)
async def tags_list(ctx: Context, args: SpaceIn) -> TagsOut:
    return TagsOut(tags=items(await get(ctx, f"{V2}/space/{args.space_id}/tag"), "tags"))


# --- Campos personalizados -------------------------------------------------------------------------

class FieldsOptions(BaseModel):
    include_applied_objects: bool = Field(default=False, description="When true, each field also lists the objects (lists, folders, spaces) it is applied to (default false)")


class ListFieldsIn(ListIn, FieldsOptions):
    pass


class FolderFieldsIn(FolderIn, FieldsOptions):
    pass


class SpaceFieldsIn(SpaceIn, FieldsOptions):
    pass


class WorkspaceFieldsIn(WorkspaceIn, FieldsOptions):
    pass


class FieldsOut(Out):
    fields: list[dict] = Field(default_factory=list, description="Custom fields, each with id, name, type (text, drop_down, number, date, labels...), type_config with its options, and date_created")


def _fields(body: object) -> FieldsOut:
    return FieldsOut(fields=items(body, "fields"))


@function(
    id="clickup.custom_fields.list_list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the custom fields that are available on the tasks of one ClickUp list, including those inherited from its folder, Space or the whole Workspace. Each "
        "field has its id, name, type (text, number, drop_down, labels, date, checkbox...), the options of the field in type_config and its creation date. Use it "
        "when the user asks which custom fields a list has, or to learn field ids and dropdown option ids. Requires list_id; set include_applied_objects to see "
        "where each field is applied. Read-only. It does not return field values of tasks and does not create fields."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {"fields": [{"id": "cf1", "name": "Severity", "type": "drop_down"}]}}],
)
async def custom_fields_list_list(ctx: Context, args: ListFieldsIn) -> FieldsOut:
    return _fields(await get(ctx, f"{V2}/list/{args.list_id}/field", query(include_applied_objects=args.include_applied_objects or None)))


@function(
    id="clickup.custom_fields.list_folder", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the custom fields created at the level of one ClickUp folder. Each field has its id, name, type (text, number, drop_down, labels, date, checkbox...), "
        "the options of the field in type_config and its creation date. Use it when the user asks which custom fields a folder has, or to learn field ids and "
        "dropdown option ids. Requires folder_id (see clickup.folders.list); set include_applied_objects to see where each field is applied. Read-only. It does "
        "not include fields created on a single list or on the Space: use clickup.custom_fields.list_list or clickup.custom_fields.list_space for those."
    ),
    examples=[{"name": "default", "input": {"folder_id": "456"}, "output": {"fields": [{"id": "cf2", "name": "Budget", "type": "currency"}]}}],
)
async def custom_fields_list_folder(ctx: Context, args: FolderFieldsIn) -> FieldsOut:
    return _fields(await get(ctx, f"{V2}/folder/{args.folder_id}/field", query(include_applied_objects=args.include_applied_objects or None)))


@function(
    id="clickup.custom_fields.list_space", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the custom fields created at the level of one ClickUp Space. Each field has its id, name, type (text, number, drop_down, labels, date, checkbox...), "
        "the options of the field in type_config and its creation date. Use it when the user asks which custom fields a Space has, or to learn field ids and "
        "dropdown option ids. Requires space_id (see clickup.spaces.list); set include_applied_objects to see where each field is applied. Read-only. It does not "
        "include fields created on folders or lists inside the Space: use clickup.custom_fields.list_folder or clickup.custom_fields.list_list for those."
    ),
    examples=[{"name": "default", "input": {"space_id": "321"}, "output": {"fields": [{"id": "cf3", "name": "Owner team", "type": "text"}]}}],
)
async def custom_fields_list_space(ctx: Context, args: SpaceFieldsIn) -> FieldsOut:
    return _fields(await get(ctx, f"{V2}/space/{args.space_id}/field", query(include_applied_objects=args.include_applied_objects or None)))


@function(
    id="clickup.custom_fields.list_workspace", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the custom fields created at the level of a whole ClickUp Workspace (fields available everywhere, not only in one Space, folder or list). Each field "
        "has its id, name, type (text, number, drop_down, labels, date, checkbox...), the options of the field in type_config and its creation date. Use it when "
        "the user asks which Workspace-wide custom fields exist. Requires workspace_id (see clickup.workspaces.list); set include_applied_objects to see where each "
        "field is applied. Read-only. Fields created in a Space, folder or list are returned by the other clickup.custom_fields.list_* functions."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"fields": [{"id": "cf4", "name": "Customer", "type": "short_text"}]}}],
)
async def custom_fields_list_workspace(ctx: Context, args: WorkspaceFieldsIn) -> FieldsOut:
    return _fields(await get(ctx, f"{V2}/team/{args.workspace_id}/field", query(include_applied_objects=args.include_applied_objects or None)))


class CustomItemsOut(Out):
    custom_items: list[dict] = Field(default_factory=list, description="Custom task types, each with id, name, name_plural and description")


@function(
    id="clickup.custom_items.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the custom task types (custom items) of a ClickUp Workspace, such as Bug, Milestone or Epic, with their numeric id, name, plural name and "
        "description. Use it when the user asks which task types exist, or to learn the custom_item_id that identifies a type in task data. Requires workspace_id "
        "(see clickup.workspaces.list). Read-only. The built-in 'Task' type has id 0 and is not listed. It does not return the tasks of each type and does not create "
        "or edit types."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"custom_items": [{"id": 1001, "name": "Bug", "name_plural": "Bugs"}]}}],
)
async def custom_items_list(ctx: Context, args: WorkspaceIn) -> CustomItemsOut:
    return CustomItemsOut(custom_items=items(await get(ctx, f"{V2}/team/{args.workspace_id}/custom_item"), "custom_items"))


# --- Vistas ----------------------------------------------------------------------------------------

@function(
    id="clickup.views.list_workspace", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the views (List, Board, Calendar, Table, Gantt, Chat...) created at the Everything level of a ClickUp Workspace. Each view has its id, name, type, "
        "grouping, sorting and filters. Use it when the user asks which Workspace-level views exist, or needs a view id to read its tasks with "
        "clickup.views.get_tasks. Requires workspace_id (see clickup.workspaces.list). Read-only. Views of a Space, folder or list are returned by "
        "clickup.views.list_space, clickup.views.list_folder and clickup.views.list_list. It does not return tasks."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"views": [{"id": "2a-1", "name": "Everything", "type": "list"}]}}],
)
async def views_list_workspace(ctx: Context, args: WorkspaceIn) -> ViewsOut:
    return ViewsOut(views=items(await get(ctx, f"{V2}/team/{args.workspace_id}/view"), "views"))


@function(
    id="clickup.views.list_space", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the views (List, Board, Calendar, Table, Gantt...) created directly on one ClickUp Space. Each view has its id, name, type, grouping, sorting and "
        "filters. Use it when the user asks which views a Space has, or needs a view id to read its tasks with clickup.views.get_tasks. Requires space_id "
        "(see clickup.spaces.list). Read-only. It is the same data as clickup.spaces.get_views. For folder, list or Workspace-level views use "
        "clickup.views.list_folder, clickup.views.list_list or clickup.views.list_workspace. It does not return tasks."
    ),
    examples=[{"name": "default", "input": {"space_id": "321"}, "output": {"views": [{"id": "3c-106", "name": "Board", "type": "board"}]}}],
)
async def views_list_space(ctx: Context, args: SpaceIn) -> ViewsOut:
    return ViewsOut(views=items(await get(ctx, f"{V2}/space/{args.space_id}/view"), "views"))


@function(
    id="clickup.views.list_folder", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the views (List, Board, Calendar, Table, Gantt...) created directly on one ClickUp folder. Each view has its id, name, type, grouping, sorting and "
        "filters. Use it when the user asks which views a folder has, or needs a view id to read its tasks with clickup.views.get_tasks. Requires folder_id "
        "(see clickup.folders.list). Read-only. It is the same data as clickup.folders.get_views. For Space, list or Workspace-level views use "
        "clickup.views.list_space, clickup.views.list_list or clickup.views.list_workspace. It does not return tasks."
    ),
    examples=[{"name": "default", "input": {"folder_id": "456"}, "output": {"views": [{"id": "5d-22", "name": "Overview", "type": "list"}]}}],
)
async def views_list_folder(ctx: Context, args: FolderIn) -> ViewsOut:
    return ViewsOut(views=items(await get(ctx, f"{V2}/folder/{args.folder_id}/view"), "views"))


@function(
    id="clickup.views.list_list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the views (List, Board, Calendar, Table, Gantt...) created directly on one ClickUp list. Each view has its id, name, type, grouping, sorting and "
        "filters. Use it when the user asks which views a list has, or needs a view id to read its tasks with clickup.views.get_tasks. Requires list_id "
        "(see clickup.lists.list). Read-only. It is the same data as clickup.lists.get_views. For Space, folder or Workspace-level views use "
        "clickup.views.list_space, clickup.views.list_folder or clickup.views.list_workspace. It does not return tasks."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {"views": [{"id": "7e-9", "name": "List", "type": "list"}]}}],
)
async def views_list_list(ctx: Context, args: ListIn) -> ViewsOut:
    return ViewsOut(views=items(await get(ctx, f"{V2}/list/{args.list_id}/view"), "views"))


class ViewOut(Out):
    view: Optional[dict] = Field(default=None, description="The view: id, name, type, parent, grouping, divide, sorting, filters, columns and settings")


@function(
    id="clickup.views.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the full definition of one ClickUp view: id, name, type (list, board, calendar, table, gantt...), the location it belongs to (parent), grouping, "
        "sorting, filters, visible columns and sidebar settings. Use it when the user asks how a view is configured. Requires view_id, which comes from the "
        "clickup.views.list_* functions. Read-only. It does not return the tasks shown in the view: use clickup.views.get_tasks for those. It does not create or "
        "change views."
    ),
    examples=[{"name": "default", "input": {"view_id": "3c-106"}, "output": {"view": {"id": "3c-106", "name": "Board", "type": "board"}}}],
)
async def views_get(ctx: Context, args: ViewIn) -> ViewOut:
    body = obj(await get(ctx, f"{V2}/view/{args.view_id}"))
    return ViewOut(view=obj(body.get("view")) or body)


class ViewTasksIn(ViewIn):
    page: int = Field(default=0, ge=0, description="Page number to read, starting at 0 (default 0); each page has up to 30 tasks")


class ViewTasksOut(Out):
    tasks: list[dict] = Field(default_factory=list, description="Tasks that match the view, each with id, name, status, assignees, dates, tags and custom fields")
    last_page: Optional[bool] = Field(default=None, description="True when this is the last page of tasks of the view")


@function(
    id="clickup.views.get_tasks", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the tasks that a ClickUp view shows, after applying the filters, grouping and sorting saved in that view. Each task has its id, name, status, "
        "priority, assignees, dates, tags and custom fields. Use it when the user asks 'what is in this board or view?'. Requires view_id (from the "
        "clickup.views.list_* functions) and optionally page, starting at 0, with up to 30 tasks per page: keep asking for the next page until last_page is true. "
        "Read-only. It does not return the definition of the view (use clickup.views.get) and does not change tasks."
    ),
    examples=[{"name": "default", "input": {"view_id": "3c-106"}, "output": {"tasks": [{"id": "86abc12", "name": "Fix bug"}], "last_page": True}}],
)
async def views_get_tasks(ctx: Context, args: ViewTasksIn) -> ViewTasksOut:
    body = await get(ctx, f"{V2}/view/{args.view_id}/task", query(page=args.page))
    return ViewTasksOut(tasks=items(body, "tasks"), last_page=obj(body).get("last_page"))
