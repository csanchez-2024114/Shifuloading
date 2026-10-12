"""ClickUp: las 14 herramientas viejas migradas al estandar nuevo (tarea 7). Las de escritura se simulan por defecto en /debug.

Rutas verificadas en la OpenAPI oficial (2026-10-08). El catalogo se equivoca en dos: asignar una tarea y cambiar su fecha NO tienen endpoint
propio, ambos son `PUT /task/{task_id}` (assignees.add/rem y due_date).
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.functions.apps.clickup._common import (
    V2, V3, Cursor, FolderIn, Ident, ListIn, Out, PathId, SpaceIn, TaskIn, WorkspaceIn, get, items, obj, page_cursor, query, send,
)
from app.functions.apps.clickup.app_spec import APP  # noqa: F401
from app.functions.apps.clickup.f_hierarchy import FolderOut, ListOut, MembersOut
from app.functions.apps.clickup.f_tasks import WorkspaceTasksOut
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb



# --- Spaces y carpetas -----------------------------------------------------------------------------

class ArchivedOpt(BaseModel):
    archived: bool = Field(default=False, description="When true, returns archived items instead of active ones (default false)")


class SpacesListIn(WorkspaceIn, ArchivedOpt):
    pass


class SpacesOut(Out):
    spaces: list[dict] = Field(default_factory=list, description="Spaces found, each with id, name, color, private flag, statuses and enabled features")


@function(
    id="clickup.spaces.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the Spaces of a ClickUp Workspace: for each one its id, name, color, whether it is private, its task statuses and the features enabled (due dates, "
        "time tracking, tags, custom fields...). Use it when the user asks 'which spaces do I have?' or needs a space_id for other functions. Requires "
        "workspace_id (see clickup.workspaces.list); set archived to true to list archived Spaces. Read-only and not paginated. It does not list the folders or "
        "lists inside (use clickup.folders.list and clickup.lists.list_folderless) and it returns only the Spaces the connected user can see."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"spaces": [{"id": "321", "name": "Engineering", "private": False}]}}],
)
async def spaces_list(ctx: Context, args: SpacesListIn) -> SpacesOut:
    return SpacesOut(spaces=items(await get(ctx, f"{V2}/team/{args.workspace_id}/space", query(archived=args.archived or None)), "spaces"))


class FoldersListIn(SpaceIn, ArchivedOpt):
    pass


class FoldersOut(Out):
    folders: list[dict] = Field(default_factory=list, description="Folders found, each with id, name, task count, archived flag, statuses and the lists it contains")


@function(
    id="clickup.folders.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the folders of one ClickUp Space: for each folder its id, name, task count, whether it is hidden or archived, and the lists inside it with their ids "
        "and names. Use it when the user asks what folders a Space has, or needs a folder_id for other functions. Requires space_id (see clickup.spaces.list); set "
        "archived to true to list archived folders. Read-only and not paginated. Lists that sit directly in the Space without a folder are returned by "
        "clickup.lists.list_folderless, not here."
    ),
    examples=[{"name": "default", "input": {"space_id": "321"}, "output": {"folders": [{"id": "456", "name": "Backlog", "task_count": "12", "lists": [{"id": "901"}]}]}}],
)
async def folders_list(ctx: Context, args: FoldersListIn) -> FoldersOut:
    return FoldersOut(folders=items(await get(ctx, f"{V2}/space/{args.space_id}/folder", query(archived=args.archived or None)), "folders"))


class FolderCreateIn(SpaceIn):
    name: str = Field(min_length=1, max_length=255, description="Name of the new folder, for example 'Q4 Campaigns'")
    parent_folder_id: Optional[PathId] = Field(default=None, description="Id of an existing folder in the same Space to create this folder inside as a subfolder; needs subfolders enabled in the Workspace. Empty creates a top-level folder")


@function(
    id="clickup.folders.create", version=1, verb=Verb.create, upstream_api="v2", scopes=[],
    description=(
        "Creates a new folder in a ClickUp Space and returns it with its id, name and Space. Use it when the user asks to create or add a folder, for example to group "
        "the lists of a project. Requires space_id (see clickup.spaces.list) and name; parent_folder_id makes it a subfolder when the Workspace supports that. "
        "It writes to ClickUp, so confirm the name first. It does not create lists inside the folder (use clickup.lists.create), does not rename or delete "
        "folders and does not check for duplicates: creating the same name twice makes two folders."
    ),
    examples=[{"name": "default", "input": {"space_id": "321", "name": "Q4 Campaigns"}, "output": {"id": "457", "name": "Q4 Campaigns", "archived": False, "lists": []}}],
)
async def folders_create(ctx: Context, args: FolderCreateIn) -> FolderOut:
    payload = {"name": args.name, **({"parent_folder_id": args.parent_folder_id} if args.parent_folder_id else {})}
    body = obj(await send(ctx, "POST", f"{V2}/space/{args.space_id}/folder", payload))
    return FolderOut(**{**body, "lists": [x for x in body.get("lists", []) if isinstance(x, dict)]})


# --- Listas ----------------------------------------------------------------------------------------

class ListsInFolderIn(FolderIn, ArchivedOpt):
    pass


class ListsOut(Out):
    lists: list[dict] = Field(default_factory=list, description="Lists found, each with id, name, task count, status, priority, due date and the folder and Space it belongs to")


@function(
    id="clickup.lists.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the lists that are inside one ClickUp folder: for each list its id, name, task count, content, status, priority, assignee and due date. Use it when "
        "the user asks what lists a folder has, or needs a list_id for other functions such as clickup.tasks.list. Requires folder_id (see clickup.folders.list); set "
        "archived to true to list archived lists. Read-only and not paginated. Lists that are not in any folder are returned by clickup.lists.list_folderless. "
        "It does not return the tasks of the lists."
    ),
    examples=[{"name": "default", "input": {"folder_id": "456"}, "output": {"lists": [{"id": "901", "name": "Sprint 1", "task_count": 10}]}}],
)
async def lists_list(ctx: Context, args: ListsInFolderIn) -> ListsOut:
    return ListsOut(lists=items(await get(ctx, f"{V2}/folder/{args.folder_id}/list", query(archived=args.archived or None)), "lists"))


class ListCreateIn(FolderIn):
    name: str = Field(min_length=1, max_length=255, description="Name of the new list, for example 'Sprint 12'")
    content: Optional[str] = Field(default=None, description="Description of the list; leave empty for none")
    due_date: Optional[int] = Field(default=None, description="Due date of the list as Unix time in milliseconds")
    due_date_time: Optional[bool] = Field(default=None, description="True when due_date includes a time of day, false when it is a whole day")
    priority: Optional[int] = Field(default=None, ge=1, le=4, description="Priority of the list: 1 urgent, 2 high, 3 normal, 4 low")
    assignee: Optional[int] = Field(default=None, description="User id of the person to assign the list to (see clickup.lists.get_members)")
    status: Optional[str] = Field(default=None, description="Color label of the list (not a task status); leave empty to use the default")


@function(
    id="clickup.lists.create", version=1, verb=Verb.create, upstream_api="v2", scopes=[],
    description=(
        "Creates a new list inside a ClickUp folder and returns it with its id, name and task count. Use it when the user asks to create or add a list, for example "
        "a new sprint. Requires folder_id (see clickup.folders.list) and name; optional content (description), due_date in Unix milliseconds, priority from 1 "
        "(urgent) to 4 (low), assignee user id and status color. It writes to ClickUp, so confirm the details first. It does not create folderless lists, does not "
        "add tasks (use clickup.tasks.create) and does not rename or delete lists."
    ),
    examples=[{"name": "default", "input": {"folder_id": "456", "name": "Sprint 12", "priority": 2}, "output": {"id": "902", "name": "Sprint 12", "task_count": "0"}}],
)
async def lists_create(ctx: Context, args: ListCreateIn) -> ListOut:
    payload = {k: v for k, v in args.model_dump(exclude={"folder_id"}).items() if v is not None}
    return ListOut(**obj(await send(ctx, "POST", f"{V2}/folder/{args.folder_id}/list", payload)))


@function(
    id="clickup.members.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the people who have access to one ClickUp list: id, username, email, initials and profile picture of each. Use it when the user asks 'who is on this "
        "list?' or needs a user id to assign a task or filter by assignee. Requires list_id (see clickup.lists.list). Read-only. ClickUp returns the people with "
        "explicit access to the list, not every member of the Workspace. It returns the same data as clickup.lists.get_members; for the people on one task use "
        "clickup.task_members.list. It does not change permissions."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {"members": [{"id": 12, "username": "ana", "email": "ana@example.com"}]}}],
)
async def members_list(ctx: Context, args: ListIn) -> MembersOut:
    return MembersOut(members=items(await get(ctx, f"{V2}/list/{args.list_id}/member"), "members"))


# --- Tareas ----------------------------------------------------------------------------------------

class ListTasksIn(ListIn):
    page: int = Field(default=0, ge=0, description="Page number to read, starting at 0 (default 0); each page has up to 100 tasks")
    order_by: Optional[Literal["id", "created", "updated", "due_date"]] = Field(default=None, description="Sort field: id, created, updated or due_date (ClickUp default is created)")
    reverse: bool = Field(default=False, description="When true, reverses the sort order (default false)")
    subtasks: bool = Field(default=False, description="When true, subtasks are returned as tasks of their own (default false)")
    include_closed: bool = Field(default=False, description="When true, closed tasks are included (default false)")
    archived: bool = Field(default=False, description="When true, archived tasks are included (default false)")
    statuses: list[str] = Field(default_factory=list, description="Only tasks in these status names, for example ['to do', 'in progress']; empty means any status")
    assignees: list[str] = Field(default_factory=list, description="Only tasks assigned to these user ids (see clickup.lists.get_members); empty means anyone")
    tags: list[str] = Field(default_factory=list, description="Only tasks with these tag names, in lower case (see clickup.tags.list); empty means any")
    due_date_gt: Optional[int] = Field(default=None, description="Only tasks due after this Unix time in milliseconds")
    due_date_lt: Optional[int] = Field(default=None, description="Only tasks due before this Unix time in milliseconds")


@function(
    id="clickup.tasks.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the tasks of one ClickUp list, 100 per page. Each task has its id, name, status, priority, assignees, dates, tags and custom fields. Filters: "
        "statuses, assignees (user ids), tags, due date range, include_closed, archived and subtasks. Use it for requests such as 'what is open in this list?'. "
        "Requires list_id (see clickup.lists.list); keep requesting page 1, 2... until last_page is true. Read-only. For tasks across the whole Workspace use "
        "clickup.tasks.list_workspace, and for the full detail of one task use clickup.tasks.get."
    ),
    examples=[{"name": "default", "input": {"list_id": "901"}, "output": {"tasks": [{"id": "86abc12", "name": "Fix bug", "status": {"status": "to do"}}], "last_page": True}}],
)
async def tasks_list(ctx: Context, args: ListTasksIn) -> WorkspaceTasksOut:
    params = query(page=args.page, order_by=args.order_by, reverse=args.reverse or None, subtasks=args.subtasks or None,
                   include_closed=args.include_closed or None, archived=args.archived or None,
                   **{"statuses[]": args.statuses, "assignees[]": args.assignees, "tags[]": args.tags},
                   due_date_gt=args.due_date_gt, due_date_lt=args.due_date_lt)
    body = await get(ctx, f"{V2}/list/{args.list_id}/task", params)
    return WorkspaceTasksOut(tasks=items(body, "tasks"), last_page=obj(body).get("last_page"))


class TaskGetIn(TaskIn):
    include_subtasks: bool = Field(default=False, description="When true, the subtasks of the task are included in the answer (default false)")
    include_markdown_description: bool = Field(default=False, description="When true, the description is also returned as Markdown (default false)")


class TaskOut(Out):
    id: Ident = Field(default=None, description="Task id")
    name: Optional[str] = Field(default=None, description="Name of the task")
    status: Optional[dict] = Field(default=None, description="Current status of the task: status name, color and type")
    url: Optional[str] = Field(default=None, description="Link to open the task in ClickUp")


@function(
    id="clickup.tasks.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the full detail of one ClickUp task: id, name, description, status, priority, assignees, watchers, dates, due date, tags, checklists, custom fields, "
        "dependencies, attachments, the list, folder and Space it lives in, and its link. Set include_subtasks to also get its subtasks. Use it when the user asks "
        "about a specific task. Requires task_id (see clickup.tasks.list). Read-only. It does not return comments (use clickup.comments.list), time per status "
        "(clickup.tasks.get_time_in_status) or people with explicit access (clickup.task_members.list)."
    ),
    examples=[{"name": "default", "input": {"task_id": "86abc12"}, "output": {
        "id": "86abc12", "name": "Fix bug", "status": {"status": "to do"}, "url": "https://app.clickup.com/t/86abc12"}}],
)
async def tasks_get(ctx: Context, args: TaskGetIn) -> TaskOut:
    params = query(include_subtasks=args.include_subtasks or None, include_markdown_description=args.include_markdown_description or None)
    return TaskOut(**obj(await get(ctx, f"{V2}/task/{args.task_id}", params)))


class CustomFieldValue(BaseModel):
    id: PathId = Field(description="Id of the custom field to set (see clickup.custom_fields.list_list)")
    value: Any = Field(description="Value to store; its shape depends on the field type (text, number, dropdown option id, Unix milliseconds for dates...)")


class TaskCreateIn(ListIn):
    name: str = Field(min_length=1, max_length=1000, description="Name (title) of the new task")
    description: Optional[str] = Field(default=None, description="Description of the task; leave empty for none")
    assignees: list[int] = Field(default_factory=list, description="User ids to assign the task to (see clickup.lists.get_members); assignees are notified")
    tags: list[str] = Field(default_factory=list, description="Tag names to put on the task (see clickup.tags.list)")
    status: Optional[str] = Field(default=None, description="Status name for the task; must exist in the list. Empty uses the first status of the list")
    priority: Optional[int] = Field(default=None, ge=1, le=4, description="Priority: 1 urgent, 2 high, 3 normal, 4 low; empty means no priority")
    due_date: Optional[int] = Field(default=None, description="Due date as Unix time in milliseconds")
    due_date_time: Optional[bool] = Field(default=None, description="True when due_date includes a time of day, false when it is a whole day")
    parent: Optional[PathId] = Field(default=None, description="Id of an existing task of the same list to create this task as its subtask")
    custom_fields: list[CustomFieldValue] = Field(default_factory=list, description="Custom field values to set, each with the field id and its value")


@function(
    id="clickup.tasks.create", version=1, verb=Verb.create, upstream_api="v2", scopes=[],
    description=(
        "Creates a new task in a ClickUp list and returns it with its id, name, status and link. Use it when the user asks to create, add or log a task. Requires "
        "list_id (see clickup.lists.list) and name; optional description, assignees (user ids), tags, status, priority from 1 (urgent) to 4 (low), due_date in Unix "
        "milliseconds, parent (to make a subtask) and custom_fields. It writes to ClickUp and notifies the assignees, so confirm the details first. It does not "
        "check for duplicates, does not edit existing tasks (use clickup.tasks.assign or clickup.tasks.update_due_date) and does not add comments."
    ),
    examples=[{"name": "default", "input": {"list_id": "901", "name": "Fix login bug", "priority": 2}, "output": {
        "id": "86abc99", "name": "Fix login bug", "status": {"status": "to do"}, "url": "https://app.clickup.com/t/86abc99"}}],
)
async def tasks_create(ctx: Context, args: TaskCreateIn) -> TaskOut:
    payload: dict[str, Any] = {"name": args.name}
    for key in ("description", "status", "priority", "due_date", "due_date_time", "parent"):
        if getattr(args, key) is not None:
            payload[key] = getattr(args, key)
    for key in ("assignees", "tags"):
        if getattr(args, key):
            payload[key] = getattr(args, key)
    if args.custom_fields:
        payload["custom_fields"] = [f.model_dump() for f in args.custom_fields]
    return TaskOut(**obj(await send(ctx, "POST", f"{V2}/list/{args.list_id}/task", payload)))


class TaskAssignIn(TaskIn):
    user_id: int = Field(description="User id of the person to assign the task to (see clickup.lists.get_members)")
    remove_user_ids: list[int] = Field(default_factory=list, description="User ids to take off the task at the same time, to reassign it; empty keeps the current assignees")


@function(
    id="clickup.tasks.assign", version=1, verb=Verb.update, exits_outside=True, upstream_api="v2", scopes=[],
    description=(
        "Assigns a ClickUp task to a user and returns the updated task with its assignees. Optionally removes other assignees in the same call (remove_user_ids) to "
        "reassign it. Use it when the user asks to assign, give or reassign a task to someone. Requires task_id (see clickup.tasks.list) and user_id (see "
        "clickup.lists.get_members). It writes to ClickUp and ClickUp notifies the new assignee, so confirm first. It adds assignees to the current ones unless "
        "remove_user_ids is used, and it does not change any other field of the task."
    ),
    examples=[{"name": "default", "input": {"task_id": "86abc12", "user_id": 12}, "output": {
        "id": "86abc12", "name": "Fix bug", "assignees": [{"id": 12, "username": "ana"}]}}],
)
async def tasks_assign(ctx: Context, args: TaskAssignIn) -> TaskOut:
    # PUT /task/{task_id} con assignees.add/rem  (la ruta del catalogo POST /task/{id}/assignee no existe)
    payload = {"assignees": {"add": [args.user_id], "rem": args.remove_user_ids}}
    return TaskOut(**obj(await send(ctx, "PUT", f"{V2}/task/{args.task_id}", payload)))


class DueDateIn(TaskIn):
    due_date: int = Field(description="New due date as Unix time in milliseconds, for example 1767225600000")
    due_date_time: Optional[bool] = Field(default=None, description="True when due_date includes a time of day, false when it is a whole day; empty keeps ClickUp's default")


@function(
    id="clickup.tasks.update_due_date", version=1, verb=Verb.update, upstream_api="v2", scopes=[],
    description=(
        "Changes the due date of a ClickUp task and returns the updated task with its new due_date. Use it when the user asks to move, postpone or set the deadline of "
        "a task. Requires task_id (see clickup.tasks.list) and due_date as Unix time in milliseconds; set due_date_time to true when the value includes a time of "
        "day. It writes to ClickUp and can be undone by setting the previous date. It changes only the due date: it does not touch the start date, status or "
        "assignees (use clickup.tasks.assign for those) and it cannot clear the date."
    ),
    examples=[{"name": "default", "input": {"task_id": "86abc12", "due_date": 1767225600000}, "output": {"id": "86abc12", "name": "Fix bug", "due_date": "1767225600000"}}],
)
async def tasks_update_due_date(ctx: Context, args: DueDateIn) -> TaskOut:
    # PUT /task/{task_id}  (la ruta del catalogo PUT /task/{id}/due_date no existe)
    payload = {"due_date": args.due_date, **({"due_date_time": args.due_date_time} if args.due_date_time is not None else {})}
    return TaskOut(**obj(await send(ctx, "PUT", f"{V2}/task/{args.task_id}", payload)))


# --- Comentarios -----------------------------------------------------------------------------------

class CommentCreateIn(TaskIn):
    comment_text: str = Field(min_length=1, max_length=10000, description="Text of the comment to post on the task")
    assignee: Optional[int] = Field(default=None, description="User id to assign the comment to as an action item; empty for none")
    notify_all: bool = Field(default=False, description="When true, the author is notified too; assignees and watchers are always notified (default false)")


class CommentCreatedOut(Out):
    id: Ident = Field(default=None, description="Id of the new comment")
    hist_id: Optional[str] = Field(default=None, description="History id of the new comment")
    date: Ident = Field(default=None, description="Creation time of the comment as Unix milliseconds")


@function(
    id="clickup.comments.create", version=1, verb=Verb.create, exits_outside=True, upstream_api="v2", scopes=[],
    description=(
        "Posts a new comment on a ClickUp task, written as the connected user, and returns the comment id, history id and date. Use it when the user asks to comment "
        "on, reply to or leave a note on a task. Requires task_id (see clickup.tasks.list) and comment_text; assignee turns the comment into an action item for that "
        "user. It writes to ClickUp and notifies the task's assignees and watchers, so show the text and ask for confirmation first. It cannot edit or delete "
        "comments and does not reply inside a comment thread."
    ),
    examples=[{"name": "default", "input": {"task_id": "86abc12", "comment_text": "Deployed to staging."}, "output": {"id": "458", "hist_id": "h-1", "date": "1767225600000"}}],
)
async def comments_create(ctx: Context, args: CommentCreateIn) -> CommentCreatedOut:
    payload: dict[str, Any] = {"comment_text": args.comment_text, "notify_all": args.notify_all}
    if args.assignee is not None:
        payload["assignee"] = args.assignee
    return CommentCreatedOut(**obj(await send(ctx, "POST", f"{V2}/task/{args.task_id}/comment", payload)))


# --- Docs (API v3) ---------------------------------------------------------------------------------

class DocsSearchIn(WorkspaceIn, Cursor):
    query: Optional[str] = Field(default=None, description="Text to look for (case-insensitive) in the Doc names of the page read; empty returns every Doc of the page")
    creator: Optional[int] = Field(default=None, description="Only Docs created by this user id")
    archived: bool = Field(default=False, description="When true, returns archived Docs (default false)")
    deleted: bool = Field(default=False, description="When true, returns deleted Docs (default false)")
    parent_id: Optional[PathId] = Field(default=None, description="Only Docs whose parent location has this id (a Space, folder or list id)")
    parent_type: Optional[Literal["SPACE", "FOLDER", "LIST", "EVERYTHING", "WORKSPACE"]] = Field(default=None, description="Type of the parent location used with parent_id: SPACE, FOLDER, LIST, EVERYTHING or WORKSPACE")


class DocsSearchOut(Out):
    docs: list[dict] = Field(default_factory=list, description="Docs found, each with id, name, creator, parent location, dates and archived/deleted flags")
    scanned: int = Field(default=0, description="How many Docs of this page were examined before matching the name")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to read the next page; empty when there are no more Docs")


@function(
    id="clickup.docs.search", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Finds the Docs of a ClickUp Workspace by name. ClickUp's API has no name search, so this reads one page of Docs (filtered by creator, parent location, "
        "archived or deleted) and keeps those whose name contains the query, ignoring case. Each Doc has its id, name, creator, parent, dates and flags. Use it "
        "when the user asks 'find the doc about onboarding'. Requires workspace_id; limit is 1 to 100 (default 50) and next_cursor pages on when more exist. "
        "Read-only. It does not return page content: use clickup.docs.get for the Doc and clickup.docs.get_pages for its text. It uses the ClickUp v3 API."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "query": "onboarding"}, "output": {
        "docs": [{"id": "8cnn-1234", "name": "Onboarding guide"}], "scanned": 20, "next_cursor": None}}],
)
async def docs_search(ctx: Context, args: DocsSearchIn) -> DocsSearchOut:
    params = query(limit=args.limit, cursor=args.cursor, creator=args.creator, archived=args.archived or None, deleted=args.deleted or None,
                   parent_id=args.parent_id, parent_type=args.parent_type)
    body = await get(ctx, f"{V3}/workspaces/{args.workspace_id}/docs", params)
    docs = items(body, "docs")
    text = (args.query or "").strip().lower()
    found = [d for d in docs if text in str(obj(d).get("name") or "").lower()] if text else docs
    return DocsSearchOut(docs=found, scanned=len(docs), next_cursor=page_cursor(body))


class DocGetIn(WorkspaceIn):
    doc_id: PathId = Field(description="ClickUp Doc id, for example '8cnn-1234'. Get it from clickup.docs.search")


class DocOut(Out):
    doc: Optional[dict] = Field(default=None, description="The Doc: id, name, creator, parent location, public flag, dates, archived/deleted flags and page defaults")


@function(
    id="clickup.docs.get", version=1, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Returns the information of one ClickUp Doc: id, name, creator, the Space, folder or list it lives in, whether it is public, creation and update dates, "
        "archived and deleted flags and its page display defaults. Use it when the user asks about a specific Doc, for example who created it or where it is. "
        "Requires workspace_id and doc_id (see clickup.docs.search). Read-only. It does not include the text: read the outline with clickup.docs.get_page_listing "
        "and the content with clickup.docs.get_pages or clickup.pages.get. It does not edit Docs. It uses the ClickUp v3 API."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "doc_id": "8cnn-1234"}, "output": {"doc": {"id": "8cnn-1234", "name": "Onboarding guide", "creator": 12}}}],
)
async def docs_get(ctx: Context, args: DocGetIn) -> DocOut:
    return DocOut(doc=obj(await get(ctx, f"{V3}/workspaces/{args.workspace_id}/docs/{args.doc_id}")))
