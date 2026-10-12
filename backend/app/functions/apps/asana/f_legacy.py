"""Asana: las 22 herramientas viejas migradas al estandar nuevo (Tarea 9). Las de escritura se simulan por defecto en /debug.

Rutas, parametros y permisos verificados en el OpenAPI oficial de Asana (github.com/Asana/openapi, 2026-10-08). El catalogo
ATENCION/tareas/asana.md difiere de la API real en lo siguiente:
- asana.tasks.create: `workspace_gid` ya no se manda si hay `projects`; Asana exige workspace, projects o parent. La descripcion de una
  tarea se llama `notes` en la API (el catalogo la llama description).
- asana.tasks.update / update_description: igual, el cuerpo usa `notes`. Asignar NO tiene endpoint propio: es PUT /tasks/{gid} con `assignee`.
- asana.tasks.duplicate: `include` es una cadena separada por comas (assignee, attachments, dates, dependencies, followers, notes, parent,
  projects, subtasks, tags), no un booleano `include_subtasks`; la respuesta es un JOB asincrono (`asana.jobs.get`), no la tarea nueva.
- asana.tasks.add_tag: la ruta es POST /tasks/{gid}/addTag con `{"data": {"tag": gid}}` y responde `{"data": {}}`.
- asana.tasks.list / list_completed / list_incomplete: GET /tasks exige project, section o assignee+workspace; no hay filtro del servidor
  para «completadas». list_incomplete usa `completed_since=now` (el servidor solo devuelve las incompletas); list_completed pide
  completed + completed_at y descarta las incompletas en la pagina.
- asana.stories.create_task_story: `created_by` NO se puede enviar (el comentario siempre lo firma la cuenta conectada); el cuerpo lleva
  `text`. Usa los scopes stories:read / stories:write, no tasks:*.
- asana.teams.list_workspace: la respuesta solo trae gid y name (no existe `member_count`).
- asana.team_memberships.list: GET /team_memberships exige team, o user + workspace; el campo es is_admin, no `role`.
- asana.project_memberships.list_project: la ruta real es /projects/{gid}/project_memberships (no /memberships); es el mismo dato que
  asana.project_memberships.list y se conserva por la herramienta vieja, con el filtro opcional `user`.
- asana.workspaces.get_events / asana.events.list: GET /workspaces/{gid}/events y GET /events?resource=<gid> (no /{resource_path}/events).
  Aceptan `sync` (token) pero NO `limit`; la primera llamada sin token responde 412 con un token nuevo en el cuerpo y se devuelve como
  `sync_reset=true` con la lista vacia. Un solo token trae hasta 100 (recurso) o 1000 (workspace) eventos.
Las descripciones y los Field(description=...) estan en INGLES a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.asana._common import BASE_URL, PageIn, build_page, get_body, nested_gid, page_model, page_params, send_body
from app.functions.apps.asana.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.apps.asana.functions import (
    TASK_OPT_FIELDS, ProjectMembershipList, StoryItem, StoryList, TagList, TaskList, TeamList, TeamMembershipList,
    _project_membership_list, _story_item, _story_list, _tag_list, _task_list, _team_list, _team_membership_list,
)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

STORY_FIELDS = "text,type,created_at,created_by.name"


def _opt(*names: str) -> str:
    return ",".join(names)


# --- asana.users.list -----------------------------------------------------------------------------

class UsersListIn(PageIn):
    workspace_gid: Optional[str] = Field(default=None, description="Gid of a workspace or organization to list users of; empty lists users of every workspace the account can see")
    team_gid: Optional[str] = Field(default=None, description="Gid of a team; keeps only the members of that team")


class UserItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the user")
    name: Optional[str] = Field(default=None, description="Full name of the user")
    email: Optional[str] = Field(default=None, description="Email address of the user, when Asana exposes it")


UsersOut = page_model(UserItem, "Users")


@function(
    id="asana.users.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["users:read"],
    description=(
        "Lists the people of an Asana workspace or organization: each user reports its gid, full name and email address. Use it when the user asks "
        "who is in the Asana workspace, or needs a person's gid to assign a task, add a collaborator or filter by assignee. workspace_gid and "
        "team_gid narrow the result; without them the users of every workspace the connected account can see are returned, sorted by id. Results "
        "are paginated with a limit of 1 to 100 and an offset token. Read-only. It does not invite or remove users and it does not return their "
        "tasks; to read one user use asana.users.get_workspace."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000000001", "name": "Ana Perez", "email": "ana@empresa.test"}], "has_more": False, "next_offset": None}}],
)
async def users_list(ctx: Context, args: UsersListIn) -> UsersOut:
    body = await get_body(ctx, "/users", params=page_params(args.limit, args.offset, "name,email", workspace=args.workspace_gid, team=args.team_gid))
    return build_page(UsersOut, body, lambda i: UserItem(gid=str(i["gid"]), name=i.get("name"), email=i.get("email")))


# --- asana.tasks.list / list_completed / list_incomplete -----------------------------------------------

class TaskFilterIn(PageIn):
    workspace_gid: Optional[str] = Field(default=None, description="Gid of the workspace to filter tasks on; it must be used together with assignee")
    assignee: Optional[str] = Field(default=None, description="User whose tasks to list: 'me', an email or a user gid; it must be used together with workspace_gid")
    project: Optional[str] = Field(default=None, description="Gid of the project whose tasks to list")
    section: Optional[str] = Field(default=None, description="Gid of the section whose tasks to list")

    @model_validator(mode="after")
    def _needs_scope(self) -> "TaskFilterIn":
        if not (self.project or self.section or (self.assignee and self.workspace_gid)):
            raise ValueError("Provide project, section, or assignee together with workspace_gid so Asana knows which tasks to list")
        return self

    def base_params(self) -> dict:
        return {"workspace": self.workspace_gid, "assignee": self.assignee, "project": self.project, "section": self.section}


class TasksListIn(TaskFilterIn):
    completed_since: Optional[str] = Field(default=None, description="ISO 8601 date-time; only incomplete tasks or tasks completed since then are returned")
    modified_since: Optional[str] = Field(default=None, description="ISO 8601 date-time; only tasks modified since then are returned")


@function(
    id="asana.tasks.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists Asana tasks that match a filter: each task reports its gid, name, assignee gid, due date and whether it is completed. Use it when the "
        "user asks for the tasks of a project or section, or for the tasks assigned to someone in a workspace. Asana requires a scope for the "
        "list: project, section, or assignee together with workspace_gid. completed_since and modified_since (ISO 8601) narrow it and results are "
        "paginated with a limit of 1 to 100. Read-only. It does not search by text (use asana.tasks.search), and for only done or only open "
        "tasks use asana.tasks.list_completed or asana.tasks.list_incomplete."
    ),
    examples=[{"name": "default", "input": {"project": "1200000000000100", "limit": 50}, "output": {
        "items": [{"gid": "1200000000000110", "name": "Rediseno portada", "assignee": "1200000000000001", "due_on": "2026-03-01", "completed": False}],
        "has_more": False, "next_offset": None}}],
)
async def tasks_list(ctx: Context, args: TasksListIn) -> TaskList:
    body = await get_body(ctx, "/tasks", params=page_params(args.limit, args.offset, TASK_OPT_FIELDS, **args.base_params(),
                                                            completed_since=args.completed_since, modified_since=args.modified_since))
    return _task_list(body)


class CompletedTaskItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the completed task")
    name: str = Field(description="Name of the task")
    completed_at: Optional[str] = Field(default=None, description="UTC date and time when the task was completed")
    assignee: Optional[str] = Field(default=None, description="Gid of the user assigned to the task, when there is one")


CompletedTasksOut = page_model(CompletedTaskItem, "Completed tasks")


class CompletedTasksIn(TaskFilterIn):
    completed_since: Optional[str] = Field(default=None, description="ISO 8601 date-time; keeps only tasks completed at or after this moment")


@function(
    id="asana.tasks.list_completed", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the completed Asana tasks of a project, section or assignee: each task reports its gid, name, the moment it was completed and the "
        "assignee. Use it when the user asks what has been finished, what was done last week or for a progress report. It needs the same scope as "
        "asana.tasks.list (project, section, or assignee with workspace_gid) and completed_since keeps only tasks completed after that ISO 8601 "
        "moment. Asana has no server-side filter for done tasks, so each page is filtered after reading it: a page can hold fewer items than "
        "limit, so keep following next_offset while has_more is true. Read-only; it does not reopen tasks."
    ),
    examples=[{"name": "default", "input": {"project": "1200000000000100", "completed_since": "2026-10-01T00:00:00Z"}, "output": {
        "items": [{"gid": "1200000000000111", "name": "Publicar sitio", "completed_at": "2026-10-03T15:00:00.000Z", "assignee": "1200000000000001"}],
        "has_more": False, "next_offset": None}}],
)
async def tasks_list_completed(ctx: Context, args: CompletedTasksIn) -> CompletedTasksOut:
    body = await get_body(ctx, "/tasks", params=page_params(args.limit, args.offset, "name,completed,completed_at,assignee.name",
                                                            **args.base_params(), completed_since=args.completed_since))
    done = [i for i in body.get("data") or [] if i.get("completed")]
    return build_page(CompletedTasksOut, {**body, "data": done}, lambda i: CompletedTaskItem(
        gid=str(i["gid"]), name=i.get("name", ""), completed_at=i.get("completed_at"), assignee=nested_gid(i, "assignee")))


@function(
    id="asana.tasks.list_incomplete", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the incomplete (still open) Asana tasks of a project, section or assignee: each task reports its gid, name, assignee, due date and "
        "completed flag. Use it when the user asks what is pending, what is left to do or what someone has on their plate. It needs the same scope "
        "as asana.tasks.list (project, section, or assignee together with workspace_gid) and asks Asana to return only tasks that are not "
        "completed. Results are paginated with a limit of 1 to 100. Read-only. It does not mark anything as done (use asana.tasks.update) and "
        "for the finished ones use asana.tasks.list_completed."
    ),
    examples=[{"name": "default", "input": {"assignee": "me", "workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000000110", "name": "Rediseno portada", "assignee": "1200000000000001", "due_on": "2026-03-01", "completed": False}],
        "has_more": False, "next_offset": None}}],
)
async def tasks_list_incomplete(ctx: Context, args: TaskFilterIn) -> TaskList:
    body = await get_body(ctx, "/tasks", params=page_params(args.limit, args.offset, TASK_OPT_FIELDS, **args.base_params(), completed_since="now"))
    return _task_list({**body, "data": [i for i in body.get("data") or [] if not i.get("completed")]})


# --- asana.tasks.get ------------------------------------------------------------------------------

class TaskGetIn(BaseModel):
    task_gid: str = Field(description="Gid of the task to fetch; to find a task by its name use asana.tasks.search first")


class TaskDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the task")
    name: str = Field(description="Name of the task")
    description: Optional[str] = Field(default=None, description="Plain text notes (description) of the task")
    assignee: Optional[str] = Field(default=None, description="Gid of the user assigned to the task, when there is one")
    due_on: Optional[str] = Field(default=None, description="Due date of the task in YYYY-MM-DD, when one is set")
    completed: bool = Field(default=False, description="Whether the task has been marked as completed")
    projects: list[str] = Field(default_factory=list, description="Gids of the projects the task belongs to")
    tags: list[str] = Field(default_factory=list, description="Gids of the tags attached to the task")
    dependencies: list[str] = Field(default_factory=list, description="Gids of the tasks that must be finished before this one")
    permalink_url: Optional[str] = Field(default=None, description="URL to open the task in the Asana web app")


def _gids(raw: dict, key: str) -> list[str]:
    return [str(i["gid"]) for i in raw.get(key) or [] if isinstance(i, dict) and i.get("gid")]


@function(
    id="asana.tasks.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Returns the full details of one Asana task: its gid, name, description (notes), assignee, due date, completed flag, the projects it "
        "belongs to, its tags, the tasks it depends on and the link to open it. Use it when the user asks about a specific task, for example 'what "
        "is the status of the Redesign task?', once the gid is known. It requires only the task gid; if the user gave a name, find the gid first "
        "with asana.tasks.search. Read-only. It does not list subtasks or comments (use asana.tasks.list_subtasks and "
        "asana.stories.list_task_stories) and it does not change the task."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500"}, "output": {
        "gid": "1200000000000500", "name": "Preparar propuesta", "description": "Incluir precios", "assignee": "1200000000000001",
        "due_on": "2026-02-01", "completed": False, "projects": ["1200000000000100"], "tags": ["1200000000000900"], "dependencies": [],
        "permalink_url": "https://app.asana.com/0/1200000000000100/1200000000000500"}}],
)
async def tasks_get(ctx: Context, args: TaskGetIn) -> TaskDetail:
    body = await get_body(ctx, f"/tasks/{args.task_gid}", params={"opt_fields": _opt(
        "name", "notes", "assignee.name", "due_on", "completed", "projects.name", "tags.name", "dependencies.name", "permalink_url")})
    d = body.get("data") or {}
    return TaskDetail(gid=str(d["gid"]), name=d.get("name", ""), description=d.get("notes"), assignee=nested_gid(d, "assignee"), due_on=d.get("due_on"),
                      completed=bool(d.get("completed")), projects=_gids(d, "projects"), tags=_gids(d, "tags"),
                      dependencies=_gids(d, "dependencies"), permalink_url=d.get("permalink_url"))


# --- asana.tasks.create / update / assign / update_description -----------------------------------------

class TaskWriteOut(BaseModel):
    gid: str = Field(description="Asana unique identifier of the task")
    name: str = Field(description="Name of the task after the change")
    description: Optional[str] = Field(default=None, description="Plain text notes (description) of the task after the change")
    assignee: Optional[str] = Field(default=None, description="Gid of the user assigned to the task, when there is one")
    due_on: Optional[str] = Field(default=None, description="Due date of the task in YYYY-MM-DD, when one is set")
    completed: bool = Field(default=False, description="Whether the task is marked as completed")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the task was created")
    permalink_url: Optional[str] = Field(default=None, description="URL to open the task in the Asana web app")


TASK_WRITE_FIELDS = _opt("name", "notes", "assignee.name", "due_on", "completed", "created_at", "permalink_url")


def _task_write(body: dict) -> TaskWriteOut:
    d = body.get("data") or {}
    return TaskWriteOut(gid=str(d["gid"]), name=d.get("name", ""), description=d.get("notes"), assignee=nested_gid(d, "assignee"),
                        due_on=d.get("due_on"), completed=bool(d.get("completed")), created_at=d.get("created_at"), permalink_url=d.get("permalink_url"))


class TaskCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=1024, description="Name of the new task, for example 'Prepare quote for ACME'")
    workspace_gid: Optional[str] = Field(default=None, description="Gid of the workspace to create the task in; needed only when projects is empty")
    projects: list[str] = Field(default_factory=list, description="Gids of the projects to add the new task to; the workspace is inferred from them")
    assignee: Optional[str] = Field(default=None, description="User to assign the task to: 'me', an email or a user gid")
    due_on: Optional[str] = Field(default=None, description="Due date of the task in YYYY-MM-DD")
    notes: Optional[str] = Field(default=None, description="Plain text description of the task")

    @model_validator(mode="after")
    def _needs_container(self) -> "TaskCreateIn":
        if not (self.workspace_gid or self.projects):
            raise ValueError("Provide workspace_gid or at least one project gid: Asana needs to know where to create the task")
        return self


@function(
    id="asana.tasks.create", version=1, verb=Verb.create, upstream_api="1.0", scopes=["tasks:write"],
    description=(
        "Creates a new task in Asana and returns it with its gid, name, assignee, due date and link. Use it when the user asks to add a task, to-do "
        "or action item, for example 'create a task to prepare the quote in the Sales project, due Friday'. The name is required and Asana also "
        "needs a place for the task: either one or more project gids (the workspace is inferred) or the workspace gid. Optionally set the assignee "
        "(me, an email or a gid), the due date (YYYY-MM-DD) and a description. It creates one task only; it does not create subtasks, "
        "comments or tags (see asana.tasks.add_tag and asana.stories.create_task_story) and it does not check for duplicates."
    ),
    examples=[{"name": "default", "input": {"name": "Preparar propuesta", "projects": ["1200000000000100"], "due_on": "2026-02-01"}, "output": {
        "gid": "1200000000000500", "name": "Preparar propuesta", "description": None, "assignee": None, "due_on": "2026-02-01",
        "completed": False, "created_at": "2026-01-20T10:00:00.000Z", "permalink_url": "https://app.asana.com/0/1200000000000100/1200000000000500"}}],
)
async def tasks_create(ctx: Context, args: TaskCreateIn) -> TaskWriteOut:
    payload: dict[str, Any] = {"name": args.name}
    if args.projects:
        payload["projects"] = args.projects
    elif args.workspace_gid:
        payload["workspace"] = args.workspace_gid
    for key, value in (("assignee", args.assignee), ("due_on", args.due_on), ("notes", args.notes)):
        if value:
            payload[key] = value
    return _task_write(await send_body(ctx, "POST", "/tasks", payload, params={"opt_fields": TASK_WRITE_FIELDS}))


class TaskUpdateIn(BaseModel):
    task_gid: str = Field(description="Gid of the task to change")
    name: Optional[str] = Field(default=None, min_length=1, max_length=1024, description="New name for the task")
    description: Optional[str] = Field(default=None, description="New plain text description (notes) for the task; replaces the previous one")
    completed: Optional[bool] = Field(default=None, description="True marks the task as completed, false reopens it")
    due_on: Optional[str] = Field(default=None, description="New due date in YYYY-MM-DD")
    assignee: Optional[str] = Field(default=None, description="User to assign the task to: 'me', an email or a user gid")

    @model_validator(mode="after")
    def _needs_change(self) -> "TaskUpdateIn":
        if all(v is None for v in (self.name, self.description, self.completed, self.due_on, self.assignee)):
            raise ValueError("Provide at least one field to change: name, description, completed, due_on or assignee")
        return self


@function(
    id="asana.tasks.update", version=1, verb=Verb.update, upstream_api="1.0", scopes=["tasks:write"],
    description=(
        "Changes fields of an existing Asana task and returns it: the name, the description, the completed flag (true to close it, false to reopen "
        "it), the due date and the assignee. Only the fields provided are changed; the others stay as they are. Use it when the user asks to rename a "
        "task, mark it as done, reopen it, move its deadline or reassign it. It requires the task gid and at least one field; find the gid with "
        "asana.tasks.search if only the name is known. It does not delete the task, change its projects or tags, or add comments; for a "
        "notified reassignment prefer asana.tasks.assign."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "completed": True}, "output": {
        "gid": "1200000000000500", "name": "Preparar propuesta", "description": None, "assignee": "1200000000000001", "due_on": "2026-02-01",
        "completed": True, "created_at": "2026-01-20T10:00:00.000Z", "permalink_url": "https://app.asana.com/0/1200000000000100/1200000000000500"}}],
)
async def tasks_update(ctx: Context, args: TaskUpdateIn) -> TaskWriteOut:
    payload: dict[str, Any] = {k: v for k, v in (("name", args.name), ("notes", args.description), ("completed", args.completed),
                                                 ("due_on", args.due_on), ("assignee", args.assignee)) if v is not None}
    return _task_write(await send_body(ctx, "PUT", f"/tasks/{args.task_gid}", payload, params={"opt_fields": TASK_WRITE_FIELDS}))


class TaskAssignIn(BaseModel):
    task_gid: str = Field(description="Gid of the task to assign")
    assignee: str = Field(min_length=1, description="User to assign the task to: 'me', an email or a user gid")


@function(
    id="asana.tasks.assign", version=1, verb=Verb.update, exits_outside=True, upstream_api="1.0", scopes=["tasks:write"],
    description=(
        "Assigns an Asana task to a person, replacing the previous assignee, and returns the task with its new assignee. Asana notifies the new "
        "assignee, so this reaches someone outside the conversation: confirm before running it. Use it when the user asks to give a task to "
        "someone, for example 'assign the quote task to Ana'. It requires the task gid and the assignee (me, an email or a user gid); find the "
        "task with asana.tasks.search and the person with asana.users.list. It does not unassign tasks, does not change other fields (use "
        "asana.tasks.update) and does not add the person as a project member."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "assignee": "ana@empresa.test"}, "output": {
        "gid": "1200000000000500", "name": "Preparar propuesta", "description": None, "assignee": "1200000000000001", "due_on": "2026-02-01",
        "completed": False, "created_at": "2026-01-20T10:00:00.000Z", "permalink_url": "https://app.asana.com/0/1200000000000100/1200000000000500"}}],
)
async def tasks_assign(ctx: Context, args: TaskAssignIn) -> TaskWriteOut:
    return _task_write(await send_body(ctx, "PUT", f"/tasks/{args.task_gid}", {"assignee": args.assignee}, params={"opt_fields": TASK_WRITE_FIELDS}))


class TaskDescriptionIn(BaseModel):
    task_gid: str = Field(description="Gid of the task whose description should be replaced")
    description: str = Field(description="New plain text description (notes) of the task; it replaces the previous description completely")


@function(
    id="asana.tasks.update_description", version=1, verb=Verb.update, upstream_api="1.0", scopes=["tasks:write"],
    description=(
        "Replaces the description (the notes field) of an Asana task with a new plain text and returns the task. Use it when the user asks to write, "
        "rewrite or clear the description of a task, for example 'put the meeting agenda in the task description'. It requires the task gid and the "
        "new text, which overwrites what was there, so read the current one with asana.tasks.get first when it must be preserved or appended. "
        "Rich text formatting is not supported by this function. It does not change the name, the assignee or the due date (use "
        "asana.tasks.update) and it does not add a comment (use asana.stories.create_task_story)."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "description": "Agenda: 1. Precios 2. Plazos"}, "output": {
        "gid": "1200000000000500", "name": "Preparar propuesta", "description": "Agenda: 1. Precios 2. Plazos", "assignee": None, "due_on": None,
        "completed": False, "created_at": "2026-01-20T10:00:00.000Z", "permalink_url": "https://app.asana.com/0/1200000000000100/1200000000000500"}}],
)
async def tasks_update_description(ctx: Context, args: TaskDescriptionIn) -> TaskWriteOut:
    return _task_write(await send_body(ctx, "PUT", f"/tasks/{args.task_gid}", {"notes": args.description}, params={"opt_fields": TASK_WRITE_FIELDS}))


# --- asana.tasks.duplicate ------------------------------------------------------------------------

class TaskDuplicateIn(BaseModel):
    task_gid: str = Field(description="Gid of the task to copy")
    name: Optional[str] = Field(default=None, min_length=1, max_length=1024, description="Name for the copy; empty keeps the original name")
    include: str = Field(default="notes,assignee,subtasks,attachments,tags,followers,projects,dates,dependencies",
                         description="Comma separated parts to copy: assignee, attachments, dates, dependencies, followers, notes, parent, projects, subtasks, tags")


class TaskDuplicateOut(BaseModel):
    job_gid: str = Field(description="Gid of the asynchronous job that makes the copy; follow it with asana.jobs.get")
    status: Optional[str] = Field(default=None, description="State of the job: not_started, in_progress, succeeded or failed")
    new_task: Optional[str] = Field(default=None, description="Gid of the new task, available once the job has produced it")
    new_task_name: Optional[str] = Field(default=None, description="Name of the new task, available once the job has produced it")


@function(
    id="asana.tasks.duplicate", version=1, verb=Verb.create, upstream_api="1.0", scopes=["tasks:write"],
    description=(
        "Makes a copy of an Asana task and returns the asynchronous job that builds it, with the state and, when ready, the gid and name of the new "
        "task. Use it when the user asks to duplicate or clone a task, for example to reuse a checklist. It requires the task gid; name sets the "
        "name of the copy and include picks what to copy (assignee, attachments, dates, dependencies, followers, notes, parent, projects, "
        "subtasks and tags; by default everything except the parent). Asana copies in the background, so check the job with asana.jobs.get if "
        "new_task is empty. It does not move the original and it does not copy comments."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "name": "Propuesta (copia)"}, "output": {
        "job_gid": "1200000000008000", "status": "in_progress", "new_task": "1200000000000501", "new_task_name": "Propuesta (copia)"}}],
)
async def tasks_duplicate(ctx: Context, args: TaskDuplicateIn) -> TaskDuplicateOut:
    payload = {"include": args.include, **({"name": args.name} if args.name else {})}
    body = await send_body(ctx, "POST", f"/tasks/{args.task_gid}/duplicate", payload, params={"opt_fields": "status,new_task.name"})
    d = body.get("data") or {}
    new_task = d.get("new_task") or {}
    return TaskDuplicateOut(job_gid=str(d["gid"]), status=d.get("status"), new_task=nested_gid(d, "new_task"), new_task_name=new_task.get("name"))


# --- asana.tasks.add_tag / list_tag_tasks ------------------------------------------------------------

class TaskAddTagIn(BaseModel):
    task_gid: str = Field(description="Gid of the task to label")
    tag_gid: str = Field(description="Gid of the existing tag to attach to the task; find it with asana.tags.list")


class TaskTagOut(BaseModel):
    task_gid: str = Field(description="Gid of the task that was labeled")
    tag_gid: str = Field(description="Gid of the tag that was attached to the task")
    added: bool = Field(description="True when Asana accepted the request and the tag is now on the task")


@function(
    id="asana.tasks.add_tag", version=1, verb=Verb.update, upstream_api="1.0", scopes=["tasks:write"],
    description=(
        "Attaches an existing tag (label) to an Asana task, for example to mark it as urgent. Use it when the user asks to label, tag or categorize a "
        "task. It requires the gid of the task and the gid of the tag, which must already exist in the same workspace: find it with asana.tags.list "
        "and the task with asana.tasks.search. Adding a tag that is already on the task is harmless. It returns a confirmation with both gids. "
        "It does not create tags, does not remove them and does not change any other field of the task. The change is internal to Asana and "
        "reversible."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "tag_gid": "1200000000000900"}, "output": {
        "task_gid": "1200000000000500", "tag_gid": "1200000000000900", "added": True}}],
)
async def tasks_add_tag(ctx: Context, args: TaskAddTagIn) -> TaskTagOut:
    await send_body(ctx, "POST", f"/tasks/{args.task_gid}/addTag", {"tag": args.tag_gid})
    return TaskTagOut(task_gid=args.task_gid, tag_gid=args.tag_gid, added=True)


class TagTasksIn(PageIn):
    tag_gid: str = Field(description="Gid of the tag whose tasks should be listed")


@function(
    id="asana.tasks.list_tag_tasks", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the Asana tasks that carry a given tag: each task reports its gid, name, assignee gid, due date and completed flag. Use it when the user "
        "asks for everything labeled 'Urgent' or any other tag across projects. It requires the tag gid (see asana.tags.list) and results are "
        "paginated with a limit of 1 to 100 and an offset token. Read-only. It does not attach or remove tags (use asana.tasks.add_tag), it "
        "does not filter by project and it returns open and completed tasks together."
    ),
    examples=[{"name": "default", "input": {"tag_gid": "1200000000000900"}, "output": {
        "items": [{"gid": "1200000000000110", "name": "Rediseno portada", "assignee": "1200000000000001", "due_on": "2026-03-01", "completed": False}],
        "has_more": False, "next_offset": None}}],
)
async def tasks_list_tag_tasks(ctx: Context, args: TagTasksIn) -> TaskList:
    return _task_list(await get_body(ctx, f"/tags/{args.tag_gid}/tasks", params=page_params(args.limit, args.offset, TASK_OPT_FIELDS)))


# --- asana.projects.list / get --------------------------------------------------------------------

class ProjectsListIn(PageIn):
    workspace_gid: Optional[str] = Field(default=None, description="Gid of the workspace or organization to list projects of; strongly recommended for large domains")
    team_gid: Optional[str] = Field(default=None, description="Gid of a team; keeps only the projects of that team")
    archived: Optional[bool] = Field(default=None, description="True returns only archived projects, false only active ones; empty returns both")


class ProjectListItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project")
    name: str = Field(description="Name of the project")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the project, when there is one")
    due_on: Optional[str] = Field(default=None, description="Due date of the project in YYYY-MM-DD, when one is set")


ProjectsOut = page_model(ProjectListItem, "Projects")


@function(
    id="asana.projects.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Lists the Asana projects visible to the connected account: each project reports its gid, name, owner gid and due date. Use it when the user "
        "asks which projects exist, wants to pick one by name, or needs a project gid for another function. Filter by workspace_gid or team_gid "
        "(recommended in big organizations, where an unfiltered call can time out) and by archived. Results are paginated with a limit of 1 to 100 "
        "and an offset token. Read-only. It does not create or archive projects, and it does not search by text (use asana.projects.search); for "
        "one project in detail use asana.projects.get."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "archived": False}, "output": {
        "items": [{"gid": "1200000000000100", "name": "Web 2026", "owner": "1200000000000001", "due_on": "2026-12-31"}],
        "has_more": False, "next_offset": None}}],
)
async def projects_list(ctx: Context, args: ProjectsListIn) -> ProjectsOut:
    params = page_params(args.limit, args.offset, "name,owner.name,due_on", workspace=args.workspace_gid, team=args.team_gid)
    if args.archived is not None:
        params["archived"] = str(args.archived).lower()
    body = await get_body(ctx, "/projects", params=params)
    return build_page(ProjectsOut, body, lambda i: ProjectListItem(gid=str(i["gid"]), name=i.get("name", ""), owner=nested_gid(i, "owner"), due_on=i.get("due_on")))


class ProjectGetIn(BaseModel):
    project_gid: str = Field(description="Gid of the project to fetch; to find a project by name use asana.projects.search first")


class ProjectCustomField(BaseModel):
    gid: str = Field(description="Asana unique identifier of the custom field")
    name: Optional[str] = Field(default=None, description="Name of the custom field")
    display_value: Optional[str] = Field(default=None, description="Value of the custom field on this project, as text")


class ProjectDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project")
    name: str = Field(description="Name of the project")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the project, when there is one")
    due_on: Optional[str] = Field(default=None, description="Due date of the project in YYYY-MM-DD, when one is set")
    description: Optional[str] = Field(default=None, description="Plain text notes (description) of the project")
    archived: bool = Field(default=False, description="Whether the project is archived")
    members: list[str] = Field(default_factory=list, description="Gids of the users who are members of the project")
    custom_fields: list[ProjectCustomField] = Field(default_factory=list, description="Custom fields of the project with their current values")


@function(
    id="asana.projects.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Returns the summary of one Asana project: its gid, name, owner, due date, description (notes), whether it is archived, the gids of its "
        "members and its custom fields with their values. Use it when the user asks what a project is about, who is in it or how it is "
        "configured, once the gid is known. It requires only the project gid; if the user gave a name, find the gid first with "
        "asana.projects.search or asana.projects.list. Read-only. It does not list the tasks (use asana.tasks.list_project_tasks), the "
        "sections or the status updates, and it does not change the project."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100"}, "output": {
        "gid": "1200000000000100", "name": "Web 2026", "owner": "1200000000000001", "due_on": "2026-12-31", "description": "Rediseno del sitio",
        "archived": False, "members": ["1200000000000001"], "custom_fields": [{"gid": "1200000000000400", "name": "Priority", "display_value": "High"}]}}],
)
async def projects_get(ctx: Context, args: ProjectGetIn) -> ProjectDetail:
    body = await get_body(ctx, f"/projects/{args.project_gid}", params={"opt_fields": _opt(
        "name", "owner.name", "due_on", "notes", "archived", "members.name", "custom_fields.name", "custom_fields.display_value")})
    d = body.get("data") or {}
    return ProjectDetail(gid=str(d["gid"]), name=d.get("name", ""), owner=nested_gid(d, "owner"), due_on=d.get("due_on"), description=d.get("notes"),
                         archived=bool(d.get("archived")), members=_gids(d, "members"),
                         custom_fields=[ProjectCustomField(gid=str(f["gid"]), name=f.get("name"), display_value=f.get("display_value"))
                                        for f in d.get("custom_fields") or [] if isinstance(f, dict) and f.get("gid")])


# --- asana.tags.list ------------------------------------------------------------------------------

class TagsListIn(PageIn):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose tags should be listed")


@function(
    id="asana.tags.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tags:read"],
    description=(
        "Lists the tags (labels) of an Asana workspace: each tag reports its gid, name and color when one is set. Use it when the user asks which "
        "labels exist, or needs a tag gid before attaching it to a task with asana.tasks.add_tag or listing its tasks with "
        "asana.tasks.list_tag_tasks. It requires the workspace gid and results are paginated with a limit of 1 to 100 and an offset token. "
        "Read-only. It does not create, rename or delete tags and it does not show which tasks use each tag. It returns the same data as "
        "asana.tags.list_workspace_tags and is kept for the legacy tool that had this name."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000000900", "name": "Urgente", "color": "red"}], "has_more": False, "next_offset": None}}],
)
async def tags_list(ctx: Context, args: TagsListIn) -> TagList:
    return _tag_list(await get_body(ctx, "/tags", params=page_params(args.limit, args.offset, "name,color", workspace=args.workspace_gid)))


# --- asana.stories --------------------------------------------------------------------------------

class TaskStoriesIn(PageIn):
    task_gid: str = Field(description="Gid of the task whose comments and activity should be listed")
    only_comments: bool = Field(default=False, description="When true, returns only the comments people wrote and leaves out system activity such as due date changes")
    newest_first: bool = Field(default=False, description="When true, returns the most recent stories first instead of the oldest first")
    created_after: Optional[str] = Field(default=None, description="ISO 8601 date-time; only stories created after this moment are returned")


@function(
    id="asana.stories.list_task_stories", version=1, verb=Verb.read, upstream_api="1.0", scopes=["stories:read"],
    description=(
        "Lists the stories of an Asana task, that is its comments and its activity feed: each story reports its gid, its kind (comment or system), "
        "its text, the gid of the author and the creation time. Use it when the user asks what was said on a task, who commented, or what changed "
        "and when. It requires the task gid; only_comments leaves out system activity, newest_first reverses the order and created_after "
        "(ISO 8601) skips older entries. Results are paginated with a limit of 1 to 100. Read-only. It does not add comments (use "
        "asana.stories.create_task_story) and it does not read the task details (use asana.tasks.get)."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "only_comments": True}, "output": {
        "items": [{"gid": "1200000000000800", "type": "comment", "text": "Listo para revisar", "created_by": "1200000000000001",
                   "created_at": "2026-01-20T10:00:00.000Z"}], "has_more": False, "next_offset": None}}],
)
async def stories_list_task_stories(ctx: Context, args: TaskStoriesIn) -> StoryList:
    params = page_params(args.limit, args.offset, STORY_FIELDS, created_after=args.created_after)
    if args.only_comments:
        params["resource_subtype"] = "comment_added"
    if args.newest_first:
        params["sort_ascending"] = "false"
    return _story_list(await get_body(ctx, f"/tasks/{args.task_gid}/stories", params=params))


class TaskStoryCreateIn(BaseModel):
    task_gid: str = Field(description="Gid of the task to comment on")
    text: str = Field(min_length=1, description="Plain text of the comment; the comment is always signed by the connected Asana account")


@function(
    id="asana.stories.create_task_story", version=1, verb=Verb.create, exits_outside=True, upstream_api="1.0", scopes=["stories:write"],
    description=(
        "Posts a comment on an Asana task and returns it with its gid, text, author and time. Asana notifies the task's assignee and followers, so "
        "the comment reaches people outside the conversation: show the draft and confirm before running it. Use it when the user asks to comment, "
        "reply or leave a note on a task, for example 'tell the team the quote was sent'. It requires the task gid and the comment text; "
        "the author is always the connected account and cannot be chosen. Plain text only. It does not edit or delete comments and it does "
        "not change the task itself (use asana.tasks.update)."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "text": "Propuesta enviada al cliente"}, "output": {
        "gid": "1200000000000800", "type": "comment", "text": "Propuesta enviada al cliente", "created_by": "1200000000000001",
        "created_at": "2026-01-20T10:00:00.000Z"}}],
)
async def stories_create_task_story(ctx: Context, args: TaskStoryCreateIn) -> StoryItem:
    body = await send_body(ctx, "POST", f"/tasks/{args.task_gid}/stories", {"text": args.text}, params={"opt_fields": STORY_FIELDS})
    return _story_item(body.get("data") or {})


# --- asana.teams.list_workspace / team_memberships.list / project_memberships.list_project ---------

class TeamsWorkspaceIn(PageIn):
    workspace_gid: str = Field(description="Gid of the organization whose teams should be listed; workspaces that are not organizations have no teams")


@function(
    id="asana.teams.list_workspace", version=1, verb=Verb.read, upstream_api="1.0", scopes=["teams:read"],
    description=(
        "Lists the teams of an Asana organization: each team reports its gid, name and the organization it belongs to. Use it when the user asks "
        "which teams exist, or needs a team gid for asana.projects.list_team_projects, memberships or templates. It requires the organization gid "
        "(see asana.workspaces.list; personal workspaces without teams return an empty list) and results are paginated with a limit of 1 to "
        "100. Read-only. It returns only the teams the connected user can see. It does not return the members of each team (use "
        "asana.team_memberships.list_team) and it does not create teams."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000000800", "name": "Marketing", "organization": "1200000000000002"}], "has_more": False, "next_offset": None}}],
)
async def teams_list_workspace(ctx: Context, args: TeamsWorkspaceIn) -> TeamList:
    return _team_list(await get_body(ctx, f"/workspaces/{args.workspace_gid}/teams", params=page_params(args.limit, args.offset, "name,organization.name")))


class TeamMembershipsListIn(PageIn):
    team_gid: Optional[str] = Field(default=None, description="Gid of the team whose memberships should be listed")
    user_gid: Optional[str] = Field(default=None, description="User whose team memberships to list: 'me', an email or a gid; it must be used together with workspace_gid")
    workspace_gid: Optional[str] = Field(default=None, description="Gid of the workspace for the user filter; it must be used together with user_gid")

    @model_validator(mode="after")
    def _needs_filter(self) -> "TeamMembershipsListIn":
        if not (self.team_gid or (self.user_gid and self.workspace_gid)):
            raise ValueError("Provide team_gid, or user_gid together with workspace_gid, so Asana knows which memberships to list")
        return self


@function(
    id="asana.team_memberships.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["team_memberships:read"],
    description=(
        "Lists Asana team memberships, the records that connect people with teams: each one reports its gid, the user, the team and whether the user "
        "is a team admin. Use it when the user asks who belongs to a team or which teams a person is in. Asana needs a filter: team_gid to get the "
        "members of one team, or user_gid together with workspace_gid to get the teams of one person. Results are paginated with a limit of 1 to "
        "100. Read-only. It does not add or remove members; the same data is also available per team with asana.team_memberships.list_team and "
        "per user with asana.team_memberships.list_user."
    ),
    examples=[{"name": "default", "input": {"team_gid": "1200000000000800"}, "output": {
        "items": [{"gid": "1200000000003500", "user": "1200000000000001", "team": "1200000000000800", "is_admin": True}],
        "has_more": False, "next_offset": None}}],
)
async def team_memberships_list(ctx: Context, args: TeamMembershipsListIn) -> TeamMembershipList:
    body = await get_body(ctx, "/team_memberships", params=page_params(args.limit, args.offset, "user.name,team.name,is_admin", team=args.team_gid,
                                                                         user=args.user_gid, workspace=args.workspace_gid))
    return _team_membership_list(body)


class ProjectMembersIn(PageIn):
    project_gid: str = Field(description="Gid of the project whose members should be listed")
    user_gid: Optional[str] = Field(default=None, description="Keep only the membership of this user: 'me', an email or a user gid")


@function(
    id="asana.project_memberships.list_project", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Lists the members of an Asana project: each membership reports its gid, the user, the project and the access and write levels of the user. "
        "Use it when the user asks who works on a project, who can edit it or whether a given person is a member. It requires the project gid and "
        "can be narrowed to one user (me, an email or a gid); results are paginated with a limit of 1 to 100. Read-only. It returns the same "
        "data as asana.project_memberships.list, which has no user filter, and is kept for the legacy member-listing tool. It does not add or "
        "remove members."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000003600", "user": "1200000000000001", "project": "1200000000000100", "access_level": "admin", "write_access": "write"}],
        "has_more": False, "next_offset": None}}],
)
async def project_memberships_list_project(ctx: Context, args: ProjectMembersIn) -> ProjectMembershipList:
    body = await get_body(ctx, f"/projects/{args.project_gid}/project_memberships",
                          params=page_params(args.limit, args.offset, "user.name,project.name,access_level,write_access", user=args.user_gid))
    return _project_membership_list(body)


# --- asana.workspaces.get_events / asana.events.list ----------------------------------------------

class EventsIn(BaseModel):
    sync_token: Optional[str] = Field(default=None, description="Sync token returned by the previous call; omit it on the first call to receive a starting token")


class EventItem(BaseModel):
    type: Optional[str] = Field(default=None, description="Kind of the object that changed, for example 'task' or 'project'")
    action: Optional[str] = Field(default=None, description="What happened to the object: changed, added, removed, deleted or undeleted")
    resource_gid: Optional[str] = Field(default=None, description="Gid of the object that triggered the event")
    resource_type: Optional[str] = Field(default=None, description="Kind of the object that triggered the event")
    resource_name: Optional[str] = Field(default=None, description="Name of the object that triggered the event, when it has one")
    parent_gid: Optional[str] = Field(default=None, description="Gid of the parent object, for example the project of a changed task")
    user_gid: Optional[str] = Field(default=None, description="Gid of the user who caused the event, when known")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the event happened")
    change: Optional[dict[str, Any]] = Field(default=None, description="Description of the field that changed (field, action and new value), for 'changed' events")


class EventsOut(BaseModel):
    items: list[EventItem] = Field(description="Events that happened since the sync token was issued")
    sync: Optional[str] = Field(default=None, description="Sync token to pass as sync_token in the next call to receive only newer events")
    has_more: bool = Field(default=False, description="True when more events are waiting; call again with the new sync token to get them")
    sync_reset: bool = Field(default=False, description="True when the call had no valid sync token: the list is empty and sync holds a fresh starting token")


def _event(raw: dict) -> EventItem:
    resource = raw.get("resource") or {}
    return EventItem(type=raw.get("type"), action=raw.get("action"), resource_gid=str(resource["gid"]) if resource.get("gid") else None,
                     resource_type=resource.get("resource_type"), resource_name=resource.get("name"), parent_gid=nested_gid(raw, "parent"),
                     user_gid=nested_gid(raw, "user"), created_at=raw.get("created_at"), change=raw.get("change"))


async def _events(ctx: Context, path: str, params: dict, sync_token: Optional[str]) -> EventsOut:
    if sync_token:
        params = {**params, "sync": sync_token}
    resp = await ctx.conn.request("GET", f"{BASE_URL}{path}", params=params or None, ok_statuses=(412,))
    body = resp.json()
    if resp.status_code == 412:  # sin token valido: Asana manda uno nuevo en el cuerpo y no hay eventos todavia
        return EventsOut(items=[], sync=body.get("sync"), has_more=False, sync_reset=True)
    return EventsOut(items=[_event(i) for i in body.get("data") or []], sync=body.get("sync"), has_more=bool(body.get("has_more")), sync_reset=False)


class WorkspaceEventsIn(EventsIn):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose events should be read")


@function(
    id="asana.workspaces.get_events", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Reads the stream of change events of an Asana workspace or organization: each event reports what kind of object changed, the action "
        "(changed, added, removed, deleted), the object, its parent, the user and the time. It works with sync tokens: the first call, without "
        "sync_token, returns an empty list and a starting token (sync_reset is true); later calls with that token return what happened since, up to "
        "1000 events, plus a new token. Use it to follow changes or build incremental syncs. Read-only. It cannot read the past before the token "
        "and it has no limit parameter; for one project, task or goal use asana.events.list."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "sync_token": "de4774f6915eae04714ca93bb2f5ee81"}, "output": {
        "items": [{"type": "task", "action": "changed", "resource_gid": "1200000000000500", "resource_type": "task", "resource_name": "Preparar propuesta",
                   "parent_gid": None, "user_gid": "1200000000000001", "created_at": "2026-01-20T10:00:00.000Z",
                   "change": {"field": "completed", "action": "changed", "new_value": True}}],
        "sync": "ee4774f6915eae04714ca93bb2f5ee99", "has_more": False, "sync_reset": False}}],
)
async def workspaces_get_events(ctx: Context, args: WorkspaceEventsIn) -> EventsOut:
    return await _events(ctx, f"/workspaces/{args.workspace_gid}/events", {}, args.sync_token)


class ResourceEventsIn(EventsIn):
    resource: str = Field(description="Gid of the task, project or goal whose change events should be read")


@function(
    id="asana.events.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Reads the change events of one Asana resource (a task, a project or a goal): each event reports what kind of object changed, the action "
        "(changed, added, removed, deleted), the object that triggered it, its parent, the user and the time. For a project, events of its tasks "
        "are included. It works with sync tokens: the first call, without sync_token, returns an empty list and a starting token (sync_reset is "
        "true); later calls with that token return what happened since, up to 100 events, with has_more when there are more. Read-only. It "
        "cannot read the past before the token and has no limit parameter; for the whole workspace use asana.workspaces.get_events."
    ),
    examples=[{"name": "default", "input": {"resource": "1200000000000100", "sync_token": "de4774f6915eae04714ca93bb2f5ee81"}, "output": {
        "items": [{"type": "task", "action": "added", "resource_gid": "1200000000000500", "resource_type": "task", "resource_name": "Preparar propuesta",
                   "parent_gid": "1200000000000100", "user_gid": "1200000000000001", "created_at": "2026-01-20T10:00:00.000Z", "change": None}],
        "sync": "ee4774f6915eae04714ca93bb2f5ee99", "has_more": False, "sync_reset": False}}],
)
async def events_list(ctx: Context, args: ResourceEventsIn) -> EventsOut:
    return await _events(ctx, "/events", {"resource": args.resource}, args.sync_token)
