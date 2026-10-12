"""ClickUp: registros de tiempo, temporizador activo, etiquetas de tiempo y metas (lecturas)."""
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.functions.apps.clickup._common import V2, Out, PathId, WorkspaceIn, get, items, obj, query, unwrap
from app.functions.apps.clickup.app_spec import APP  # noqa: F401
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb


def _first(value: Any) -> Optional[dict]:
    """ClickUp devuelve el registro singular como objeto o como lista de uno, segun la cuenta."""
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, dict) else None


# --- Registros de tiempo ---------------------------------------------------------------------------

class TimeEntriesIn(WorkspaceIn):
    start_date: Optional[int] = Field(default=None, description="Start of the range as Unix time in milliseconds; ClickUp defaults to 30 days before end_date when empty")
    end_date: Optional[int] = Field(default=None, description="End of the range as Unix time in milliseconds; ClickUp defaults to now when empty")
    assignee: Optional[str] = Field(default=None, description="User id, or several ids separated by commas, whose time entries are wanted; only Workspace owners and admins can read other people's entries")
    space_id: Optional[PathId] = Field(default=None, description="Only entries of tasks in this Space id")
    folder_id: Optional[PathId] = Field(default=None, description="Only entries of tasks in this folder id")
    list_id: Optional[PathId] = Field(default=None, description="Only entries of tasks in this list id")
    task_id: Optional[PathId] = Field(default=None, description="Only entries logged on this task id")
    is_billable: Optional[bool] = Field(default=None, description="True returns only billable entries, false only non-billable ones; empty returns both")
    include_task_tags: bool = Field(default=False, description="When true, each entry also lists the tags of its task (default false)")
    include_location_names: bool = Field(default=False, description="When true, each entry also includes the names of its list, folder and Space (default false)")


class TimeEntriesOut(Out):
    time_entries: list[dict] = Field(default_factory=list, description="Time entries, each with id, task, user, start, end, duration in milliseconds, billable, description and tags")


@function(
    id="clickup.time_entries.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the time tracked in a ClickUp Workspace within a date range: for each time entry its id, the task, the user, start and end time, duration in "
        "milliseconds, whether it is billable, description and tags. Use it for timesheets and questions such as 'how many hours did I log last week?'. "
        "Requires workspace_id; start_date and end_date are Unix milliseconds (default: the last 30 days). It returns the entries of the connected user unless "
        "assignee is set, which only owners and admins may do. Filters: space_id, folder_id, list_id, task_id, is_billable. Read-only and not paginated. A negative "
        "duration marks a running timer; for the running timer use clickup.timer.get_running."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"time_entries": [
        {"id": "te1", "task": {"id": "86abc12", "name": "Fix bug"}, "user": {"id": 12, "username": "ana"}, "duration": "3600000", "billable": False}]}}],
)
async def time_entries_list(ctx: Context, args: TimeEntriesIn) -> TimeEntriesOut:
    # GET /team/{team_id}/time_entries  (la ruta del catalogo /time_entries no existe)
    params = query(start_date=args.start_date, end_date=args.end_date, assignee=args.assignee, space_id=args.space_id, folder_id=args.folder_id,
                   list_id=args.list_id, task_id=args.task_id, is_billable=args.is_billable,
                   include_task_tags=args.include_task_tags or None, include_location_names=args.include_location_names or None)
    return TimeEntriesOut(time_entries=items(await get(ctx, f"{V2}/team/{args.workspace_id}/time_entries", params), "data"))


class TimeEntryIn(WorkspaceIn):
    time_entry_id: PathId = Field(description="Id of the time entry (timer id), for example '1963465985517105840'. Get it from clickup.time_entries.list")


class TimeEntryDetailIn(TimeEntryIn):
    include_task_tags: bool = Field(default=False, description="When true, the entry also lists the tags of its task (default false)")
    include_location_names: bool = Field(default=False, description="When true, the entry also includes the names of its list, folder and Space (default false)")


class TimeEntryOut(Out):
    time_entry: Optional[dict] = Field(default=None, description="The time entry: id, task, user, billable, start, end, duration in milliseconds, description, tags and source")


@function(
    id="clickup.time_entries.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns one ClickUp time entry: id, the task it was logged on, the user, whether it is billable, start and end time, duration in milliseconds, "
        "description, tags, source and the time it was last changed. Use it when the user asks about one specific entry whose id is known. Requires workspace_id "
        "and time_entry_id (see clickup.time_entries.list). Set include_task_tags or include_location_names for extra context. Read-only. It does not list a "
        "range of entries (use clickup.time_entries.list), does not return its change log (use clickup.time_entries.get_history) and does not start or stop timers."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "time_entry_id": "1963465985517105840"}, "output": {"time_entry": {
        "id": "1963465985517105840", "duration": "3600000", "billable": False}}}],
)
async def time_entries_get(ctx: Context, args: TimeEntryDetailIn) -> TimeEntryOut:
    params = query(include_task_tags=args.include_task_tags or None, include_location_names=args.include_location_names or None)
    body = await get(ctx, f"{V2}/team/{args.workspace_id}/time_entries/{args.time_entry_id}", params)
    return TimeEntryOut(time_entry=_first(unwrap(body)))


class TimeHistoryOut(Out):
    changes: list[dict] = Field(default_factory=list, description="Change log of the entry, each change with its id, date, the user and the before and after values")


@function(
    id="clickup.time_entries.get_history", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the change history of one ClickUp time entry: each edit with its id, the date, the user who made it and the values before and after (duration, "
        "start, end, description, billable, tags). Use it when the user asks who changed a time entry, or what it said before. Requires workspace_id and "
        "time_entry_id (see clickup.time_entries.list). Read-only. It does not return the current entry (use clickup.time_entries.get), does not list the entries "
        "of a range (use clickup.time_entries.list) and does not undo changes."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001", "time_entry_id": "1963465985517105840"}, "output": {"changes": [
        {"id": "h1", "date": "1767225600000", "field": "duration", "before": "1800000", "after": "3600000"}]}}],
)
async def time_entries_get_history(ctx: Context, args: TimeEntryIn) -> TimeHistoryOut:
    data = unwrap(await get(ctx, f"{V2}/team/{args.workspace_id}/time_entries/{args.time_entry_id}/history"))
    return TimeHistoryOut(changes=[c for c in data if isinstance(c, dict)] if isinstance(data, list) else [])


class RunningTimerIn(WorkspaceIn):
    assignee: Optional[int] = Field(default=None, description="User id whose running timer is wanted; only Workspace owners and admins can read another user's timer. Empty means the connected user")


class RunningTimerOut(Out):
    running: bool = Field(default=False, description="True when the user has a timer running right now")
    timer: Optional[dict] = Field(default=None, description="The running time entry: id, task, start, description, tags and a negative duration; empty when no timer is running")


@function(
    id="clickup.timer.get_running", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the timer that is running right now for the connected ClickUp user: the time entry id, the task it is tracking, when it started, its description "
        "and tags. Use it when the user asks 'am I tracking time?' or 'what am I working on?'. Requires workspace_id (see clickup.workspaces.list); owners and "
        "admins may pass assignee to read another user's timer. Read-only. When nothing is running it answers running false with no timer. It does not start or "
        "stop timers and does not list past entries (use clickup.time_entries.list)."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"running": True, "timer": {
        "id": "te9", "task": {"id": "86abc12", "name": "Fix bug"}, "duration": -1767225600000}}}],
)
async def timer_get_running(ctx: Context, args: RunningTimerIn) -> RunningTimerOut:
    # GET /team/{team_id}/time_entries/current  (la ruta del catalogo /user/time_entries/running no existe)
    timer = _first(unwrap(await get(ctx, f"{V2}/team/{args.workspace_id}/time_entries/current", query(assignee=args.assignee))))
    return RunningTimerOut(running=bool(timer and timer.get("id")), timer=timer if timer and timer.get("id") else None)


class TimeTagsOut(Out):
    tags: list[dict] = Field(default_factory=list, description="Tags used on time entries, each with name, creator, foreground color (tag_fg) and background color (tag_bg)")


@function(
    id="clickup.time_entries.list_tags", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists all the tags that have been used on time entries in a ClickUp Workspace: name, creator and colors of each. Use it when the user asks which time "
        "tags exist or needs the exact tag name before reading entries. Requires workspace_id (see clickup.workspaces.list). Read-only. These are tags of time "
        "entries, not task tags: for task tags use clickup.tags.list. It does not count how many entries use each tag, does not list the entries "
        "(use clickup.time_entries.list) and does not create or rename tags."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"tags": [{"name": "billable", "creator": 12, "tag_fg": "#fff", "tag_bg": "#0a0"}]}}],
)
async def time_entries_list_tags(ctx: Context, args: WorkspaceIn) -> TimeTagsOut:
    data = unwrap(await get(ctx, f"{V2}/team/{args.workspace_id}/time_entries/tags"))
    return TimeTagsOut(tags=[t for t in data if isinstance(t, dict)] if isinstance(data, list) else [])


# --- Metas -----------------------------------------------------------------------------------------

class GoalsIn(WorkspaceIn):
    include_completed: bool = Field(default=False, description="When true, completed goals are included too (default false)")


class GoalsOut(Out):
    goals: list[dict] = Field(default_factory=list, description="Goals, each with id, name, owners, due date, percent_completed, key_result_count and color")
    folders: list[dict] = Field(default_factory=list, description="Goal folders that group goals, each with id, name and goal_count")


@function(
    id="clickup.goals.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the goals of a ClickUp Workspace: for each goal its id, name, description, owners, start and due dates, percent completed, number of key results "
        "(targets) and whether it is private or archived, plus the goal folders that group them. Use it when the user asks about OKRs, goals or progress. "
        "Requires workspace_id (see clickup.workspaces.list); set include_completed to also see finished goals. Read-only and not paginated. Goals are not "
        "available on every ClickUp plan. For one goal with its key results use clickup.goals.get."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"goals": [
        {"id": "g1", "name": "Q1 OKRs", "percent_completed": 50, "key_result_count": 3}], "folders": []}}],
)
async def goals_list(ctx: Context, args: GoalsIn) -> GoalsOut:
    body = await get(ctx, f"{V2}/team/{args.workspace_id}/goal", query(include_completed=args.include_completed or None))
    return GoalsOut(goals=items(body, "goals"), folders=items(body, "folders"))


class GoalIn(BaseModel):
    goal_id: PathId = Field(description="ClickUp goal id, a UUID such as 'e53a033c-900e-462d-a849-4a216b06d930'. Get it from clickup.goals.list")


class GoalOut(Out):
    goal: Optional[dict] = Field(default=None, description="The goal: id, name, description, owners, dates, percent_completed, key_results and history")


@function(
    id="clickup.goals.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the details of one ClickUp goal: id, name, description, color, owners, members, start and due dates, privacy, percent completed and its key "
        "results (targets) with their progress. Use it when the user asks how a specific goal or OKR is going. Requires goal_id (see clickup.goals.list). "
        "Read-only. Goals are not available on every ClickUp plan. It does not list all goals (use clickup.goals.list) and does not create or update goals or "
        "key results."
    ),
    examples=[{"name": "default", "input": {"goal_id": "e53a033c-900e-462d-a849-4a216b06d930"}, "output": {"goal": {
        "id": "e53a033c-900e-462d-a849-4a216b06d930", "name": "Q1 OKRs", "percent_completed": 50, "key_results": []}}}],
)
async def goals_get(ctx: Context, args: GoalIn) -> GoalOut:
    body = obj(await get(ctx, f"{V2}/goal/{args.goal_id}"))
    return GoalOut(goal=obj(body.get("goal")) or body)
