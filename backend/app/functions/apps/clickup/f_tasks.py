"""ClickUp: tareas, comentarios, adjuntos, tiempo en estado y miembros de tarea (lecturas)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.functions.apps.clickup._common import (
    V2, V3, Cursor, Out, PathId, TaskIn, WorkspaceIn, get, items, obj, page_cursor, query,
)
from app.functions.apps.clickup.app_spec import APP  # noqa: F401
from app.functions.apps.clickup.f_hierarchy import CommentsIn, CommentsOut, MembersOut, comments_page
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb


# --- Tareas del Workspace --------------------------------------------------------------------------

class TaskFilters(BaseModel):
    page: int = Field(default=0, ge=0, description="Page number to read, starting at 0 (default 0); each page has up to 100 tasks")
    order_by: Optional[Literal["id", "created", "updated", "due_date"]] = Field(default=None, description="Sort field: id, created, updated or due_date (ClickUp default is created)")
    reverse: bool = Field(default=False, description="When true, reverses the sort order (default false)")
    subtasks: bool = Field(default=False, description="When true, subtasks are returned as tasks of their own (default false)")
    include_closed: bool = Field(default=False, description="When true, closed tasks are included (default false)")
    statuses: list[str] = Field(default_factory=list, description="Only tasks in these status names, for example ['to do', 'in progress']; empty means any status")
    assignees: list[str] = Field(default_factory=list, description="Only tasks assigned to these user ids (see clickup.lists.get_members); empty means anyone")
    tags: list[str] = Field(default_factory=list, description="Only tasks with these tag names, in lower case (see clickup.tags.list); empty means any")
    space_ids: list[str] = Field(default_factory=list, description="Only tasks in these Space ids; empty means all Spaces")
    folder_ids: list[str] = Field(default_factory=list, description="Only tasks in these folder ids (the API calls them project ids); empty means all folders")
    list_ids: list[str] = Field(default_factory=list, description="Only tasks in these list ids; empty means all lists")
    due_date_gt: Optional[int] = Field(default=None, description="Only tasks due after this Unix time in milliseconds")
    due_date_lt: Optional[int] = Field(default=None, description="Only tasks due before this Unix time in milliseconds")
    date_created_gt: Optional[int] = Field(default=None, description="Only tasks created after this Unix time in milliseconds")
    date_created_lt: Optional[int] = Field(default=None, description="Only tasks created before this Unix time in milliseconds")
    date_updated_gt: Optional[int] = Field(default=None, description="Only tasks updated after this Unix time in milliseconds")
    date_updated_lt: Optional[int] = Field(default=None, description="Only tasks updated before this Unix time in milliseconds")


class WorkspaceTasksIn(WorkspaceIn, TaskFilters):
    pass


class WorkspaceTasksOut(Out):
    tasks: list[dict] = Field(default_factory=list, description="Tasks found, each with id, name, status, priority, assignees, dates, tags, list and Space")
    last_page: Optional[bool] = Field(default=None, description="True when this is the last page of results")


def task_params(f: TaskFilters) -> dict:
    return query(
        page=f.page, order_by=f.order_by, reverse=f.reverse or None, subtasks=f.subtasks or None, include_closed=f.include_closed or None,
        **{"statuses[]": f.statuses, "assignees[]": f.assignees, "tags[]": f.tags, "space_ids[]": f.space_ids,
           "project_ids[]": f.folder_ids, "list_ids[]": f.list_ids},
        due_date_gt=f.due_date_gt, due_date_lt=f.due_date_lt, date_created_gt=f.date_created_gt, date_created_lt=f.date_created_lt,
        date_updated_gt=f.date_updated_gt, date_updated_lt=f.date_updated_lt,
    )


@function(
    id="clickup.tasks.list_workspace", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists tasks across a whole ClickUp Workspace, with optional filters, 100 tasks per page. Each task has its id, name, status, priority, assignees, dates, "
        "tags, custom fields, list, folder and Space. Filters: statuses, assignees (user ids), tags, space_ids, folder_ids, list_ids, due/created/updated date "
        "ranges in Unix milliseconds, include_closed and subtasks. Use it for requests such as 'tasks assigned to me that are due this week' across all Spaces. "
        "Requires workspace_id (see clickup.workspaces.list). Keep requesting page 1, 2... until last_page is true. Read-only. For one list use clickup.tasks.list "
        "and to look for words in task names use clickup.tasks.search."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "statuses": ["in progress"]}, "output": {
        "tasks": [{"id": "86abc12", "name": "Fix bug", "status": {"status": "in progress"}}], "last_page": True}}],
)
async def tasks_list_workspace(ctx: Context, args: WorkspaceTasksIn) -> WorkspaceTasksOut:
    body = await get(ctx, f"{V2}/team/{args.workspace_id}/task", task_params(args))
    return WorkspaceTasksOut(tasks=items(body, "tasks"), last_page=obj(body).get("last_page"))


class TasksSearchIn(WorkspaceIn, TaskFilters):
    query: Optional[str] = Field(default=None, description="Text to look for (case-insensitive) in the task name and description; empty applies only the filters")


class TasksSearchOut(Out):
    tasks: list[dict] = Field(default_factory=list, description="Tasks of the page that match the text and the filters")
    scanned: int = Field(default=0, description="How many tasks of this page were examined before matching the text")
    last_page: Optional[bool] = Field(default=None, description="True when this was the last page; if false, call again with page + 1 to keep searching")


def _matches(task: object, text: str) -> bool:
    t = obj(task)
    return text in str(t.get("name") or "").lower() or text in str(t.get("text_content") or t.get("description") or "").lower()


@function(
    id="clickup.tasks.search", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Searches the tasks of a ClickUp Workspace by text and filters. ClickUp's public API has no full-text search endpoint, so this reads one page of up to 100 "
        "filtered tasks (statuses, assignees, tags, Spaces, folders, lists, date ranges, include_closed) and keeps those whose name or description contains the "
        "query, ignoring case. Use it for requests such as 'find the tasks about invoices'. Requires workspace_id. The text is matched only inside the page that was "
        "read: when last_page is false, call again with page + 1 to continue. Read-only. It does not search comments or documents. For plain filtering without "
        "text use clickup.tasks.list_workspace."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "query": "bug"}, "output": {
        "tasks": [{"id": "86abc12", "name": "Fix bug"}], "scanned": 40, "last_page": True}}],
)
async def tasks_search(ctx: Context, args: TasksSearchIn) -> TasksSearchOut:
    body = await get(ctx, f"{V2}/team/{args.workspace_id}/task", task_params(args))
    tasks = items(body, "tasks")
    text = (args.query or "").strip().lower()
    found = [t for t in tasks if _matches(t, text)] if text else tasks
    return TasksSearchOut(tasks=found, scanned=len(tasks), last_page=obj(body).get("last_page"))


# --- Tiempo en estado ------------------------------------------------------------------------------

class TimeInStatusOut(Out):
    current_status: Optional[dict] = Field(default=None, description="Status the task is in now: status name, color and total_time (minutes and since-date)")
    status_history: list[dict] = Field(default_factory=list, description="Past statuses, each with status name, color, type and total_time spent there")


_TIS_DESC = (
    "Returns how long a ClickUp task has spent in each status: the current status with its time since the task entered it, and the history of past statuses with "
    "the total time spent in each (in minutes, with the date since). Use it for cycle-time and lead-time questions such as 'how long was this task in review?'. "
    "Requires task_id. Read-only. The 'Time in Status' ClickApp must be enabled in the Workspace or ClickUp answers with an error. "
)


@function(
    id="clickup.tasks.get_time_in_status", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=_TIS_DESC + "It covers one task and changes nothing; for several tasks at once use clickup.time_in_status.get_workspace.",
    examples=[{"name": "default", "input": {"task_id": "86abc12"}, "output": {
        "current_status": {"status": "in progress", "total_time": {"by_minute": 120, "since": "1767225600000"}}, "status_history": []}}],
)
async def tasks_get_time_in_status(ctx: Context, args: TaskIn) -> TimeInStatusOut:
    return TimeInStatusOut(**obj(await get(ctx, f"{V2}/task/{args.task_id}/time_in_status")))


@function(
    id="clickup.time_in_status.get_task", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=_TIS_DESC + "It returns the same data as clickup.tasks.get_time_in_status; for many tasks in one call use clickup.time_in_status.get_workspace.",
    examples=[{"name": "default", "input": {"task_id": "86abc12"}, "output": {
        "current_status": {"status": "in progress", "total_time": {"by_minute": 120, "since": "1767225600000"}}, "status_history": []}}],
)
async def time_in_status_get_task(ctx: Context, args: TaskIn) -> TimeInStatusOut:
    return TimeInStatusOut(**obj(await get(ctx, f"{V2}/task/{args.task_id}/time_in_status")))


class BulkTimeInStatusIn(BaseModel):
    task_ids: list[PathId] = Field(min_length=1, max_length=100, description="Ids of the tasks to read, from 1 to 100 (see clickup.tasks.list_workspace)")
    workspace_id: Optional[PathId] = Field(default=None, description="Workspace id; only needed when the task ids are custom task ids (for example 'DEV-123')")
    custom_task_ids: bool = Field(default=False, description="Set to true when task_ids are custom task ids; workspace_id is then required (default false)")


class BulkTimeInStatusOut(Out):
    tasks: dict[str, dict] = Field(default_factory=dict, description="For each requested task id, its current_status and status_history (same shape as clickup.time_in_status.get_task)")


@function(
    id="clickup.time_in_status.get_workspace", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the time in status of several ClickUp tasks in one call (up to 100): for each task id, the current status with its time so far and the history of "
        "past statuses with the total time spent in each. Use it for cycle-time reports across many tasks, for example after listing them with "
        "clickup.tasks.list_workspace. Requires task_ids; if they are custom task ids (like 'DEV-123'), set custom_task_ids to true and pass workspace_id. "
        "Read-only. The 'Time in Status' ClickApp must be enabled in the Workspace. For one task use clickup.time_in_status.get_task."
    ),
    examples=[{"name": "default", "input": {"task_ids": ["86abc12", "86abc13"]}, "output": {"tasks": {
        "86abc12": {"current_status": {"status": "to do"}, "status_history": []}}}}],
)
async def time_in_status_get_workspace(ctx: Context, args: BulkTimeInStatusIn) -> BulkTimeInStatusOut:
    # GET /task/bulk_time_in_status/task_ids  (la ruta del catalogo /team/{id}/task/time_in_status no existe)
    params = query(task_ids=args.task_ids, custom_task_ids=args.custom_task_ids or None, team_id=args.workspace_id if args.custom_task_ids else None)
    body = obj(await get(ctx, f"{V2}/task/bulk_time_in_status/task_ids", params))
    return BulkTimeInStatusOut(tasks={str(k): obj(v) for k, v in body.items()})


# --- Comentarios -----------------------------------------------------------------------------------

class TaskCommentsIn(TaskIn, CommentsIn):
    pass


@function(
    id="clickup.comments.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the comments written on one ClickUp task, newest first, 25 per page. Each comment has its id, text (comment_text), author, date, whether it is "
        "resolved, the assignee, reactions and the number of replies. Use it when the user asks 'what was said on this task?'. Requires task_id (see "
        "clickup.tasks.list). To read older comments pass the returned next_start and next_start_id as start and start_id. Read-only. It does not include replies "
        "in threads (use clickup.comments.list_replies with a comment id) and does not return comments of lists (use clickup.lists.get_comments)."
    ),
    examples=[{"name": "default", "input": {"task_id": "86abc12"}, "output": {"comments": [
        {"id": "c1", "comment_text": "Needs a fix", "user": {"id": 12, "username": "ana"}, "date": "1767225600000", "reply_count": "1"}]}}],
)
async def comments_list(ctx: Context, args: TaskCommentsIn) -> CommentsOut:
    return comments_page(await get(ctx, f"{V2}/task/{args.task_id}/comment", query(start=args.start, start_id=args.start_id)))


class CommentIn(BaseModel):
    comment_id: PathId = Field(description="Id of the parent comment whose replies are wanted; get it from clickup.comments.list or clickup.lists.get_comments")


class RepliesOut(Out):
    replies: list[dict] = Field(default_factory=list, description="Replies of the comment thread, each with id, comment_text, user, date and resolved")


@function(
    id="clickup.comments.list_replies", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the replies of one ClickUp comment thread: for each reply its id, text, author, date and whether it is resolved. Use it when a comment shows a "
        "reply_count above zero and the user wants to read the conversation under it. Requires comment_id, which comes from clickup.comments.list or "
        "clickup.lists.get_comments. Read-only. ClickUp returns the whole thread in one response. It does not return the parent comment itself and does not "
        "post replies."
    ),
    examples=[{"name": "default", "input": {"comment_id": "c1"}, "output": {"replies": [
        {"id": "c2", "comment_text": "Done", "user": {"id": 13, "username": "bob"}, "date": "1767225700000"}]}}],
)
async def comments_list_replies(ctx: Context, args: CommentIn) -> RepliesOut:
    # GET /comment/{comment_id}/reply  (la ruta del catalogo /comment/{id}/comment no existe)
    return RepliesOut(replies=items(await get(ctx, f"{V2}/comment/{args.comment_id}/reply"), "comments"))


# Verificado con la API real (2026-10-09): GET /api/v3/workspaces/{ws}/tasks/{task}/attachments responde 200; con `attachments` en ese tramo da 404
# "Not Found or Authorized" y con `task` 400 "Invalid path param for entityType". `custom_fields` viene de la referencia oficial y no se probo (no hay campos File).
# --- Adjuntos --------------------------------------------------------------------------------------

class AttachmentsIn(WorkspaceIn, Cursor):
    entity_id: PathId = Field(description="Id of the task (or of the File-type custom field) whose attachments are wanted")
    entity_type: Literal["tasks", "custom_fields"] = Field(
        default="tasks", description="'tasks' when entity_id is a task id (default) or 'custom_fields' for a File-type custom field id")


class AttachmentsOut(Out):
    attachments: list[dict] = Field(default_factory=list, description="Attachments, each with id, title, extension, mime_type, size, url, thumbnails, dates and the user who added it")
    next_cursor: Optional[str] = Field(default=None, description="Pass as cursor to get the next page; empty when there are no more attachments")


@function(
    id="clickup.attachments.list", version=2, verb=Verb.read, upstream_api="v3", scopes=[],
    description=(
        "Lists the files attached to a ClickUp task (or to a File-type custom field): for each attachment its id, title, extension, MIME type, size in bytes, "
        "download URL, thumbnails, creation date and the id of the user who added it. Use it when the user asks which files a task has. Requires workspace_id, "
        "entity_id (the task id) and optionally entity_type, limit (1 to 100, default 50) and cursor: pass the returned next_cursor to read the next page. "
        "Read-only. It does not download or upload files. This function uses the ClickUp v3 API; the download URLs may be temporary signed links."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "entity_id": "86abc12"}, "output": {
        "attachments": [{"id": "att-1", "title": "spec.pdf", "extension": "pdf", "size": 2048}], "next_cursor": None}}],
)
async def attachments_list(ctx: Context, args: AttachmentsIn) -> AttachmentsOut:
    body = await get(ctx, f"{V3}/workspaces/{args.workspace_id}/{args.entity_type}/{args.entity_id}/attachments", query(cursor=args.cursor, limit=args.limit))
    return AttachmentsOut(attachments=items(body, "data"), next_cursor=page_cursor(body))


# --- Miembros de una tarea -------------------------------------------------------------------------

@function(
    id="clickup.task_members.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the people who have explicit access to one ClickUp task, besides those who get access through the list, folder or Space: id, username, email, "
        "initials and profile picture of each. Use it when the user asks 'who is on this task?' or 'who else can see it?'. Requires task_id (see "
        "clickup.tasks.list). Read-only. It does not return the assignees or watchers of the task (those are fields of the task itself) and does not change "
        "access. For the people of a list use clickup.lists.get_members."
    ),
    examples=[{"name": "default", "input": {"task_id": "86abc12"}, "output": {"members": [{"id": 12, "username": "ana", "email": "ana@example.com"}]}}],
)
async def task_members_list(ctx: Context, args: TaskIn) -> MembersOut:
    return MembersOut(members=items(await get(ctx, f"{V2}/task/{args.task_id}/member"), "members"))
