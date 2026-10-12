"""Funciones de lectura de Asana (API 1.0) para la Tarea 3 (Users, Tasks, Projects, Sections, Tags).

Verificado en la documentacion y en el SDK oficial python-asana (developers.asana.com/reference y
raw.githubusercontent.com/Asana/python-asana/master/docs/, 2026-10-07). Correcciones respecto al catalogo
ATENCION/tareas/asana.md (que genero una IA y no estaba verificado):
- asana.users.list_favorites: GET /users/{user_gid}/favorites existe, pero exige los query params obligatorios
  `workspace` y `resource_type` (default "project"); solo devuelve favoritos del usuario autenticado.
- asana.users.get_workspace: el endpoint real es GET /workspaces/{workspace_gid}/users/{user_gid} (la respuesta no
  trae `role`; devuelve gid, name, email).
- asana.tasks.get_by_custom_id: la ruta usa /tasks/custom_id/{custom_id} (custom_id con guion bajo, no customId).
- asana.projects.get_task_counts: la ruta usa /projects/{project_gid}/task_counts (con guion bajo) y la respuesta no
  incluye `gid`; campos reales: num_tasks, num_incomplete_tasks, num_completed_tasks, num_milestones.
- asana.sections.*: el permiso `sections:read` NO existe en Asana (los documentos del SDK no declaran scope granular
  para sections); se declara `projects:read`, el scope del recurso contenedor.
- Paginacion: cursor con limit 1-100 y offset; el body de listas trae {"data": [...], "next_page": {offset}}.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente las usa para buscar
la funcion y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.asana._common import BASE_URL, LIMIT_KW, get_body, nested_gid, next_offset  # noqa: F401
from app.functions.apps.asana.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

# --- helpers compartidos (viven en _common.py; se conservan los nombres con "_" que usa este modulo) ----------------

_get_body = get_body
_nested_gid = nested_gid
_next_offset = next_offset


# --- asana.users.get (whoami) ---------------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class Account(BaseModel):
    account_id: str = Field(description="Asana user gid of the connected account; the same value stored when the account was connected")
    display_name: Optional[str] = Field(default=None, description="Full name of the Asana user, as shown in the Asana profile")
    email: Optional[str] = Field(default=None, description="Email address of the Asana user, when the profile exposes it")
    workspaces: list[str] = Field(default_factory=list, description="Gids of the workspaces and organizations this Asana user can access")


@function(
    id="asana.users.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["users:read"],
    description=(
        "Returns the Asana account that is connected for the user: the Asana user gid (used as the account identifier), the full name, the email "
        "address and the workspaces the user belongs to. Use it to confirm which Asana account is being used, to answer questions such as 'which "
        "Asana account do I have connected?', or to check that the connection still works before reading anything else. Read-only: it takes no "
        "parameters and does not create, change or delete anything in Asana. If the user has several Asana accounts connected, one of them must be "
        "chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "1200000000000001", "display_name": "Ana Perez", "email": "ana@empresa.test",
        "workspaces": ["1200000000000002"]}}],
)
async def users_get(ctx: Context, args: NoArgs) -> Account:
    resp = await ctx.conn.request("GET", f"{BASE_URL}/users/me", params={"opt_fields": "email,name,workspaces"})
    body = resp.json().get("data") or {}
    return Account(
        account_id=str(body["gid"]),
        display_name=body.get("name"),
        email=body.get("email"),
        workspaces=[str(w.get("gid")) for w in body.get("workspaces") or []],
    )


# --- asana.users.list_favorites -------------------------------------------------------------------

class FavoritesIn(BaseModel):
    user_gid: str = Field(default="me", description="Asana user to list favorites for: 'me', an email or the user gid (the API only returns favorites of the authenticated user)")
    workspace: str = Field(description="Gid of the workspace or organization whose favorites should be listed")
    resource_type: str = Field(default="project", description="Kind of favorites to return, for example 'project', 'task' or 'tag' (default 'project')")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


class FavoriteItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the favorited object")
    resource_type: str = Field(description="Kind of favorited object, for example 'project' or 'task'")
    name: str = Field(description="Display name of the favorited object")


class FavoritesOut(BaseModel):
    items: list[FavoriteItem] = Field(description="Objects favorited by the user in the given workspace and of the requested type")
    has_more: bool = Field(description="True when there are more favorites than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of favorites")


@function(
    id="asana.users.list_favorites", version=1, verb=Verb.read, upstream_api="1.0", scopes=["users:read"],
    description=(
        "Lists the objects a user has marked as favorites inside a given Asana workspace, for one resource type at a time. Each favorite reports "
        "its gid, its resource type and its name, in the same order as it appears in the user's Asana sidebar. Use it when the user asks which "
        "projects, tasks or tags they have pinned or starred in a workspace, or wants to quickly reach a pinned item. It requires the workspace "
        "gid and accepts a resource type ('project' by default); results are paginated with a limit of 1 to 100 items per page. Read-only. Note "
        "that the API only returns favorites of the authenticated user, never of another account, and it does not list recently viewed items."
    ),
    examples=[{"name": "default", "input": {"user_gid": "me", "workspace": "1200000000000002", "resource_type": "project"}, "output": {
        "items": [{"gid": "1200000000000100", "resource_type": "project", "name": "Web 2026"}], "has_more": False, "next_offset": None}}],
)
async def users_list_favorites(ctx: Context, args: FavoritesIn) -> FavoritesOut:
    body = await _get_body(ctx, f"/users/{args.user_gid}/favorites",
                           params={"workspace": args.workspace, "resource_type": args.resource_type, "limit": args.limit,
                                   **({"offset": args.offset} if args.offset else {}), "opt_fields": "name,resource_type"})
    data = body.get("data") or []
    return FavoritesOut(
        items=[FavoriteItem(gid=str(i["gid"]), resource_type=i.get("resource_type", ""), name=i.get("name", "")) for i in data],
        has_more=bool(body.get("next_page")), next_offset=_next_offset(body),
    )


# --- asana.users.get_workspace -------------------------------------------------------------------

class WorkspaceUserIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization that contains the user")
    user_gid: str = Field(description="Asana user to fetch: 'me', an email or the user gid")


class WorkspaceUser(BaseModel):
    gid: str = Field(description="Asana unique identifier of the user")
    name: Optional[str] = Field(default=None, description="Full name of the user")
    email: Optional[str] = Field(default=None, description="Email address of the user, when the profile exposes it")


@function(
    id="asana.users.get_workspace", version=1, verb=Verb.read, upstream_api="1.0", scopes=["users:read"],
    description=(
        "Returns the record of a single Asana user within a specific workspace or organization: the user gid, the full name and the email "
        "address. Use it when the user asks about one person inside a particular workspace, for example to confirm that an email belongs to the "
        "right Asana account before sharing anything with them. It requires the workspace gid and the user identifier, which can be the special "
        "value 'me', the user's email or the user's gid. Read-only: it does not change the user or their membership. It is narrower than "
        "asana.users.get, which returns the connected account, and it does not list all users of a workspace."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "user_gid": "me"}, "output": {
        "gid": "1200000000000001", "name": "Ana Perez", "email": "ana@empresa.test"}}],
)
async def users_get_workspace(ctx: Context, args: WorkspaceUserIn) -> WorkspaceUser:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/users/{args.user_gid}", params={"opt_fields": "email,name"})
    data = body.get("data") or {}
    return WorkspaceUser(gid=str(data["gid"]), name=data.get("name"), email=data.get("email"))


# --- asana.tasks.list_project_tasks --------------------------------------------------------------

class TaskItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the task")
    name: str = Field(description="Name of the task")
    assignee: Optional[str] = Field(default=None, description="Gid of the user assigned to the task, when there is one")
    due_on: Optional[str] = Field(default=None, description="Due date of the task in YYYY-MM-DD, when one is set")
    completed: bool = Field(default=False, description="Whether the task has been marked as completed")


class TaskList(BaseModel):
    items: list[TaskItem] = Field(description="Tasks returned in this page")
    has_more: bool = Field(description="True when there are more tasks than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of tasks")


TASK_OPT_FIELDS = "name,assignee.name,due_on,completed"


def _task_item(raw: dict) -> TaskItem:
    return TaskItem(gid=str(raw["gid"]), name=raw.get("name", ""), assignee=_nested_gid(raw, "assignee"),
                    due_on=raw.get("due_on"), completed=bool(raw.get("completed")))


def _task_list(body: dict) -> TaskList:
    data = body.get("data") or []
    return TaskList(items=[_task_item(i) for i in data], has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class ProjectTasksIn(BaseModel):
    project_gid: str = Field(description="Gid of the project whose tasks should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tasks.list_project_tasks", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the tasks of an Asana project: each task reports its gid, its name, the gid of the assigned user (when assigned), the due date "
        "in YYYY-MM-DD (when set) and whether it is completed. Use it when the user asks for the tasks of a project, wants to see what has been "
        "done or is pending in one, or needs the gids to then read a specific task. Results are paginated with a limit of 1 to 100 tasks per "
        "page and an offset token to continue. Read-only. It does not include subtasks by default, does not search by name or content (use "
        "asana.tasks.search) and does not return details such as the description or the custom fields."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000110", "name": "Rediseno portada", "assignee": "1200000000000001",
                   "due_on": "2026-03-01", "completed": False}], "has_more": False, "next_offset": None}}],
)
async def tasks_list_project_tasks(ctx: Context, args: ProjectTasksIn) -> TaskList:
    body = await _get_body(ctx, f"/projects/{args.project_gid}/tasks",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": TASK_OPT_FIELDS})
    return _task_list(body)


# --- asana.tasks.list_section_tasks --------------------------------------------------------------

class SectionTasksIn(BaseModel):
    section_gid: str = Field(description="Gid of the section whose tasks should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tasks.list_section_tasks", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the tasks inside one Asana section: each task reports its gid, its name, the gid of the assigned user (when assigned), the due "
        "date in YYYY-MM-DD (when set) and whether it is completed. Use it when the user asks for the tasks of a board column or a specific "
        "section, for example 'what is in the Doing column?', or needs the gids to then read one of those tasks. Results are paginated with a "
        "limit of 1 to 100 tasks per page and an offset token to continue. Read-only. It does not create, move or edit tasks, it does not search "
        "by text, and to list tasks of a whole project use asana.tasks.list_project_tasks."
    ),
    examples=[{"name": "default", "input": {"section_gid": "1200000000000200", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000210", "name": "Redactar brief", "assignee": "1200000000000001",
                   "due_on": "2026-02-10", "completed": False}], "has_more": False, "next_offset": None}}],
)
async def tasks_list_section_tasks(ctx: Context, args: SectionTasksIn) -> TaskList:
    body = await _get_body(ctx, f"/sections/{args.section_gid}/tasks",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": TASK_OPT_FIELDS})
    return _task_list(body)


# --- asana.tasks.list_user_task_list -------------------------------------------------------------

class UserTaskListIn(BaseModel):
    user_task_list_gid: str = Field(description="Gid of the user's My Tasks list to fetch tasks from")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tasks.list_user_task_list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the tasks of a user's personal 'My Tasks' list in Asana: each task reports its gid, its name, the gid of the assigned user, the "
        "due date in YYYY-MM-DD (when set) and whether it is completed. Use it when the user asks about their own task list or inbox, such as "
        "'what do I have assigned today?', or when they need the gids of their personal tasks. Results are paginated with a limit of 1 to 100 "
        "tasks per page and an offset token to continue. Read-only. It does not read the tasks of a project (use asana.tasks.list_project_tasks) "
        "and it does not create, complete or reassign any task."
    ),
    examples=[{"name": "default", "input": {"user_task_list_gid": "1200000000000300", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000310", "name": "Preparar demo", "assignee": "1200000000000001",
                   "due_on": "2026-02-15", "completed": False}], "has_more": False, "next_offset": None}}],
)
async def tasks_list_user_task_list(ctx: Context, args: UserTaskListIn) -> TaskList:
    body = await _get_body(ctx, f"/user_task_lists/{args.user_task_list_gid}/tasks",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": TASK_OPT_FIELDS})
    return _task_list(body)


# --- asana.tasks.search --------------------------------------------------------------------------

class TaskSearchIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization to search tasks in")
    text: str = Field(min_length=1, description="Text to look for in the task name or notes")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tasks.search", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Searches for Asana tasks inside a workspace by free text: each match reports its gid, its name, the gid of the assigned user, the due "
        "date in YYYY-MM-DD (when set) and whether it is completed. Use it when the user remembers a word of a task name or note and does not "
        "know the project, for example 'find the task about the invoice'. It requires the workspace gid and the text to search. Results are "
        "paginated with a limit of 1 to 100 tasks per page. Read-only. It does not search projects or files, it does not accept filters such as "
        "completion date or assignee, and to list everything in a project use asana.tasks.list_project_tasks."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "text": "factura"}, "output": {
        "items": [{"gid": "1200000000000400", "name": "Revisar factura", "assignee": "1200000000000001",
                   "due_on": "2026-02-20", "completed": False}], "has_more": False, "next_offset": None}}],
)
async def tasks_search(ctx: Context, args: TaskSearchIn) -> TaskList:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/tasks/search",
                           params={"text": args.text, "limit": args.limit,
                                   **({"offset": args.offset} if args.offset else {}), "opt_fields": TASK_OPT_FIELDS})
    return _task_list(body)


# --- asana.tasks.get_by_custom_id -----------------------------------------------------------------

class TaskByCustomIdIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization that owns the custom ID")
    custom_id: str = Field(min_length=1, description="Custom ID shortcode of the task, for example 'EX-42'")


class TaskCustomDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the task")
    name: str = Field(description="Name of the task")
    assignee: Optional[str] = Field(default=None, description="Gid of the user assigned to the task, when there is one")


@function(
    id="asana.tasks.get_by_custom_id", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Returns a single Asana task looked up by its custom ID shortcode, such as 'EX-42', inside a given workspace: the task gid, its name and "
        "the gid of the assigned user (when assigned). Use it when the user references a task by its public reference number instead of its "
        "internal gid, for example 'open task EX-12'. It requires the workspace gid and the custom ID. Read-only. If the custom ID does not "
        "exist or is not visible in that workspace, Asana returns an error. To look tasks up by their normal gid use asana.tasks.get; this "
        "function does not search by text."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "custom_id": "EX-42"}, "output": {
        "gid": "1200000000000420", "name": "Tarea EX-42", "assignee": "1200000000000001"}}],
)
async def tasks_get_by_custom_id(ctx: Context, args: TaskByCustomIdIn) -> TaskCustomDetail:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/tasks/custom_id/{args.custom_id}",
                           params={"opt_fields": "name,assignee.name"})
    data = body.get("data") or {}
    return TaskCustomDetail(gid=str(data["gid"]), name=data.get("name", ""), assignee=_nested_gid(data, "assignee"))


# --- asana.tasks.list_subtasks -------------------------------------------------------------------

class SubtasksIn(BaseModel):
    task_gid: str = Field(description="Gid of the parent task whose subtasks should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tasks.list_subtasks", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the direct subtasks of an Asana task: each subtask reports its gid, its name, the gid of the assigned user, the due date in "
        "YYYY-MM-DD (when set) and whether it is completed. Use it when the user asks for the breakdown of a task, such as 'what are the subtasks "
        "of this task?', or needs the gids of the child tasks to read or reference them later. Only direct children are returned, not grandchildren. "
        "Results are paginated with a limit of 1 to 100 subtasks per page. Read-only: it does not create, delete or reorder subtasks (for that a "
        "write function is needed) and it does not list tasks of a whole project, use asana.tasks.list_project_tasks."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000510", "name": "Buscar proveedor", "assignee": "1200000000000001",
                   "due_on": "2026-01-30", "completed": True}], "has_more": False, "next_offset": None}}],
)
async def tasks_list_subtasks(ctx: Context, args: SubtasksIn) -> TaskList:
    body = await _get_body(ctx, f"/tasks/{args.task_gid}/subtasks",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": TASK_OPT_FIELDS})
    return _task_list(body)


# --- asana.tasks.list_dependencies / list_dependents ----------------------------------------------

class TaskRef(BaseModel):
    gid: str = Field(description="Asana unique identifier of the task")
    name: str = Field(description="Name of the task")


class TaskRefList(BaseModel):
    items: list[TaskRef] = Field(description="Related tasks returned in this page")
    has_more: bool = Field(description="True when there are more related tasks than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page")


def _task_ref_list(body: dict) -> TaskRefList:
    data = body.get("data") or []
    return TaskRefList(items=[TaskRef(gid=str(i["gid"]), name=i.get("name", "")) for i in data],
                       has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class RelatedTasksIn(BaseModel):
    task_gid: str = Field(description="Gid of the task whose related tasks should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tasks.list_dependencies", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the dependencies of an Asana task, that is, the tasks that must be completed before this one can be finished. Each dependency "
        "reports its gid and its name. Use it when the user wants to know what blocks a task, for example 'why is this task not done, what does "
        "it depend on?', or needs the gids of the blocking tasks. Results are paginated with a limit of 1 to 100 tasks per page. Read-only. It "
        "does not add or remove dependencies (a task has at most 30 dependencies plus dependents combined), and to see which tasks depend on this "
        "one use asana.tasks.list_dependents instead."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000600", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000610", "name": "Aprobar presupuesto"}, {"gid": "1200000000000620", "name": "Firmar contrato"}],
        "has_more": False, "next_offset": None}}],
)
async def tasks_list_dependencies(ctx: Context, args: RelatedTasksIn) -> TaskRefList:
    body = await _get_body(ctx, f"/tasks/{args.task_gid}/dependencies",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "name"})
    return _task_ref_list(body)


@function(
    id="asana.tasks.list_dependents", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the dependents of an Asana task, that is, the tasks that cannot start or finish until this one is completed. Each dependent "
        "reports its gid and its name. Use it when the user wants to know what is waiting on a task, for example 'what depends on this task?', or "
        "needs the gids of the downstream tasks before planning. Results are paginated with a limit of 1 to 100 tasks per page. Read-only. It "
        "does not create or remove dependencies, and to see which tasks block this one use asana.tasks.list_dependencies instead."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000600", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000630", "name": "Publicar landing"}, {"gid": "1200000000000640", "name": "Enviar a prensa"}],
        "has_more": False, "next_offset": None}}],
)
async def tasks_list_dependents(ctx: Context, args: RelatedTasksIn) -> TaskRefList:
    body = await _get_body(ctx, f"/tasks/{args.task_gid}/dependents",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "name"})
    return _task_ref_list(body)


# --- asana.tasks.list_projects -------------------------------------------------------------------

class ProjectBrief(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project")
    name: str = Field(description="Name of the project")


class ProjectBriefList(BaseModel):
    items: list[ProjectBrief] = Field(description="Projects returned in this page")
    has_more: bool = Field(description="True when there are more projects than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of projects")


@function(
    id="asana.tasks.list_projects", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Lists the Asana projects that a given task belongs to: each project reports its gid and its name. Use it when the user asks in which "
        "projects a task appears or is multi-homed, for example 'which project does this task belong to?', or needs the project gids to read their "
        "contents later. Results are paginated with a limit of 1 to 100 projects per page. Read-only. It does not add the task to a project, it "
        "does not list the tasks of a project (use asana.tasks.list_project_tasks) and it only returns projects the user can see."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000700", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000100", "name": "Web 2026"}, {"gid": "1200000000000150", "name": "CRM"}],
        "has_more": False, "next_offset": None}}],
)
async def tasks_list_projects(ctx: Context, args: RelatedTasksIn) -> ProjectBriefList:
    body = await _get_body(ctx, f"/tasks/{args.task_gid}/projects",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "name"})
    data = body.get("data") or []
    return ProjectBriefList(items=[ProjectBrief(gid=str(i["gid"]), name=i.get("name", "")) for i in data],
                            has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


# --- asana.projects.list_team_projects / list_workspace_projects / search -----------------------------

class ProjectItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project")
    name: str = Field(description="Name of the project")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the project, when there is one")


class ProjectList(BaseModel):
    items: list[ProjectItem] = Field(description="Projects returned in this page")
    has_more: bool = Field(description="True when there are more projects than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of projects")


PROJECT_OPT_FIELDS = "name,owner.name"


def _project_item(raw: dict) -> ProjectItem:
    return ProjectItem(gid=str(raw["gid"]), name=raw.get("name", ""), owner=_nested_gid(raw, "owner"))


def _project_list(body: dict) -> ProjectList:
    data = body.get("data") or []
    return ProjectList(items=[_project_item(i) for i in data], has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class TeamProjectsIn(BaseModel):
    team_gid: str = Field(description="Gid of the team whose projects should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.projects.list_team_projects", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Lists the Asana projects that belong to a team: each project reports its gid, its name and the gid of its owner when there is one. Use "
        "it when the user asks for the projects of a team or department, for example 'which projects does the Marketing team have?', or needs the "
        "project gids to read their tasks later. Only projects the user can see are returned. Results are paginated with a limit of 1 to 100 "
        "projects per page. Read-only. It does not create projects, it does not list tasks (use asana.tasks.list_project_tasks) and to list the "
        "projects of a whole workspace use asana.projects.list_workspace_projects."
    ),
    examples=[{"name": "default", "input": {"team_gid": "1200000000000800", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000100", "name": "Web 2026", "owner": "1200000000000001"}],
        "has_more": False, "next_offset": None}}],
)
async def projects_list_team_projects(ctx: Context, args: TeamProjectsIn) -> ProjectList:
    body = await _get_body(ctx, f"/teams/{args.team_gid}/projects",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": PROJECT_OPT_FIELDS})
    return _project_list(body)


class WorkspaceProjectsIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose projects should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.projects.list_workspace_projects", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Lists the Asana projects inside a workspace or organization: each project reports its gid, its name and the gid of its owner when there "
        "is one. Use it when the user asks for all the projects of a workspace, or when a project gid is needed before reading or searching its "
        "tasks. Only projects the user can see are returned. Results are paginated with a limit of 1 to 100 projects per page and an offset token "
        "to continue. Read-only. It does not create projects, it does not return their tasks, and to scope the listing to one team use "
        "asana.projects.list_team_projects."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "limit": 2}, "output": {
        "items": [{"gid": "1200000000000100", "name": "Web 2026", "owner": "1200000000000001"},
                  {"gid": "1200000000000150", "name": "CRM", "owner": None}], "has_more": False, "next_offset": None}}],
)
async def projects_list_workspace_projects(ctx: Context, args: WorkspaceProjectsIn) -> ProjectList:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/projects",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": PROJECT_OPT_FIELDS})
    return _project_list(body)


class ProjectSearchIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization to search projects in")
    text: str = Field(min_length=1, description="Text to look for in the project name")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.projects.search", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Searches for Asana projects inside a workspace by their name: each match reports its gid, its name and the gid of its owner when there "
        "is one. Use it when the user remembers part of a project name but not the exact project, for example 'find the project about the "
        "website'. It requires the workspace gid and the text to search. Results are paginated with a limit of 1 to 100 projects per page. "
        "Read-only. It does not search tasks (use asana.tasks.search), it does not filter by archived status or owner, and to see everything in a "
        "workspace use asana.projects.list_workspace_projects."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "text": "web"}, "output": {
        "items": [{"gid": "1200000000000100", "name": "Web 2026", "owner": "1200000000000001"}],
        "has_more": False, "next_offset": None}}],
)
async def projects_search(ctx: Context, args: ProjectSearchIn) -> ProjectList:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/projects/search",
                           params={"text": args.text, "limit": args.limit,
                                   **({"offset": args.offset} if args.offset else {}), "opt_fields": PROJECT_OPT_FIELDS})
    return _project_list(body)


# --- asana.projects.get_task_counts --------------------------------------------------------------

class TaskCountsIn(BaseModel):
    project_gid: str = Field(description="Gid of the project whose task counts should be fetched")


class TaskCounts(BaseModel):
    num_tasks: Optional[int] = Field(default=None, description="Total number of tasks in the project")
    num_incomplete_tasks: Optional[int] = Field(default=None, description="Number of tasks in the project that are not completed")
    num_completed_tasks: Optional[int] = Field(default=None, description="Number of tasks in the project that are completed")
    num_milestones: Optional[int] = Field(default=None, description="Total number of milestones in the project")


@function(
    id="asana.projects.get_task_counts", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Returns the task counts of an Asana project: the total number of tasks, the number of incomplete tasks, the number of completed tasks "
        "and the number of milestones. Use it when the user asks for a quick summary or progress of a project without listing every task, for "
        "example 'how many tasks are left in this project?'. It requires only the project gid. Read-only. The counts reflect the tasks the user "
        "can see and depend on the filters of the Asana view. It does not list the tasks themselves (use asana.tasks.list_project_tasks) and it "
        "does not return dates or assignees."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100"}, "output": {
        "num_tasks": 12, "num_incomplete_tasks": 4, "num_completed_tasks": 8, "num_milestones": 1}}],
)
async def projects_get_task_counts(ctx: Context, args: TaskCountsIn) -> TaskCounts:
    body = await _get_body(ctx, f"/projects/{args.project_gid}/task_counts")
    data = body.get("data") or {}
    return TaskCounts(num_tasks=data.get("num_tasks"), num_incomplete_tasks=data.get("num_incomplete_tasks"),
                      num_completed_tasks=data.get("num_completed_tasks"), num_milestones=data.get("num_milestones"))


# --- asana.sections.list -------------------------------------------------------------------------

class SectionItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the section")
    name: str = Field(description="Name of the section, for example 'To do', 'Doing' or 'Done'")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the section was created")


class SectionList(BaseModel):
    items: list[SectionItem] = Field(description="Sections of the project returned in this page")
    has_more: bool = Field(description="True when there are more sections than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of sections")


class SectionsIn(BaseModel):
    project_gid: str = Field(description="Gid of the project whose sections should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.sections.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Lists the sections (board columns) of an Asana project in display order: each section reports its gid, its name and, when available, "
        "its creation date. Use it when the user asks for the columns of a project, for example 'what columns does this board have?', or needs the "
        "section gid to then list its tasks with asana.tasks.list_section_tasks. Results are paginated with a limit of 1 to 100 sections per "
        "page. Read-only. Note that Asana does not expose a granular scope for sections, so access follows the project scope. It does not create, "
        "rename or reorder sections, and it does not return the tasks inside each section."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000000200", "name": "To do", "created_at": "2026-01-01T10:00:00Z"},
                  {"gid": "1200000000000201", "name": "Doing", "created_at": "2026-01-01T10:00:00Z"}],
        "has_more": False, "next_offset": None}}],
)
async def sections_list(ctx: Context, args: SectionsIn) -> SectionList:
    body = await _get_body(ctx, f"/projects/{args.project_gid}/sections",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "name,created_at"})
    data = body.get("data") or []
    return SectionList(items=[SectionItem(gid=str(i["gid"]), name=i.get("name", ""), created_at=i.get("created_at")) for i in data],
                       has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


# --- asana.sections.get --------------------------------------------------------------------------

class SectionGetIn(BaseModel):
    section_gid: str = Field(description="Gid of the section to fetch")


class SectionDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the section")
    name: str = Field(description="Name of the section")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the section was created")
    project: Optional[str] = Field(default=None, description="Gid of the project that contains the section")


@function(
    id="asana.sections.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Returns the details of a single Asana section: its gid, its name, its creation date and the gid of the project that contains it. Use it "
        "when the user references a section directly, for example to confirm its name or to know which project it belongs to before listing its "
        "tasks. It requires only the section gid. Read-only. Note that Asana does not expose a granular scope for sections, so access follows the "
        "project scope. It does not return the tasks of the section (use asana.tasks.list_section_tasks) and it does not list the sections of a "
        "whole project (use asana.sections.list)."
    ),
    examples=[{"name": "default", "input": {"section_gid": "1200000000000200"}, "output": {
        "gid": "1200000000000200", "name": "To do", "created_at": "2026-01-01T10:00:00Z", "project": "1200000000000100"}}],
)
async def sections_get(ctx: Context, args: SectionGetIn) -> SectionDetail:
    body = await _get_body(ctx, f"/sections/{args.section_gid}", params={"opt_fields": "name,created_at,project.name"})
    data = body.get("data") or {}
    return SectionDetail(gid=str(data["gid"]), name=data.get("name", ""), created_at=data.get("created_at"),
                         project=_nested_gid(data, "project"))


# --- asana.tags ----------------------------------------------------------------------------------

class TagItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the tag")
    name: str = Field(description="Name of the tag")
    color: Optional[str] = Field(default=None, description="Color of the tag, for example 'light-green', when one is set")


class TagList(BaseModel):
    items: list[TagItem] = Field(description="Tags returned in this page")
    has_more: bool = Field(description="True when there are more tags than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of tags")


class TagGetIn(BaseModel):
    tag_gid: str = Field(description="Gid of the tag to fetch")


class TagDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the tag")
    name: str = Field(description="Name of the tag")
    color: Optional[str] = Field(default=None, description="Color of the tag, for example 'light-green', when one is set")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace that owns the tag")


def _tag_item(raw: dict) -> TagItem:
    return TagItem(gid=str(raw["gid"]), name=raw.get("name", ""), color=raw.get("color"))


def _tag_list(body: dict) -> TagList:
    data = body.get("data") or []
    return TagList(items=[_tag_item(i) for i in data], has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


@function(
    id="asana.tags.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tags:read"],
    description=(
        "Returns the details of a single Asana tag: its gid, its name, its color when one is set and the gid of the workspace that owns it. Use "
        "it when the user references a tag directly, for example to confirm what color or name it has, or to know which workspace it belongs to "
        "before listing its tasks. It requires only the tag gid. Read-only. It does not return the tasks that use the tag, it does not list tags "
        "of a workspace (use asana.tags.list_workspace_tags) and it does not modify the tag in any way."
    ),
    examples=[{"name": "default", "input": {"tag_gid": "1200000000000900"}, "output": {
        "gid": "1200000000000900", "name": "Urgente", "color": "red", "workspace": "1200000000000002"}}],
)
async def tags_get(ctx: Context, args: TagGetIn) -> TagDetail:
    body = await _get_body(ctx, f"/tags/{args.tag_gid}", params={"opt_fields": "name,color,workspace.name"})
    data = body.get("data") or {}
    return TagDetail(gid=str(data["gid"]), name=data.get("name", ""), color=data.get("color"), workspace=_nested_gid(data, "workspace"))


class TaskTagsIn(BaseModel):
    task_gid: str = Field(description="Gid of the task whose tags should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tags.list_task_tags", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tags:read"],
    description=(
        "Lists the Asana tags applied to a task: each tag reports its gid, its name and its color when one is set. Use it when the user asks what "
        "labels or categories a task has, for example 'which tags does this task have?', or needs the tag gids to filter or reference later. "
        "Results are paginated with a limit of 1 to 100 tags per page. Read-only. It does not add or remove tags from the task, and to list the "
        "tags available in a workspace use asana.tags.list_workspace_tags."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500"}, "output": {
        "items": [{"gid": "1200000000000900", "name": "Urgente", "color": "red"}], "has_more": False, "next_offset": None}}],
)
async def tags_list_task_tags(ctx: Context, args: TaskTagsIn) -> TagList:
    body = await _get_body(ctx, f"/tasks/{args.task_gid}/tags",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "name,color"})
    return _tag_list(body)


class WorkspaceTagsIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose tags should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.tags.list_workspace_tags", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tags:read"],
    description=(
        "Lists the Asana tags available in a workspace or organization: each tag reports its gid, its name and its color when one is set. Use it "
        "when the user asks for all the labels of a workspace, for example 'which tags exist?', or needs a tag gid before filtering tasks. Only "
        "tags the user can see are returned. Results are paginated with a limit of 1 to 100 tags per page. Read-only. It does not create or "
        "rename tags, it does not show which tasks use each tag, and to see the tags of a specific task use asana.tags.list_task_tags."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000000900", "name": "Urgente", "color": "red"}], "has_more": False, "next_offset": None}}],
)
async def tags_list_workspace_tags(ctx: Context, args: WorkspaceTagsIn) -> TagList:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/tags",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "name,color"})
    return _tag_list(body)


# --------------------------------------------------------------------------------------------------
# Tarea 4: stories, attachments, custom fields, custom field settings, teams, team memberships,
# project memberships y workspaces. Verificado contra python-asana (StoriesApi, AttachmentsApi,
# CustomFieldsApi, CustomFieldSettingsApi, TeamsApi, TeamMembershipsApi, ProjectMembershipsApi,
# WorkspacesApi, 2026-10-07). Correcciones respecto al catalogo ATENCION/tareas/asana.md:
# - asana.attachments.list: NO existe GET /{parent_type}/{parent_gid}/attachments; el endpoint real es
#   GET /attachments con el query `parent` obligatorio (gid de project, project_brief o task).
# - asana.team_memberships.list_team: la ruta es /teams/{team_gid}/team_memberships (no /memberships).
# - asana.team_memberships.list_user: exige el query `workspace`.
# - asana.teams.list_user_teams: exige el query `organization` (workspace/org para filtrar).
# - asana.project_memberships.list: no existe GET /project_memberships; el real es
#   GET /projects/{project_gid}/project_memberships (requiere project_gid).
# - asana.custom_field_settings.*: cada endpoint pide el scope del recurso contenedor
#   (projects:read, portfolios:read, teams:read, goals:read), no custom_fields:read.
# - Scopes reales (pertenecen a la lista oficial de /docs/oauth-scopes y ya estan archivados en
#   app_spec.py): stories:read, attachments:read, custom_fields:read, teams:read,
#   team_memberships:read, workspaces:read.
# --------------------------------------------------------------------------------------------------

# --- asana.stories --------------------------------------------------------------------------------

class StoryItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the story")
    type: Optional[str] = Field(default=None, description="Kind of story, for example 'comment', 'system' or 'activity'")
    text: Optional[str] = Field(default=None, description="Text content of the story, for example the comment body")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who created the story, when known")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the story was created")


class StoryList(BaseModel):
    items: list[StoryItem] = Field(description="Stories returned in this page")
    has_more: bool = Field(description="True when there are more stories than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of stories")


def _story_item(raw: dict) -> StoryItem:
    return StoryItem(gid=str(raw["gid"]), type=raw.get("type"), text=raw.get("text"),
                     created_by=_nested_gid(raw, "created_by"), created_at=raw.get("created_at"))


def _story_list(body: dict) -> StoryList:
    data = body.get("data") or []
    return StoryList(items=[_story_item(i) for i in data], has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class StoryGetIn(BaseModel):
    story_gid: str = Field(description="Gid of the story to fetch")


class StoryDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the story")
    type: Optional[str] = Field(default=None, description="Kind of story, for example 'comment', 'system' or 'activity'")
    text: Optional[str] = Field(default=None, description="Text content of the story, for example the comment body")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who created the story, when known")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the story was created")
    task: Optional[str] = Field(default=None, description="Gid of the task the story belongs to, when it is a task story")


@function(
    id="asana.stories.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["stories:read"],
    description=(
        "Returns the details of a single Asana story: its gid, its kind, its text content, who created it, when it was created and the gid of the "
        "task it belongs to when it is a task story. Stories are the activity entries and comments that Asana records on a task or goal. Use it "
        "when the user references a comment or an activity item directly, for example to read the full text of a comment or to know who posted "
        "it. It requires only the story gid. Read-only. It does not post or edit comments and it does not list the stories of a task or goal (use "
        "the stories listing functions)."
    ),
    examples=[{"name": "default", "input": {"story_gid": "1200000000003000"}, "output": {
        "gid": "1200000000003000", "type": "comment", "text": "Listo para revision",
        "created_by": "1200000000000001", "created_at": "2026-02-01T10:00:00Z", "task": "1200000000000500"}}],
)
async def stories_get(ctx: Context, args: StoryGetIn) -> StoryDetail:
    body = await _get_body(ctx, f"/stories/{args.story_gid}",
                           params={"opt_fields": "text,type,created_at,created_by.name,task.name"})
    data = body.get("data") or {}
    return StoryDetail(gid=str(data["gid"]), type=data.get("type"), text=data.get("text"),
                       created_by=_nested_gid(data, "created_by"), created_at=data.get("created_at"),
                       task=_nested_gid(data, "task"))


class GoalStoriesIn(BaseModel):
    goal_gid: str = Field(description="Gid of the goal whose stories should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")
    created_after: Optional[str] = Field(default=None, description="Only return stories created after this ISO date and time")
    resource_subtype: Optional[str] = Field(default=None, description="Only return stories of this subtype, for example 'comment_added'")
    sort_ascending: Optional[bool] = Field(default=None, description="Return stories oldest first (true, the default) or newest first (false)")


@function(
    id="asana.stories.list_goal_stories", version=1, verb=Verb.read, upstream_api="1.0", scopes=["stories:read"],
    description=(
        "Lists the stories of an Asana goal: each story reports its gid, its kind, its text, who created it and when. Stories on a goal include the "
        "comments posted on it and the activity entries that record the changes to it. Use it when the user asks for the activity feed or the "
        "comments of a goal. It requires the goal gid. Results are paginated with a limit of 1 to 100 stories per page and can be filtered by "
        "creation date, by story subtype such as 'comment_added' and by ordering. Read-only. It does not post comments and it does not list the "
        "stories of a task (use the task stories endpoint)."
    ),
    examples=[{"name": "default", "input": {"goal_gid": "1200000000004000"}, "output": {
        "items": [{"gid": "1200000000003000", "type": "comment", "text": "Avanzando bien",
                   "created_by": "1200000000000001", "created_at": "2026-02-01T10:00:00Z"}],
        "has_more": False, "next_offset": None}}],
)
async def stories_list_goal_stories(ctx: Context, args: GoalStoriesIn) -> StoryList:
    params = {"limit": args.limit, "opt_fields": "text,type,created_at,created_by.name"}
    if args.offset:
        params["offset"] = args.offset
    if args.created_after:
        params["created_after"] = args.created_after
    if args.resource_subtype:
        params["resource_subtype"] = args.resource_subtype
    if args.sort_ascending is not None:
        params["sort_ascending"] = str(args.sort_ascending).lower()
    body = await _get_body(ctx, f"/goals/{args.goal_gid}/stories", params=params)
    return _story_list(body)


# --- asana.attachments ----------------------------------------------------------------------------

class AttachmentItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the attachment")
    name: str = Field(description="File name of the attachment")
    size: Optional[int] = Field(default=None, description="Size of the attachment in bytes, when Asana reports it")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the attachment was added")
    view_url: Optional[str] = Field(default=None, description="URL to view the attachment inside the Asana app")
    download_url: Optional[str] = Field(default=None, description="URL to download the attachment content")


class AttachmentList(BaseModel):
    items: list[AttachmentItem] = Field(description="Attachments returned in this page")
    has_more: bool = Field(description="True when there are more attachments than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of attachments")


def _attachment_item(raw: dict) -> AttachmentItem:
    return AttachmentItem(gid=str(raw["gid"]), name=raw.get("name", ""), size=raw.get("size"),
                          created_at=raw.get("created_at"), view_url=raw.get("view_url"), download_url=raw.get("download_url"))


def _attachment_list(body: dict) -> AttachmentList:
    data = body.get("data") or []
    return AttachmentList(items=[_attachment_item(i) for i in data], has_more=bool(body.get("next_page")),
                          next_offset=_next_offset(body))


class ObjectAttachmentsIn(BaseModel):
    parent_gid: str = Field(description="Gid of the object to fetch attachments from; must be a project, a project brief or a task")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.attachments.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["attachments:read"],
    description=(
        "Lists the attachments of an Asana object (a project, a project brief or a task): each attachment reports its gid, its file name, its size "
        "in bytes, when it was added and the URLs to view it in Asana and to download its content. Use it when the user asks for the files of a "
        "task or the key resources of a project. It requires the gid of the parent object; the endpoint is GET /attachments with the parent as a "
        "query parameter. Results are paginated with a limit of 1 to 100 items per page. Read-only. It does not upload or delete attachments."
    ),
    examples=[{"name": "default", "input": {"parent_gid": "1200000000000500"}, "output": {
        "items": [{"gid": "1200000000003100", "name": "brief.pdf", "size": 204800, "created_at": "2026-02-01T10:00:00Z",
                   "view_url": "https://app.asana.com/0/attachments/1200000000003100",
                   "download_url": "https://app.asana.com/attachments/1200000000003100/download"}],
        "has_more": False, "next_offset": None}}],
)
async def attachments_list(ctx: Context, args: ObjectAttachmentsIn) -> AttachmentList:
    params = {"limit": args.limit, "parent": args.parent_gid,
              "opt_fields": "name,size,created_at,view_url,download_url"}
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, "/attachments", params=params)
    return _attachment_list(body)


class AttachmentGetIn(BaseModel):
    attachment_gid: str = Field(description="Gid of the attachment to fetch")


class AttachmentDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the attachment")
    resource_subtype: Optional[str] = Field(default=None, description="How the attachment was added, for example 'external' or 'uploaded'")
    name: str = Field(description="File name of the attachment")
    size: Optional[int] = Field(default=None, description="Size of the attachment in bytes, when Asana reports it")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the attachment was added")
    view_url: Optional[str] = Field(default=None, description="URL to view the attachment inside the Asana app")
    download_url: Optional[str] = Field(default=None, description="URL to download the attachment content")
    parent: Optional[str] = Field(default=None, description="Gid of the object the attachment belongs to")


@function(
    id="asana.attachments.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["attachments:read"],
    description=(
        "Returns the full record of a single Asana attachment: its gid, how it was added, its file name, its size in bytes, when it was added, the "
        "URLs to view it in Asana and to download its content and the gid of the object it belongs to. Use it when the user asks for the details "
        "of one specific file or needs its download or view URL. It requires only the attachment gid. Read-only. It does not upload or delete "
        "attachments and it does not list the attachments of an object (use asana.attachments.list)."
    ),
    examples=[{"name": "default", "input": {"attachment_gid": "1200000000003100"}, "output": {
        "gid": "1200000000003100", "resource_subtype": "external", "name": "brief.pdf", "size": 204800,
        "created_at": "2026-02-01T10:00:00Z", "view_url": "https://app.asana.com/0/attachments/1200000000003100",
        "download_url": "https://app.asana.com/attachments/1200000000003100/download", "parent": "1200000000000500"}}],
)
async def attachments_get(ctx: Context, args: AttachmentGetIn) -> AttachmentDetail:
    body = await _get_body(ctx, f"/attachments/{args.attachment_gid}",
                           params={"opt_fields": "resource_subtype,name,size,created_at,view_url,download_url,parent.name"})
    data = body.get("data") or {}
    return AttachmentDetail(gid=str(data["gid"]), resource_subtype=data.get("resource_subtype"),
                            name=data.get("name", ""), size=data.get("size"), created_at=data.get("created_at"),
                            view_url=data.get("view_url"), download_url=data.get("download_url"),
                            parent=_nested_gid(data, "parent"))


# --- asana.custom_fields --------------------------------------------------------------------------

class EnumOption(BaseModel):
    gid: str = Field(description="Asana unique identifier of the enum option")
    name: str = Field(description="Label of the enum option")
    color: Optional[str] = Field(default=None, description="Color of the enum option, for example 'light-green', when one is set")
    enabled: bool = Field(description="True when the enum option can still be selected")


class CustomFieldItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the custom field")
    name: str = Field(description="Name of the custom field")
    type: Optional[str] = Field(default=None, description="Data type of the custom field, for example 'text', 'number' or 'enum'")
    enum_options: list[EnumOption] = Field(default_factory=list, description="Choices of an enum or multi-enum custom field, empty for other types")


class CustomFieldList(BaseModel):
    items: list[CustomFieldItem] = Field(description="Custom fields returned in this page")
    has_more: bool = Field(description="True when there are more custom fields than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of custom fields")


def _enum_options(raw: dict) -> list[EnumOption]:
    return [EnumOption(gid=str(opt["gid"]), name=opt.get("name", ""), color=opt.get("color"), enabled=bool(opt.get("enabled", True)))
            for opt in raw.get("enum_options") or []]


def _custom_field_item(raw: dict) -> CustomFieldItem:
    return CustomFieldItem(gid=str(raw["gid"]), name=raw.get("name", ""), type=raw.get("type"), enum_options=_enum_options(raw))


def _custom_field_list(body: dict) -> CustomFieldList:
    data = body.get("data") or []
    return CustomFieldList(items=[_custom_field_item(i) for i in data], has_more=bool(body.get("next_page")),
                           next_offset=_next_offset(body))


class WorkspaceCustomFieldsIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose custom fields should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.custom_fields.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["custom_fields:read"],
    description=(
        "Lists the custom fields defined in an Asana workspace or organization: each custom field reports its gid, its name, its data type and, "
        "when it is an enum or multi-enum field, its available choices with their color. Use it when the user asks which custom fields exist to "
        "track extra information on tasks, projects or portfolios. It requires the workspace gid. Results are paginated with a limit of 1 to 100 "
        "custom fields per page. Read-only. It does not create or modify custom fields and it does not show the current values on a specific task."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000003200", "name": "Prioridad", "type": "enum", "enum_options": [
            {"gid": "1200000000003210", "name": "Alta", "color": "red", "enabled": True}]}],
        "has_more": False, "next_offset": None}}],
)
async def custom_fields_list(ctx: Context, args: WorkspaceCustomFieldsIn) -> CustomFieldList:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/custom_fields",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}),
                                   "opt_fields": "name,type,enum_options.name,enum_options.color,enum_options.enabled"})
    return _custom_field_list(body)


class CustomFieldGetIn(BaseModel):
    custom_field_gid: str = Field(description="Gid of the custom field to fetch")


class CustomFieldDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the custom field")
    name: str = Field(description="Name of the custom field")
    type: Optional[str] = Field(default=None, description="Data type of the custom field, for example 'text', 'number' or 'enum'")
    enum_options: list[EnumOption] = Field(default_factory=list, description="Choices of an enum or multi-enum custom field, empty for other types")
    is_global_to_workspace: bool = Field(description="True when the custom field is available across the whole workspace")


@function(
    id="asana.custom_fields.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["custom_fields:read"],
    description=(
        "Returns the complete definition of a single Asana custom field: its gid, its name, its data type, its enum choices when it is an enum or "
        "multi-enum field and whether it is global to the workspace. Use it when the user asks for the details of a specific custom field, for "
        "example which choices an enum field allows. It requires only the custom field gid. Read-only. It does not create or modify custom "
        "fields and it does not list the custom fields of a workspace (use asana.custom_fields.list)."
    ),
    examples=[{"name": "default", "input": {"custom_field_gid": "1200000000003200"}, "output": {
        "gid": "1200000000003200", "name": "Prioridad", "type": "enum", "enum_options": [
            {"gid": "1200000000003210", "name": "Alta", "color": "red", "enabled": True}], "is_global_to_workspace": False}}],
)
async def custom_fields_get(ctx: Context, args: CustomFieldGetIn) -> CustomFieldDetail:
    body = await _get_body(ctx, f"/custom_fields/{args.custom_field_gid}",
                           params={"opt_fields": "name,type,enum_options.name,enum_options.color,enum_options.enabled,is_global_to_workspace"})
    data = body.get("data") or {}
    return CustomFieldDetail(gid=str(data["gid"]), name=data.get("name", ""), type=data.get("type"),
                             enum_options=_enum_options(data), is_global_to_workspace=bool(data.get("is_global_to_workspace")))


# --- asana.custom_field_settings ------------------------------------------------------------------

class CustomFieldSettingItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the custom field setting")
    custom_field: Optional[str] = Field(default=None, description="Gid of the custom field this setting refers to")
    is_important: bool = Field(description="True when the custom field is highlighted as important on the object")


class CustomFieldSettingsList(BaseModel):
    items: list[CustomFieldSettingItem] = Field(description="Custom field settings returned in this page")
    has_more: bool = Field(description="True when there are more settings than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of settings")


def _custom_field_settings_list(body: dict) -> CustomFieldSettingsList:
    data = body.get("data") or []
    return CustomFieldSettingsList(
        items=[CustomFieldSettingItem(gid=str(i["gid"]), custom_field=_nested_gid(i, "custom_field"),
                                      is_important=bool(i.get("is_important", False))) for i in data],
        has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class ProjectSettingsIn(BaseModel):
    project_gid: str = Field(description="Gid of the project whose custom field settings should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.custom_field_settings.list_project", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Lists the custom field settings of an Asana project: each one reports its gid, the gid of the custom field it refers to and whether the "
        "field is marked as important on the project. A setting is the configuration that connects a custom field with a specific project. Use it "
        "when the user asks which custom fields a project uses. It requires the project gid. Results are paginated with a limit of 1 to 100 "
        "settings per page. Read-only. The scope required is projects:read, the scope of the project resource that owns the settings."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000003300", "custom_field": "1200000000003200", "is_important": True}],
        "has_more": False, "next_offset": None}}],
)
async def custom_field_settings_list_project(ctx: Context, args: ProjectSettingsIn) -> CustomFieldSettingsList:
    body = await _get_body(ctx, f"/projects/{args.project_gid}/custom_field_settings",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "custom_field.name,is_important"})
    return _custom_field_settings_list(body)


class PortfolioSettingsIn(BaseModel):
    portfolio_gid: str = Field(description="Gid of the portfolio whose custom field settings should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.custom_field_settings.list_portfolio", version=1, verb=Verb.read, upstream_api="1.0", scopes=["portfolios:read"],
    description=(
        "Lists the custom field settings of an Asana portfolio: each one reports its gid, the gid of the custom field it refers to and whether the "
        "field is marked as important on the portfolio. Use it when the user asks which custom fields a portfolio uses to summarize its projects. "
        "It requires the portfolio gid. Results are paginated with a limit of 1 to 100 settings per page. Read-only. The scope required is "
        "portfolios:read, the scope of the portfolio resource that owns the settings."
    ),
    examples=[{"name": "default", "input": {"portfolio_gid": "1200000000003400"}, "output": {
        "items": [{"gid": "1200000000003310", "custom_field": "1200000000003200", "is_important": False}],
        "has_more": False, "next_offset": None}}],
)
async def custom_field_settings_list_portfolio(ctx: Context, args: PortfolioSettingsIn) -> CustomFieldSettingsList:
    body = await _get_body(ctx, f"/portfolios/{args.portfolio_gid}/custom_field_settings",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "custom_field.name,is_important"})
    return _custom_field_settings_list(body)


class TeamSettingsIn(BaseModel):
    team_gid: str = Field(description="Gid of the team whose custom field settings should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.custom_field_settings.list_team", version=1, verb=Verb.read, upstream_api="1.0", scopes=["teams:read"],
    description=(
        "Lists the custom field settings of an Asana team: each one reports its gid, the gid of the custom field it refers to and whether the "
        "field is marked as important on the team. Use it when the user asks which custom fields are configured for a team. It requires the team "
        "gid. Results are paginated with a limit of 1 to 100 settings per page. Read-only. The scope required is teams:read, the scope of the "
        "team resource that owns the settings."
    ),
    examples=[{"name": "default", "input": {"team_gid": "1200000000000800"}, "output": {
        "items": [{"gid": "1200000000003320", "custom_field": "1200000000003200", "is_important": False}],
        "has_more": False, "next_offset": None}}],
)
async def custom_field_settings_list_team(ctx: Context, args: TeamSettingsIn) -> CustomFieldSettingsList:
    body = await _get_body(ctx, f"/teams/{args.team_gid}/custom_field_settings",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "custom_field.name,is_important"})
    return _custom_field_settings_list(body)


class GoalSettingsIn(BaseModel):
    goal_gid: str = Field(description="Gid of the goal whose custom field settings should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.custom_field_settings.list_goal", version=1, verb=Verb.read, upstream_api="1.0", scopes=["goals:read"],
    description=(
        "Lists the custom field settings of an Asana goal: each one reports its gid, the gid of the custom field it refers to and whether the "
        "field is marked as important on the goal. Use it when the user asks which custom fields a goal uses to track its progress. It requires "
        "the goal gid. Results are paginated with a limit of 1 to 100 settings per page. Read-only. The scope required is goals:read, the scope "
        "of the goal resource that owns the settings."
    ),
    examples=[{"name": "default", "input": {"goal_gid": "1200000000004000"}, "output": {
        "items": [{"gid": "1200000000003330", "custom_field": "1200000000003200", "is_important": True}],
        "has_more": False, "next_offset": None}}],
)
async def custom_field_settings_list_goal(ctx: Context, args: GoalSettingsIn) -> CustomFieldSettingsList:
    body = await _get_body(ctx, f"/goals/{args.goal_gid}/custom_field_settings",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "custom_field.name,is_important"})
    return _custom_field_settings_list(body)


# --- asana.teams ----------------------------------------------------------------------------------

class TeamItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the team")
    name: str = Field(description="Name of the team")
    organization: Optional[str] = Field(default=None, description="Gid of the workspace or organization that contains the team")


class TeamList(BaseModel):
    items: list[TeamItem] = Field(description="Teams returned in this page")
    has_more: bool = Field(description="True when there are more teams than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of teams")


def _team_item(raw: dict) -> TeamItem:
    return TeamItem(gid=str(raw["gid"]), name=raw.get("name", ""), organization=_nested_gid(raw, "organization"))


def _team_list(body: dict) -> TeamList:
    data = body.get("data") or []
    return TeamList(items=[_team_item(i) for i in data], has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class TeamGetIn(BaseModel):
    team_gid: str = Field(description="Gid of the team to fetch")


class TeamDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the team")
    name: str = Field(description="Name of the team")
    description: Optional[str] = Field(default=None, description="Short description of the team")
    organization: Optional[str] = Field(default=None, description="Gid of the workspace or organization that contains the team")
    permalink_url: Optional[str] = Field(default=None, description="URL to open the team inside the Asana app")


@function(
    id="asana.teams.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["teams:read"],
    description=(
        "Returns the details of a single Asana team: its gid, its name, its description, the gid of the workspace or organization that contains it "
        "and a URL to open it in Asana. Teams group people and projects inside an organization. Use it when the user references a team directly, "
        "for example to confirm its name. It requires only the team gid. Read-only. It does not list the members of the team (use the team "
        "memberships functions) nor the projects of the team (use asana.projects.list_team_projects)."
    ),
    examples=[{"name": "default", "input": {"team_gid": "1200000000000800"}, "output": {
        "gid": "1200000000000800", "name": "Producto", "description": "Equipo de producto",
        "organization": "1200000000000002", "permalink_url": "https://app.asana.com/0/team/1200000000000800/list"}}],
)
async def teams_get(ctx: Context, args: TeamGetIn) -> TeamDetail:
    body = await _get_body(ctx, f"/teams/{args.team_gid}",
                           params={"opt_fields": "name,description,organization.name,permalink_url"})
    data = body.get("data") or {}
    return TeamDetail(gid=str(data["gid"]), name=data.get("name", ""), description=data.get("description"),
                      organization=_nested_gid(data, "organization"), permalink_url=data.get("permalink_url"))


class UserTeamsIn(BaseModel):
    user_gid: str = Field(default="me", description="Asana user to list teams for: 'me', an email or the user gid")
    organization: str = Field(description="Workspace or organization gid to filter the teams of the user")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.teams.list_user_teams", version=1, verb=Verb.read, upstream_api="1.0", scopes=["teams:read"],
    description=(
        "Lists the Asana teams a user belongs to inside a given workspace or organization: each team reports its gid, its name and the gid of the "
        "organization that contains it. Use it when the user asks which teams they are part of or needs a team gid to filter projects. It requires "
        "the organization (workspace gid) to filter teams, and the user gid defaults to 'me'. Results are paginated with a limit of 1 to 100 "
        "teams per page. Read-only. It does not list the members of a team and it does not create or rename teams."
    ),
    examples=[{"name": "default", "input": {"organization": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000000800", "name": "Producto", "organization": "1200000000000002"}],
        "has_more": False, "next_offset": None}}],
)
async def teams_list_user_teams(ctx: Context, args: UserTeamsIn) -> TeamList:
    params = {"limit": args.limit, "organization": args.organization, "opt_fields": "name,organization.name"}
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, f"/users/{args.user_gid}/teams", params=params)
    return _team_list(body)


# --- asana.team_memberships -----------------------------------------------------------------------

class TeamMembershipItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the team membership")
    user: Optional[str] = Field(default=None, description="Gid of the user in the team")
    team: Optional[str] = Field(default=None, description="Gid of the team the user belongs to")
    is_admin: bool = Field(description="True when the user is an admin of the team")


class TeamMembershipList(BaseModel):
    items: list[TeamMembershipItem] = Field(description="Team memberships returned in this page")
    has_more: bool = Field(description="True when there are more memberships than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of memberships")


def _team_membership_list(body: dict) -> TeamMembershipList:
    data = body.get("data") or []
    return TeamMembershipList(
        items=[TeamMembershipItem(gid=str(i["gid"]), user=_nested_gid(i, "user"), team=_nested_gid(i, "team"),
                                  is_admin=bool(i.get("is_admin", False))) for i in data],
        has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class TeamMembershipGetIn(BaseModel):
    team_membership_gid: str = Field(description="Gid of the team membership to fetch")


class TeamMembershipDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the team membership")
    user: Optional[str] = Field(default=None, description="Gid of the user in the team")
    team: Optional[str] = Field(default=None, description="Gid of the team the user belongs to")
    is_admin: bool = Field(description="True when the user is an admin of the team")
    is_guest: bool = Field(description="True when the user is only a guest of the team")
    is_limited_access: bool = Field(description="True when the user has limited access to the team")


@function(
    id="asana.team_memberships.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["team_memberships:read"],
    description=(
        "Returns the details of a single Asana team membership: its gid, the gid of the user, the gid of the team and the access flags of the user "
        "in that team (admin, guest or limited access). A team membership is the record that says a user belongs to a team. Use it when the user "
        "references a membership directly, for example to check the access level of a teammate. It requires only the membership gid. Read-only. "
        "It does not add or remove users from teams and it does not list the memberships of a team (use asana.team_memberships.list_team)."
    ),
    examples=[{"name": "default", "input": {"team_membership_gid": "1200000000003500"}, "output": {
        "gid": "1200000000003500", "user": "1200000000000001", "team": "1200000000000800",
        "is_admin": True, "is_guest": False, "is_limited_access": False}}],
)
async def team_memberships_get(ctx: Context, args: TeamMembershipGetIn) -> TeamMembershipDetail:
    body = await _get_body(ctx, f"/team_memberships/{args.team_membership_gid}",
                           params={"opt_fields": "user.name,team.name,is_admin,is_guest,is_limited_access"})
    data = body.get("data") or {}
    return TeamMembershipDetail(gid=str(data["gid"]), user=_nested_gid(data, "user"), team=_nested_gid(data, "team"),
                                is_admin=bool(data.get("is_admin", False)), is_guest=bool(data.get("is_guest", False)),
                                is_limited_access=bool(data.get("is_limited_access", False)))


class TeamMembershipsForTeamIn(BaseModel):
    team_gid: str = Field(description="Gid of the team whose memberships should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.team_memberships.list_team", version=1, verb=Verb.read, upstream_api="1.0", scopes=["team_memberships:read"],
    description=(
        "Lists the team memberships of an Asana team, that is who belongs to the team: each membership reports its gid, the gid of the user and "
        "the gid of the team. Use it when the user asks who is part of a team or how many members it has. It requires the team gid; the endpoint "
        "is GET /teams/{team_gid}/team_memberships. Results are paginated with a limit of 1 to 100 memberships per page. Read-only. For the "
        "details of a single membership use asana.team_memberships.get and for the memberships of a user use asana.team_memberships.list_user."
    ),
    examples=[{"name": "default", "input": {"team_gid": "1200000000000800"}, "output": {
        "items": [{"gid": "1200000000003500", "user": "1200000000000001", "team": "1200000000000800", "is_admin": True}],
        "has_more": False, "next_offset": None}}],
)
async def team_memberships_list_team(ctx: Context, args: TeamMembershipsForTeamIn) -> TeamMembershipList:
    body = await _get_body(ctx, f"/teams/{args.team_gid}/team_memberships",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}),
                                   "opt_fields": "user.name,team.name,is_admin"})
    return _team_membership_list(body)


class TeamMembershipsForUserIn(BaseModel):
    user_gid: str = Field(default="me", description="Asana user to list memberships for: 'me', an email or the user gid")
    workspace: str = Field(description="Workspace or organization gid required by the API to list the memberships of the user")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.team_memberships.list_user", version=1, verb=Verb.read, upstream_api="1.0", scopes=["team_memberships:read"],
    description=(
        "Lists the team memberships of an Asana user, that is which teams the user belongs to inside a workspace: each membership reports its "
        "gid, the gid of the user and the gid of the team. Use it when the user asks which teams a person is part of. It requires the workspace "
        "gid, which the API uses to filter the memberships, and the user gid defaults to 'me'. Results are paginated with a limit of 1 to 100 "
        "memberships per page. Read-only. For the memberships of a team use asana.team_memberships.list_team and for the details of one "
        "membership use asana.team_memberships.get."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000003510", "user": "1200000000000001", "team": "1200000000000800", "is_admin": True}],
        "has_more": False, "next_offset": None}}],
)
async def team_memberships_list_user(ctx: Context, args: TeamMembershipsForUserIn) -> TeamMembershipList:
    params = {"limit": args.limit, "workspace": args.workspace, "opt_fields": "user.name,team.name,is_admin"}
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, f"/users/{args.user_gid}/team_memberships", params=params)
    return _team_membership_list(body)


# --- asana.project_memberships --------------------------------------------------------------------

class ProjectMembershipItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project membership")
    user: Optional[str] = Field(default=None, description="Gid of the user in the project")
    project: Optional[str] = Field(default=None, description="Gid of the project the user belongs to")
    access_level: Optional[str] = Field(default=None, description="Access level of the user in the project, for example 'admin' or 'commenter'")
    write_access: Optional[str] = Field(default=None, description="Level of write access of the user in the project")


class ProjectMembershipList(BaseModel):
    items: list[ProjectMembershipItem] = Field(description="Project memberships returned in this page")
    has_more: bool = Field(description="True when there are more memberships than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of memberships")


def _project_membership_item(raw: dict) -> ProjectMembershipItem:
    return ProjectMembershipItem(gid=str(raw["gid"]), user=_nested_gid(raw, "user"), project=_nested_gid(raw, "project"),
                                 access_level=raw.get("access_level"), write_access=raw.get("write_access"))


def _project_membership_list(body: dict) -> ProjectMembershipList:
    data = body.get("data") or []
    return ProjectMembershipList(items=[_project_membership_item(i) for i in data],
                                 has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class ProjectMembershipGetIn(BaseModel):
    project_membership_gid: str = Field(description="Gid of the project membership to fetch")


@function(
    id="asana.project_memberships.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Returns the details of a single Asana project membership: its gid, the gid of the user, the gid of the project and the access and write "
        "levels of the user in that project. A project membership is the record that connects a user with a project. Use it when the user "
        "references a membership directly, for example to know the access level of a collaborator. It requires only the membership gid and uses "
        "the project scope. Read-only. It does not add or remove users from projects and it does not list the memberships of a project (use "
        "asana.project_memberships.list)."
    ),
    examples=[{"name": "default", "input": {"project_membership_gid": "1200000000003600"}, "output": {
        "gid": "1200000000003600", "user": "1200000000000001", "project": "1200000000000100",
        "access_level": "admin", "write_access": "write"}}],
)
async def project_memberships_get(ctx: Context, args: ProjectMembershipGetIn) -> ProjectMembershipItem:
    body = await _get_body(ctx, f"/project_memberships/{args.project_membership_gid}",
                           params={"opt_fields": "user.name,project.name,access_level,write_access"})
    return _project_membership_item(body.get("data") or {})


class ProjectMembershipsForProjectIn(BaseModel):
    project_gid: str = Field(description="Gid of the project whose memberships should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.project_memberships.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["projects:read"],
    description=(
        "Lists the memberships of an Asana project, that is who collaborates on it: each membership reports its gid, the gid of the user, the gid "
        "of the project and the access and write levels of the user. Use it when the user asks who has access to a project or how many members it "
        "has. It requires the project gid; there is no global list of project memberships, the endpoint is GET /projects/{project_gid}/project_"
        "memberships. Results are paginated with a limit of 1 to 100 memberships per page. Read-only. It uses the project scope and it does not "
        "modify the membership of anyone."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000003600", "user": "1200000000000001", "project": "1200000000000100",
                   "access_level": "admin", "write_access": "write"}],
        "has_more": False, "next_offset": None}}],
)
async def project_memberships_list(ctx: Context, args: ProjectMembershipsForProjectIn) -> ProjectMembershipList:
    body = await _get_body(ctx, f"/projects/{args.project_gid}/project_memberships",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}),
                                   "opt_fields": "user.name,project.name,access_level,write_access"})
    return _project_membership_list(body)


# --- asana.workspaces -----------------------------------------------------------------------------

class WorkspaceItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the workspace or organization")
    name: str = Field(description="Name of the workspace or organization")
    is_organization: bool = Field(description="True when the object is an organization rather than a simple workspace")


class WorkspaceList(BaseModel):
    items: list[WorkspaceItem] = Field(description="Workspaces returned in this page")
    has_more: bool = Field(description="True when there are more workspaces than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of workspaces")


def _workspace_item(raw: dict) -> WorkspaceItem:
    return WorkspaceItem(gid=str(raw["gid"]), name=raw.get("name", ""), is_organization=bool(raw.get("is_organization")))


def _workspace_list(body: dict) -> WorkspaceList:
    data = body.get("data") or []
    return WorkspaceList(items=[_workspace_item(i) for i in data], has_more=bool(body.get("next_page")),
                         next_offset=_next_offset(body))


class WorkspacesListIn(BaseModel):
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.workspaces.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["workspaces:read"],
    description=(
        "Lists the Asana workspaces and organizations visible to the connected user: each one reports its gid, its name and whether it is an "
        "organization. Use it when the user asks which Asana workspaces they can access or needs the workspace gid to pass to functions like "
        "searching tasks or listing projects. Results are paginated with a limit of 1 to 100 workspaces per page. Read-only. It does not create "
        "workspaces and it does not return email domains (use asana.workspaces.get for the details of one workspace)."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "items": [{"gid": "1200000000000002", "name": "Mi equipo", "is_organization": True}],
        "has_more": False, "next_offset": None}}],
)
async def workspaces_list(ctx: Context, args: WorkspacesListIn) -> WorkspaceList:
    body = await _get_body(ctx, "/workspaces",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}),
                                   "opt_fields": "name,is_organization"})
    return _workspace_list(body)


class WorkspaceGetIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization to fetch")


class WorkspaceDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the workspace or organization")
    name: str = Field(description="Name of the workspace or organization")
    is_organization: bool = Field(description="True when the object is an organization rather than a simple workspace")
    email_domains: list[str] = Field(default_factory=list, description="Email domains of the organization, empty for simple workspaces")


@function(
    id="asana.workspaces.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["workspaces:read"],
    description=(
        "Returns the details of a single Asana workspace or organization: its gid, its name, whether it is an organization and the email domains "
        "of the organization when it has them. Use it when the user references a workspace directly, for example to confirm its name or to know "
        "if it is an organization. It requires only the workspace gid. Read-only. It does not list the workspaces of the user (use asana.workspaces."
        "list) and it does not return the members of the workspace."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "gid": "1200000000000002", "name": "Mi equipo", "is_organization": True, "email_domains": ["empresa.test"]}}],
)
async def workspaces_get(ctx: Context, args: WorkspaceGetIn) -> WorkspaceDetail:
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}", params={"opt_fields": "name,is_organization,email_domains"})
    data = body.get("data") or {}
    return WorkspaceDetail(gid=str(data["gid"]), name=data.get("name", ""), is_organization=bool(data.get("is_organization")),
                           email_domains=[str(d) for d in data.get("email_domains") or []])


# --------------------------------------------------------------------------------------------------
# Tarea 5: workspace memberships, portfolios, portfolio memberships, goals, goal relationships,
# project templates y task templates. Verificado contra python-asana (WorkspaceMembershipsApi,
# PortfoliosApi, PortfolioMembershipsApi, GoalsApi, GoalRelationshipsApi, ProjectTemplatesApi,
# TaskTemplatesApi) y la referencia developers.asana.com, 2026-10-07. Correcciones respecto al
# catalogo ATENCION/tareas/asana.md (generado por IA y sin verificar):
# - asana.workspace_memberships.list_user: GET /users/{user_gid}/workspace_memberships acepta solo
#   limit/offset/opt_fields (NO exige query `workspace`).
# - asana.portfolios.list: exige el query `workspace`.
# - asana.portfolio_memberships.list: exige un filtro obligatorio (`portfolio`, u `workspace`+`user`);
#   aqui se requiere `portfolio`. Los miembros usan `access_level` (no `role`).
# - asana.portfolio_memberships.list_portfolio: la ruta es /portfolios/{portfolio_gid}/portfolio_
#   memberships (el catalogo decian /memberships).
# - asana.goals.list: hay que filtrar por `workspace` o `team`; aqui `workspace` es obligatorio.
# - asana.goal_relationships.list: exige el query `supported_goal` (el catalogo solo ponia limit/offset);
#   los campos reales son `resource_subtype`, `supported_goal`, `supporting_resource` y
#   `contribution_weight` (el catalogo decian goal/supporting_goal).
# - asana.goals.list_parent_goals: la ruta es /goals/{goal_gid}/parentGoals (camelCase confirmado).
# - asana.project_templates.*: las plantillas de proyecto NO tienen campo created_at; los reales son
#   color, description, html_description, owner, public, requested_dates, requested_roles, team.
# - asana.project_templates.list: exige `workspace` o `team`; aqui `workspace` es obligatorio.
# - asana.task_templates.list: exige el query `project` (el catalogo solo ponia limit/offset).
# - Scopes reales (pertenecen a la lista oficial de /docs/oauth-scopes y ya estan archivados en
#   app_spec.py): workspaces:read, portfolios:read, goals:read, project_templates:read,
#   task_templates:read.
# --------------------------------------------------------------------------------------------------

# --- asana.workspace_memberships ---------------------------------------------------------------

class WorkspaceMembershipItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the workspace membership")
    user: Optional[str] = Field(default=None, description="Gid of the user who is a member of the workspace")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace the user belongs to")
    is_admin: bool = Field(description="True when the user is an admin of the workspace")


class WorkspaceMembershipList(BaseModel):
    items: list[WorkspaceMembershipItem] = Field(description="Workspace memberships returned in this page")
    has_more: bool = Field(description="True when there are more memberships than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of memberships")


def _workspace_membership_item(raw: dict) -> WorkspaceMembershipItem:
    return WorkspaceMembershipItem(gid=str(raw["gid"]), user=_nested_gid(raw, "user"),
                                   workspace=_nested_gid(raw, "workspace"), is_admin=bool(raw.get("is_admin", False)))


def _workspace_membership_list(body: dict) -> WorkspaceMembershipList:
    data = body.get("data") or []
    return WorkspaceMembershipList(items=[_workspace_membership_item(i) for i in data],
                                   has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class WorkspaceMembershipGetIn(BaseModel):
    workspace_membership_gid: str = Field(description="Gid of the workspace membership to fetch")


class WorkspaceMembershipDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the workspace membership")
    user: Optional[str] = Field(default=None, description="Gid of the user who is a member of the workspace")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace the user belongs to")
    is_admin: bool = Field(description="True when the user is an admin of the workspace")
    is_guest: bool = Field(description="True when the user is only a guest of the workspace")
    is_view_only: bool = Field(description="True when the user can only view the workspace")
    is_active: bool = Field(description="True when the membership is currently active")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the membership was created")


@function(
    id="asana.workspace_memberships.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["workspaces:read"],
    description=(
        "Returns the details of a single Asana workspace membership: its gid, the gid of the user, the gid of the workspace and the access "
        "flags of the user in that workspace (admin, guest, view only) plus its status and creation date. A workspace membership is the record "
        "that says a user belongs to a workspace or organization. Use it when the user references a membership directly, for example to check "
        "the access level of a collaborator. It requires only the membership gid. Read-only. It does not add or remove users from workspaces "
        "and it does not list the memberships of a workspace (use asana.workspace_memberships.list)."
    ),
    examples=[{"name": "default", "input": {"workspace_membership_gid": "1200000000005000"}, "output": {
        "gid": "1200000000005000", "user": "1200000000000001", "workspace": "1200000000000002",
        "is_admin": True, "is_guest": False, "is_view_only": False, "is_active": True,
        "created_at": "2026-01-01T10:00:00Z"}}],
)
async def workspace_memberships_get(ctx: Context, args: WorkspaceMembershipGetIn) -> WorkspaceMembershipDetail:
    body = await _get_body(ctx, f"/workspace_memberships/{args.workspace_membership_gid}",
                           params={"opt_fields": "user.name,workspace.name,is_admin,is_guest,is_view_only,is_active,created_at"})
    data = body.get("data") or {}
    return WorkspaceMembershipDetail(gid=str(data["gid"]), user=_nested_gid(data, "user"), workspace=_nested_gid(data, "workspace"),
                                     is_admin=bool(data.get("is_admin", False)), is_guest=bool(data.get("is_guest", False)),
                                     is_view_only=bool(data.get("is_view_only", False)), is_active=bool(data.get("is_active")),
                                     created_at=data.get("created_at"))


class WorkspaceMembershipsForWorkspaceIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose memberships should be listed")
    user: Optional[str] = Field(default=None, description="When set, only return the membership of this user ('me', an email or a gid)")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.workspace_memberships.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["workspaces:read"],
    description=(
        "Lists the workspace memberships of an Asana workspace or organization, that is who belongs to it: each membership reports its gid, "
        "the gid of the user, the gid of the workspace and whether the user is an admin. Use it when the user asks who is part of a workspace "
        "or how many members it has. It requires the workspace gid and can optionally filter by a single user. Results are paginated with a "
        "limit of 1 to 100 memberships per page. Read-only. It does not add or remove members and for the detailed flags of one membership use "
        "asana.workspace_memberships.get."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000005000", "user": "1200000000000001", "workspace": "1200000000000002", "is_admin": True}],
        "has_more": False, "next_offset": None}}],
)
async def workspace_memberships_list(ctx: Context, args: WorkspaceMembershipsForWorkspaceIn) -> WorkspaceMembershipList:
    params = {"limit": args.limit, "opt_fields": "user.name,workspace.name,is_admin"}
    if args.offset:
        params["offset"] = args.offset
    if args.user:
        params["user"] = args.user
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/workspace_memberships", params=params)
    return _workspace_membership_list(body)


class WorkspaceMembershipsForUserIn(BaseModel):
    user_gid: str = Field(default="me", description="Asana user to list memberships for: 'me', an email or the user gid")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.workspace_memberships.list_user", version=1, verb=Verb.read, upstream_api="1.0", scopes=["workspaces:read"],
    description=(
        "Lists the workspace memberships of an Asana user, that is which workspaces the user belongs to: each membership reports its gid, the "
        "gid of the user and the gid of the workspace. Use it when the user asks which Asana workspaces or organizations a person is part of. "
        "The user gid defaults to 'me'. Unlike the similar team memberships endpoint, this one does not need a workspace filter: it returns the "
        "memberships across every workspace the user belongs to. Results are paginated with a limit of 1 to 100 memberships per page. "
        "Read-only. For the memberships of a whole workspace use asana.workspace_memberships.list."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "items": [{"gid": "1200000000005010", "user": "1200000000000001", "workspace": "1200000000000002", "is_admin": True}],
        "has_more": False, "next_offset": None}}],
)
async def workspace_memberships_list_user(ctx: Context, args: WorkspaceMembershipsForUserIn) -> WorkspaceMembershipList:
    body = await _get_body(ctx, f"/users/{args.user_gid}/workspace_memberships",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}),
                                   "opt_fields": "user.name,workspace.name,is_admin"})
    return _workspace_membership_list(body)


# --- asana.portfolios ---------------------------------------------------------------------------

class PortfolioItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the portfolio")
    name: str = Field(description="Name of the portfolio")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the portfolio, when there is one")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the portfolio was created")


class PortfolioList(BaseModel):
    items: list[PortfolioItem] = Field(description="Portfolios returned in this page")
    has_more: bool = Field(description="True when there are more portfolios than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of portfolios")


def _portfolio_item(raw: dict) -> PortfolioItem:
    return PortfolioItem(gid=str(raw["gid"]), name=raw.get("name", ""), owner=_nested_gid(raw, "owner"),
                         created_at=raw.get("created_at"))


def _portfolio_list(body: dict) -> PortfolioList:
    data = body.get("data") or []
    return PortfolioList(items=[_portfolio_item(i) for i in data], has_more=bool(body.get("next_page")),
                         next_offset=_next_offset(body))


class PortfoliosListIn(BaseModel):
    workspace: str = Field(description="Gid of the workspace or organization whose portfolios should be listed")
    owner: Optional[str] = Field(default=None, description="Only return portfolios owned by this user (a gid; mainly for service accounts)")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.portfolios.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["portfolios:read"],
    description=(
        "Lists the Asana portfolios of a workspace or organization: each portfolio reports its gid, its name, the gid of its owner and when it "
        "was created. Portfolios group projects and goals to track a program or initiative. Use it when the user asks which portfolios exist or "
        "needs a portfolio gid before reading its items. It requires the workspace gid and can filter by owner. Results are paginated with a "
        "limit of 1 to 100 portfolios per page. Read-only. It does not create portfolios, it does not list the items of a portfolio (use "
        "asana.portfolios.list_items) and it only returns portfolios the user can see."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000005100", "name": "Programa 2026", "owner": "1200000000000001", "created_at": "2026-01-01T10:00:00Z"}],
        "has_more": False, "next_offset": None}}],
)
async def portfolios_list(ctx: Context, args: PortfoliosListIn) -> PortfolioList:
    params = {"limit": args.limit, "workspace": args.workspace, "opt_fields": "name,owner.name,created_at"}
    if args.offset:
        params["offset"] = args.offset
    if args.owner:
        params["owner"] = args.owner
    body = await _get_body(ctx, "/portfolios", params=params)
    return _portfolio_list(body)


class PortfolioGetIn(BaseModel):
    portfolio_gid: str = Field(description="Gid of the portfolio to fetch")


class PortfolioDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the portfolio")
    name: str = Field(description="Name of the portfolio")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the portfolio, when there is one")
    members: list[str] = Field(default_factory=list, description="Gids of the users who are members of the portfolio")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the portfolio was created")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace or organization that owns the portfolio")
    permalink_url: Optional[str] = Field(default=None, description="URL to open the portfolio inside the Asana app")


@function(
    id="asana.portfolios.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["portfolios:read"],
    description=(
        "Returns the details of a single Asana portfolio: its gid, its name, the gid of its owner, the gids of its members, when it was "
        "created, the gid of the workspace that owns it and a URL to open it in Asana. Use it when the user references a portfolio directly, "
        "for example to see who manages it or to confirm its name. It requires only the portfolio gid. Read-only. It does not list all "
        "portfolios of a workspace (use asana.portfolios.list), it does not list the projects inside it (use asana.portfolios.list_items) and "
        "it does not modify the portfolio."
    ),
    examples=[{"name": "default", "input": {"portfolio_gid": "1200000000005100"}, "output": {
        "gid": "1200000000005100", "name": "Programa 2026", "owner": "1200000000000001", "members": ["1200000000000001"],
        "created_at": "2026-01-01T10:00:00Z", "workspace": "1200000000000002",
        "permalink_url": "https://app.asana.com/0/portfolio/1200000000005100/list"}}],
)
async def portfolios_get(ctx: Context, args: PortfolioGetIn) -> PortfolioDetail:
    body = await _get_body(ctx, f"/portfolios/{args.portfolio_gid}",
                           params={"opt_fields": "name,owner.name,members.name,created_at,workspace.name,permalink_url"})
    data = body.get("data") or {}
    return PortfolioDetail(gid=str(data["gid"]), name=data.get("name", ""), owner=_nested_gid(data, "owner"),
                           members=[str(m.get("gid")) for m in data.get("members") or []], created_at=data.get("created_at"),
                           workspace=_nested_gid(data, "workspace"), permalink_url=data.get("permalink_url"))


class PortfolioItemsIn(BaseModel):
    portfolio_gid: str = Field(description="Gid of the portfolio whose items should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


class PortfolioItemEntry(BaseModel):
    gid: str = Field(description="Asana unique identifier of the portfolio item")
    name: str = Field(description="Name of the portfolio item")
    resource_type: Optional[str] = Field(default=None, description="Kind of item, for example 'project' or 'goal'")


class PortfolioItemsList(BaseModel):
    items: list[PortfolioItemEntry] = Field(description="Items of the portfolio returned in this page")
    has_more: bool = Field(description="True when there are more items than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of items")


@function(
    id="asana.portfolios.list_items", version=1, verb=Verb.read, upstream_api="1.0", scopes=["portfolios:read"],
    description=(
        "Lists the items inside an Asana portfolio, that is the projects and goals it groups: each item reports its gid, its name and its "
        "resource type. Use it when the user asks 'what is inside this portfolio?' or wants the gids of the projects of a program. It requires "
        "the portfolio gid. Results are paginated with a limit of 1 to 100 items per page and an offset token to continue. Read-only. It does "
        "not add or remove items, it does not return the tasks of the projects and to read the details of one item use the matching project or "
        "goal function."
    ),
    examples=[{"name": "default", "input": {"portfolio_gid": "1200000000005100"}, "output": {
        "items": [{"gid": "1200000000000100", "name": "Web 2026", "resource_type": "project"}],
        "has_more": False, "next_offset": None}}],
)
async def portfolios_list_items(ctx: Context, args: PortfolioItemsIn) -> PortfolioItemsList:
    body = await _get_body(ctx, f"/portfolios/{args.portfolio_gid}/items",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}),
                                   "opt_fields": "name,resource_type"})
    data = body.get("data") or []
    return PortfolioItemsList(items=[PortfolioItemEntry(gid=str(i["gid"]), name=i.get("name", ""),
                                                        resource_type=i.get("resource_type")) for i in data],
                              has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


# --- asana.portfolio_memberships ---------------------------------------------------------------

class PortfolioMembershipItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the portfolio membership")
    user: Optional[str] = Field(default=None, description="Gid of the user who is a member of the portfolio")
    portfolio: Optional[str] = Field(default=None, description="Gid of the portfolio the user belongs to")
    access_level: Optional[str] = Field(default=None, description="Access level of the user in the portfolio, for example 'admin' or 'editor'")


class PortfolioMembershipList(BaseModel):
    items: list[PortfolioMembershipItem] = Field(description="Portfolio memberships returned in this page")
    has_more: bool = Field(description="True when there are more memberships than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of memberships")


def _portfolio_membership_item(raw: dict) -> PortfolioMembershipItem:
    return PortfolioMembershipItem(gid=str(raw["gid"]), user=_nested_gid(raw, "user"), portfolio=_nested_gid(raw, "portfolio"),
                                   access_level=raw.get("access_level"))


def _portfolio_membership_list(body: dict) -> PortfolioMembershipList:
    data = body.get("data") or []
    return PortfolioMembershipList(items=[_portfolio_membership_item(i) for i in data],
                                   has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class PortfolioMembershipsListIn(BaseModel):
    portfolio: str = Field(description="Gid of the portfolio to filter the memberships on (the API requires at least this filter)")
    user: Optional[str] = Field(default=None, description="When set, only return the membership of this user ('me', an email or a gid)")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.portfolio_memberships.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["portfolios:read"],
    description=(
        "Lists the memberships of Asana portfolios that match a filter, that is who collaborates on them: each membership reports its gid, the "
        "gid of the user, the gid of the portfolio and the access level of the user. The API requires a filter, so the portfolio gid is "
        "mandatory and a user can be added to narrow the results. Use it when the user asks who has access to a portfolio. Results are "
        "paginated with a limit of 1 to 100 memberships per page. Read-only. For all memberships of one portfolio use "
        "asana.portfolio_memberships.list_portfolio and for a single membership use asana.portfolio_memberships.get."
    ),
    examples=[{"name": "default", "input": {"portfolio": "1200000000005100"}, "output": {
        "items": [{"gid": "1200000000005200", "user": "1200000000000001", "portfolio": "1200000000005100", "access_level": "admin"}],
        "has_more": False, "next_offset": None}}],
)
async def portfolio_memberships_list(ctx: Context, args: PortfolioMembershipsListIn) -> PortfolioMembershipList:
    params = {"limit": args.limit, "portfolio": args.portfolio, "opt_fields": "user.name,portfolio.name,access_level"}
    if args.offset:
        params["offset"] = args.offset
    if args.user:
        params["user"] = args.user
    body = await _get_body(ctx, "/portfolio_memberships", params=params)
    return _portfolio_membership_list(body)


class PortfolioMembershipGetIn(BaseModel):
    portfolio_membership_gid: str = Field(description="Gid of the portfolio membership to fetch")


@function(
    id="asana.portfolio_memberships.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["portfolios:read"],
    description=(
        "Returns the details of a single Asana portfolio membership: its gid, the gid of the user, the gid of the portfolio and the access "
        "level of the user in that portfolio. A portfolio membership is the record that connects a user with a portfolio. Use it when the user "
        "references a membership directly, for example to know the access level of a collaborator. It requires only the membership gid. "
        "Read-only. It does not add or remove users from portfolios and it does not list the memberships of a portfolio (use "
        "asana.portfolio_memberships.list_portfolio)."
    ),
    examples=[{"name": "default", "input": {"portfolio_membership_gid": "1200000000005200"}, "output": {
        "gid": "1200000000005200", "user": "1200000000000001", "portfolio": "1200000000005100", "access_level": "admin"}}],
)
async def portfolio_memberships_get(ctx: Context, args: PortfolioMembershipGetIn) -> PortfolioMembershipItem:
    body = await _get_body(ctx, f"/portfolio_memberships/{args.portfolio_membership_gid}",
                           params={"opt_fields": "user.name,portfolio.name,access_level"})
    return _portfolio_membership_item(body.get("data") or {})


class PortfolioMembershipsForPortfolioIn(BaseModel):
    portfolio_gid: str = Field(description="Gid of the portfolio whose memberships should be listed")
    user: Optional[str] = Field(default=None, description="When set, only return the membership of this user ('me', an email or a gid)")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.portfolio_memberships.list_portfolio", version=1, verb=Verb.read, upstream_api="1.0", scopes=["portfolios:read"],
    description=(
        "Lists the memberships of one Asana portfolio, that is who collaborates on it: each membership reports its gid, the gid of the user, "
        "the gid of the portfolio and the access level of the user. Use it when the user asks who has access to a portfolio or how many members "
        "it has. It requires the portfolio gid and can filter by a single user. Results are paginated with a limit of 1 to 100 memberships per "
        "page. Read-only. Note that the endpoint is GET /portfolios/{portfolio_gid}/portfolio_memberships. To search across portfolios with a "
        "filter use asana.portfolio_memberships.list."
    ),
    examples=[{"name": "default", "input": {"portfolio_gid": "1200000000005100"}, "output": {
        "items": [{"gid": "1200000000005200", "user": "1200000000000001", "portfolio": "1200000000005100", "access_level": "admin"}],
        "has_more": False, "next_offset": None}}],
)
async def portfolio_memberships_list_portfolio(ctx: Context, args: PortfolioMembershipsForPortfolioIn) -> PortfolioMembershipList:
    params = {"limit": args.limit, "opt_fields": "user.name,portfolio.name,access_level"}
    if args.offset:
        params["offset"] = args.offset
    if args.user:
        params["user"] = args.user
    body = await _get_body(ctx, f"/portfolios/{args.portfolio_gid}/portfolio_memberships", params=params)
    return _portfolio_membership_list(body)


# --- asana.goals --------------------------------------------------------------------------------

class GoalItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the goal")
    name: str = Field(description="Name of the goal")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the goal, when there is one")
    due_on: Optional[str] = Field(default=None, description="Due date of the goal in YYYY-MM-DD, when one is set")
    status: Optional[str] = Field(default=None, description="Current status of the goal, for example 'on_track' or 'ahead'")
    team: Optional[str] = Field(default=None, description="Gid of the team that owns the goal, when it is a team goal")


class GoalList(BaseModel):
    items: list[GoalItem] = Field(description="Goals returned in this page")
    has_more: bool = Field(description="True when there are more goals than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of goals")


def _goal_item(raw: dict) -> GoalItem:
    return GoalItem(gid=str(raw["gid"]), name=raw.get("name", ""), owner=_nested_gid(raw, "owner"),
                    due_on=raw.get("due_on"), status=raw.get("status"), team=_nested_gid(raw, "team"))


def _goal_list(body: dict) -> GoalList:
    data = body.get("data") or []
    return GoalList(items=[_goal_item(i) for i in data], has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


GOAL_OPT_FIELDS = "name,owner.name,due_on,status,team.name"


def _goal_params(limit: int, offset: Optional[str]) -> dict:
    return {"limit": limit, **({"offset": offset} if offset else {}), "opt_fields": GOAL_OPT_FIELDS}


class GoalsListIn(BaseModel):
    workspace: str = Field(description="Gid of the workspace or organization to filter the goals on")
    team: Optional[str] = Field(default=None, description="Gid of the team to filter the goals on, when team goals are wanted")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.goals.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["goals:read"],
    description=(
        "Lists the Asana goals of a workspace or organization: each goal reports its gid, its name, the gid of its owner, its due date, its "
        "current status and the gid of its team when it is a team goal. Use it when the user asks which goals exist or needs a goal gid before "
        "reading its details. It requires the workspace gid and can filter by team. Results are paginated with a limit of 1 to 100 goals per "
        "page. Read-only. It does not create goals, it does not show the parent goals of a goal (use asana.goals.list_parent_goals) and to read "
        "one goal in depth use asana.goals.get."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000005300", "name": "Crecer 20%", "owner": "1200000000000001", "due_on": "2026-12-31",
                   "status": "on_track", "team": "1200000000000800"}], "has_more": False, "next_offset": None}}],
)
async def goals_list(ctx: Context, args: GoalsListIn) -> GoalList:
    params = _goal_params(args.limit, args.offset)
    params["workspace"] = args.workspace
    if args.team:
        params["team"] = args.team
    body = await _get_body(ctx, "/goals", params=params)
    return _goal_list(body)


class GoalGetIn(BaseModel):
    goal_gid: str = Field(description="Gid of the goal to fetch")


class GoalDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the goal")
    name: str = Field(description="Name of the goal")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the goal, when there is one")
    team: Optional[str] = Field(default=None, description="Gid of the team that owns the goal, when it is a team goal")
    due_on: Optional[str] = Field(default=None, description="Due date of the goal in YYYY-MM-DD, when one is set")
    start_on: Optional[str] = Field(default=None, description="Start date of the goal in YYYY-MM-DD, when one is set")
    status: Optional[str] = Field(default=None, description="Current status of the goal, for example 'on_track' or 'ahead'")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace or organization that owns the goal")


@function(
    id="asana.goals.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["goals:read"],
    description=(
        "Returns the details of a single Asana goal: its gid, its name, the gid of its owner, the gid of its team, its due and start dates, "
        "its current status and the workspace that owns it. Use it when the user references a goal directly, for example to confirm when it "
        "ends or who is in charge of it. It requires only the goal gid. Read-only. It does not modify the goal, it does not list goals of a "
        "workspace (use asana.goals.list) and it does not expose the parent goals or the supporting goals of this goal."
    ),
    examples=[{"name": "default", "input": {"goal_gid": "1200000000005300"}, "output": {
        "gid": "1200000000005300", "name": "Crecer 20%", "owner": "1200000000000001", "team": "1200000000000800",
        "due_on": "2026-12-31", "start_on": "2026-01-01", "status": "on_track", "workspace": "1200000000000002"}}],
)
async def goals_get(ctx: Context, args: GoalGetIn) -> GoalDetail:
    body = await _get_body(ctx, f"/goals/{args.goal_gid}",
                           params={"opt_fields": "name,owner.name,team.name,due_on,start_on,status,workspace.name"})
    data = body.get("data") or {}
    return GoalDetail(gid=str(data["gid"]), name=data.get("name", ""), owner=_nested_gid(data, "owner"),
                      team=_nested_gid(data, "team"), due_on=data.get("due_on"), start_on=data.get("start_on"),
                      status=data.get("status"), workspace=_nested_gid(data, "workspace"))


class GoalParentGoalsIn(BaseModel):
    goal_gid: str = Field(description="Gid of the goal whose parent goals should be listed")


class GoalParentItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the parent goal")
    name: str = Field(description="Name of the parent goal")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the parent goal, when there is one")
    due_on: Optional[str] = Field(default=None, description="Due date of the parent goal in YYYY-MM-DD, when one is set")


class GoalParentList(BaseModel):
    items: list[GoalParentItem] = Field(description="Parent goals returned in this page")
    has_more: bool = Field(description="True when there are more parent goals than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of parent goals")


@function(
    id="asana.goals.list_parent_goals", version=1, verb=Verb.read, upstream_api="1.0", scopes=["goals:read"],
    description=(
        "Lists the parent goals of an Asana goal, that is the broader goals this goal rolls up into: each parent reports its gid, its name, the "
        "gid of its owner and its due date. Use it when the user asks 'which larger goal is this part of?' or wants to understand the goal "
        "hierarchy before planning. It requires the goal gid; the endpoint is GET /goals/{goal_gid}/parentGoals. Results are paginated with a "
        "limit of 1 to 100 parent goals per page. Read-only. It does not change the goal hierarchy and to see which goals support a goal use "
        "asana.goal_relationships.list."
    ),
    examples=[{"name": "default", "input": {"goal_gid": "1200000000005300"}, "output": {
        "items": [{"gid": "1200000000005310", "name": "Objetivo anual", "owner": "1200000000000001", "due_on": "2026-12-31"}],
        "has_more": False, "next_offset": None}}],
)
async def goals_list_parent_goals(ctx: Context, args: GoalParentGoalsIn) -> GoalParentList:
    body = await _get_body(ctx, f"/goals/{args.goal_gid}/parentGoals",
                           params={"limit": 100, "opt_fields": "name,owner.name,due_on"})
    data = body.get("data") or []
    return GoalParentList(items=[GoalParentItem(gid=str(i["gid"]), name=i.get("name", ""), owner=_nested_gid(i, "owner"),
                                                due_on=i.get("due_on")) for i in data],
                          has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


# --- asana.goal_relationships -------------------------------------------------------------------

class GoalRelationshipItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the goal relationship")
    resource_subtype: Optional[str] = Field(default=None, description="Kind of relationship, for example 'subgoal' or 'supporting_resource'")
    supported_goal: Optional[str] = Field(default=None, description="Gid of the goal that receives the support")
    supporting_resource: Optional[str] = Field(default=None, description="Gid of the resource (goal, project or task) that supports the goal")
    contribution_weight: Optional[float] = Field(default=None, description="How much this supporting resource contributes to the goal")


class GoalRelationshipList(BaseModel):
    items: list[GoalRelationshipItem] = Field(description="Goal relationships returned in this page")
    has_more: bool = Field(description="True when there are more relationships than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of relationships")


def _goal_relationship_item(raw: dict) -> GoalRelationshipItem:
    return GoalRelationshipItem(gid=str(raw["gid"]), resource_subtype=raw.get("resource_subtype"),
                                supported_goal=_nested_gid(raw, "supported_goal"),
                                supporting_resource=_nested_gid(raw, "supporting_resource"),
                                contribution_weight=raw.get("contribution_weight"))


def _goal_relationship_list(body: dict) -> GoalRelationshipList:
    data = body.get("data") or []
    return GoalRelationshipList(items=[_goal_relationship_item(i) for i in data],
                                has_more=bool(body.get("next_page")), next_offset=_next_offset(body))


class GoalRelationshipsListIn(BaseModel):
    supported_goal: str = Field(description="Gid of the goal whose supporting relationships should be listed (the API requires it)")
    resource_subtype: Optional[str] = Field(default=None, description="Filter to relationships of this subtype, for example 'subgoal'")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.goal_relationships.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["goals:read"],
    description=(
        "Lists the goal relationships of an Asana goal, that is what supports it: each relationship reports its gid, its subtype, the gid of "
        "the goal that receives the support, the gid of the supporting resource (a goal, project or task) and the contribution weight. Use it "
        "when the user asks 'what is working towards this goal?' or wants to see how a goal is decomposed. The API requires the gid of the "
        "goal, passed as supported_goal. Results are paginated with a limit of 1 to 100 relationships per page. Read-only. It does not create or "
        "remove relationships and for the details of one use asana.goal_relationships.get."
    ),
    examples=[{"name": "default", "input": {"supported_goal": "1200000000005300"}, "output": {
        "items": [{"gid": "1200000000005400", "resource_subtype": "subgoal", "supported_goal": "1200000000005300",
                   "supporting_resource": "1200000000005401", "contribution_weight": 1.0}],
        "has_more": False, "next_offset": None}}],
)
async def goal_relationships_list(ctx: Context, args: GoalRelationshipsListIn) -> GoalRelationshipList:
    params = {"limit": args.limit, "supported_goal": args.supported_goal,
              "opt_fields": "resource_subtype,supported_goal.name,supporting_resource.name,contribution_weight"}
    if args.offset:
        params["offset"] = args.offset
    if args.resource_subtype:
        params["resource_subtype"] = args.resource_subtype
    body = await _get_body(ctx, "/goal_relationships", params=params)
    return _goal_relationship_list(body)


class GoalRelationshipGetIn(BaseModel):
    goal_relationship_gid: str = Field(description="Gid of the goal relationship to fetch")


@function(
    id="asana.goal_relationships.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["goals:read"],
    description=(
        "Returns the details of a single Asana goal relationship: its gid, its subtype, the gid of the goal that receives the support, the gid "
        "of the supporting resource and the contribution weight. A goal relationship connects a goal with the goals, projects or tasks that "
        "support it. Use it when the user references a relationship directly, for example before updating or removing it. It requires only the "
        "relationship gid. Read-only. It does not modify the relationship and it does not list the relationships of a goal (use "
        "asana.goal_relationships.list)."
    ),
    examples=[{"name": "default", "input": {"goal_relationship_gid": "1200000000005400"}, "output": {
        "gid": "1200000000005400", "resource_subtype": "subgoal", "supported_goal": "1200000000005300",
        "supporting_resource": "1200000000005401", "contribution_weight": 1.0}}],
)
async def goal_relationships_get(ctx: Context, args: GoalRelationshipGetIn) -> GoalRelationshipItem:
    body = await _get_body(ctx, f"/goal_relationships/{args.goal_relationship_gid}",
                           params={"opt_fields": "resource_subtype,supported_goal.name,supporting_resource.name,contribution_weight"})
    return _goal_relationship_item(body.get("data") or {})


# --- asana.project_templates --------------------------------------------------------------------

class ProjectTemplateItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project template")
    name: str = Field(description="Name of the project template")
    team: Optional[str] = Field(default=None, description="Gid of the team that owns the template, when there is one")


class ProjectTemplateList(BaseModel):
    items: list[ProjectTemplateItem] = Field(description="Project templates returned in this page")
    has_more: bool = Field(description="True when there are more templates than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of templates")


def _project_template_item(raw: dict) -> ProjectTemplateItem:
    return ProjectTemplateItem(gid=str(raw["gid"]), name=raw.get("name", ""), team=_nested_gid(raw, "team"))


def _project_template_list(body: dict) -> ProjectTemplateList:
    data = body.get("data") or []
    return ProjectTemplateList(items=[_project_template_item(i) for i in data], has_more=bool(body.get("next_page")),
                               next_offset=_next_offset(body))


class ProjectTemplatesListIn(BaseModel):
    workspace: Optional[str] = Field(default=None, description="Gid of a regular workspace whose project templates should be listed; Asana rejects an organization (domain) here, so use team instead")
    team: Optional[str] = Field(default=None, description="Gid of the team whose project templates should be listed; the way to list them in an organization")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")

    @model_validator(mode="after")
    def _needs_a_scope(self):
        if not (self.workspace or self.team):
            raise ValueError("Provide workspace (a regular workspace) or team (the way to list templates in an organization)")
        return self


@function(
    id="asana.project_templates.list", version=2, verb=Verb.read, upstream_api="1.0", scopes=["project_templates:read"],
    description=(
        "Lists the Asana project templates of a workspace or team: each template reports its gid, its name and the gid of the team that "
        "owns it. Project templates are reusable starting points that create projects with a predefined setup. Use it when the user asks which "
        "templates exist or needs a template gid before reading its details. Give workspace (a regular workspace) or team; in an organization "
        "(a company domain) Asana only accepts team. Results are "
        "paginated with a limit of 1 to 100 templates per page. Read-only. It does not create or instantiate projects and to read one template "
        "in depth use asana.project_templates.get, or asana.project_templates.list_team to scope to a team."
    ),
    examples=[{"name": "default", "input": {"team": "1200000000000800"}, "output": {
        "items": [{"gid": "1200000000005500", "name": "Onboarding", "team": "1200000000000800"}],
        "has_more": False, "next_offset": None}}],
)
async def project_templates_list(ctx: Context, args: ProjectTemplatesListIn) -> ProjectTemplateList:
    params = {"limit": args.limit, "opt_fields": "name,team.name"}
    if args.workspace:
        params["workspace"] = args.workspace
    if args.offset:
        params["offset"] = args.offset
    if args.team:
        params["team"] = args.team
    body = await _get_body(ctx, "/project_templates", params=params)
    return _project_template_list(body)


class ProjectTemplateGetIn(BaseModel):
    project_template_gid: str = Field(description="Gid of the project template to fetch")


class ProjectTemplateDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project template")
    name: str = Field(description="Name of the project template")
    team: Optional[str] = Field(default=None, description="Gid of the team that owns the template, when there is one")
    description: Optional[str] = Field(default=None, description="Short description of the project template")
    public: Optional[bool] = Field(default=None, description="True when the template is public and can be discovered by other users")
    color: Optional[str] = Field(default=None, description="Color of the project template, for example 'light-blue', when one is set")


@function(
    id="asana.project_templates.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["project_templates:read"],
    description=(
        "Returns the details of a single Asana project template: its gid, its name, the gid of the team that owns it, its description, whether "
        "it is public and its color. Project templates are reusable starting points that create projects with a predefined setup. Use it when "
        "the user references a template directly, for example to read its description or to know which team it belongs to. It requires only the "
        "template gid. Read-only. Note that project templates do not expose a creation date. It does not instantiate a project and to list "
        "templates use asana.project_templates.list or asana.project_templates.list_team."
    ),
    examples=[{"name": "default", "input": {"project_template_gid": "1200000000005500"}, "output": {
        "gid": "1200000000005500", "name": "Onboarding", "team": "1200000000000800", "description": "Plantilla de onboarding",
        "public": True, "color": "light-blue"}}],
)
async def project_templates_get(ctx: Context, args: ProjectTemplateGetIn) -> ProjectTemplateDetail:
    body = await _get_body(ctx, f"/project_templates/{args.project_template_gid}",
                           params={"opt_fields": "name,team.name,description,public,color"})
    data = body.get("data") or {}
    return ProjectTemplateDetail(gid=str(data["gid"]), name=data.get("name", ""), team=_nested_gid(data, "team"),
                                 description=data.get("description"), public=data.get("public"), color=data.get("color"))


class ProjectTemplatesForTeamIn(BaseModel):
    team_gid: str = Field(description="Gid of the team whose project templates should be listed")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.project_templates.list_team", version=1, verb=Verb.read, upstream_api="1.0", scopes=["project_templates:read"],
    description=(
        "Lists the Asana project templates that belong to a team: each template reports its gid, its name and the gid of the team that owns it. "
        "Use it when the user asks for the templates of a team or department, for example 'which templates does the Producto team have?', or "
        "needs a template gid scoped to a team. It requires the team gid; the endpoint is GET /teams/{team_gid}/project_templates. Results are "
        "paginated with a limit of 1 to 100 templates per page. Read-only. It does not create templates and to search across a whole workspace "
        "use asana.project_templates.list, or to read one template use asana.project_templates.get."
    ),
    examples=[{"name": "default", "input": {"team_gid": "1200000000000800"}, "output": {
        "items": [{"gid": "1200000000005500", "name": "Onboarding", "team": "1200000000000800"}],
        "has_more": False, "next_offset": None}}],
)
async def project_templates_list_team(ctx: Context, args: ProjectTemplatesForTeamIn) -> ProjectTemplateList:
    body = await _get_body(ctx, f"/teams/{args.team_gid}/project_templates",
                           params={"limit": args.limit, **({"offset": args.offset} if args.offset else {}), "opt_fields": "name,team.name"})
    return _project_template_list(body)


# --- asana.task_templates -----------------------------------------------------------------------

class TaskTemplateItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the task template")
    name: str = Field(description="Name of the task template")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the task template was created")
    project: Optional[str] = Field(default=None, description="Gid of the project that contains the task template")


class TaskTemplateList(BaseModel):
    items: list[TaskTemplateItem] = Field(description="Task templates returned in this page")
    has_more: bool = Field(description="True when there are more templates than were returned and a next page can be requested")
    next_offset: Optional[str] = Field(default=None, description="Offset token to pass as input to request the next page of templates")


def _task_template_item(raw: dict) -> TaskTemplateItem:
    return TaskTemplateItem(gid=str(raw["gid"]), name=raw.get("name", ""), created_at=raw.get("created_at"),
                            project=_nested_gid(raw, "project"))


def _task_template_list(body: dict) -> TaskTemplateList:
    data = body.get("data") or []
    return TaskTemplateList(items=[_task_template_item(i) for i in data], has_more=bool(body.get("next_page")),
                            next_offset=_next_offset(body))


class TaskTemplatesListIn(BaseModel):
    project: str = Field(description="Gid of the project to filter task templates on (the API requires it)")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.task_templates.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["task_templates:read"],
    description=(
        "Lists the Asana task templates of a project: each template reports its gid, its name, when it was created and the gid of the project "
        "that contains it. Task templates are reusable setups that create new tasks with a predefined configuration, such as followers, "
        "dependencies or custom fields. Use it when the user asks which templates a project has or needs a template gid before reading its "
        "details. The API requires the project gid. Results are paginated with a limit of 1 to 100 templates per page. Read-only. It does not "
        "create templates or instantiate tasks and to read one template use asana.task_templates.get."
    ),
    examples=[{"name": "default", "input": {"project": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000005600", "name": "Bug reporte", "created_at": "2026-01-01T10:00:00Z", "project": "1200000000000100"}],
        "has_more": False, "next_offset": None}}],
)
async def task_templates_list(ctx: Context, args: TaskTemplatesListIn) -> TaskTemplateList:
    params = {"limit": args.limit, "project": args.project, "opt_fields": "name,created_at,project.name"}
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, "/task_templates", params=params)
    return _task_template_list(body)


class TaskTemplateGetIn(BaseModel):
    task_template_gid: str = Field(description="Gid of the task template to fetch")


class TaskTemplateDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the task template")
    name: str = Field(description="Name of the task template")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the task template was created")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who created the task template, when known")
    project: Optional[str] = Field(default=None, description="Gid of the project that contains the task template")


@function(
    id="asana.task_templates.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["task_templates:read"],
    description=(
        "Returns the details of a single Asana task template: its gid, its name, when it was created, who created it and the gid of the project "
        "that contains it. Task templates are reusable setups that create new tasks with a predefined configuration. Use it when the user "
        "references a template directly, for example to confirm who created it or which project it belongs to before instantiating a task. It "
        "requires only the template gid. Read-only. It does not instantiate a task and it does not list the templates of a project (use "
        "asana.task_templates.list)."
    ),
    examples=[{"name": "default", "input": {"task_template_gid": "1200000000005600"}, "output": {
        "gid": "1200000000005600", "name": "Bug reporte", "created_at": "2026-01-01T10:00:00Z",
        "created_by": "1200000000000001", "project": "1200000000000100"}}],
)
async def task_templates_get(ctx: Context, args: TaskTemplateGetIn) -> TaskTemplateDetail:
    body = await _get_body(ctx, f"/task_templates/{args.task_template_gid}",
                           params={"opt_fields": "name,created_at,created_by.name,project.name"})
    data = body.get("data") or {}
    return TaskTemplateDetail(gid=str(data["gid"]), name=data.get("name", ""), created_at=data.get("created_at"),
                              created_by=_nested_gid(data, "created_by"), project=_nested_gid(data, "project"))


# --- Tarea 6: Status updates, Memberships, Time tracking, Webhooks, Audit log y Organization exports -------------
#
# Verificado en developers.asana.com/reference y en el SDK oficial python-asana (raw.githubusercontent.com/Asana/
# python-asana/master/docs/, 2026-10-07). Correcciones y aclaraciones respecto al catalogo ATENCION/tareas/asana.md:
# - asana.status_updates.list: NO existe GET /{resource_type}/{resource_gid}/status_updates; el endpoint real es
#   GET /status_updates con el query param obligatorio `parent` (gid de un project, portfolio o goal). Se filtra por
#   `parent`, no por parent_resource_type. Permite ademas `created_since`. NO existe scope granular `status_updates:read`
#   en Asana (el openapi declara oauth2: []); se usan scopes=().
# - asana.memberships.list/get: NO existe scope `memberships:read`; scopes=(). El cat�logo pasaba parent_gid +
#   parent_resource_type, pero el endpoint exige el query param `parent` (un solo gid) o bien member+resource_subtype.
#   El campo de nivel NO es `role` sino `access_level`.
# - asana.time_tracking_entries.*: el scope real es `time_tracking_entries:read` (no `time_tracking:read`). En las
#   respuestas de listados NO hay `user` ni `spent_at`: el creador es `created_by` y la fecha es `entered_on`.
#   asana.time_tracking_entries.list filtra por `user`/`workspace`/`task`/`attributable_to`/`portfolio` y rangos
#   entered_on_start_date/entered_on_end_date (el catalogo pedia from/to).
# - asana.time_tracking_categories.list: el endpoint real es GET /time_tracking_categories?workspace={gid} (no
#   /workspaces/{workspace_gid}/time_tracking_categories). Campos reales: gid, name, color, is_archived (no
#   enabled/created_at). Scope real `time_tracking_categories:read`. La variante list_entries usa
#   GET /time_tracking_categories/{category_gid}/time_tracking_entries con el mismo scope y params start_date/end_date.
# - asana.webhooks.list/get: scope real `webhooks:read`. webhooks.list NO tiene rango sin query: exige `workspace` y
#   acepta `resource`. Campos: active, created_at, delivery_retry_count, filters, last_success_at, last_failure_at,
#   next_attempt_after, resource.name, target.
# - asana.audit_log.list: NO existe scope granular `audit_log:read` (oauth2: []). Solo un Service Account con PAT de
#   Asana Enterprise+ puede leerlo. Ruta confirmada GET /workspaces/{workspace_gid}/audit_log_events con filtros
#   start_at/end_at/event_type/actor_type/actor_gid/resource_gid y paginacion por offset (default 1000 eventos).
# - asana.organization_exports.get: campos reales state, created_at, download_url y organization (no `url` ni `gid`
#   de descarga). Sin scope granular (oauth2: []); scopes=().

# --- asana.status_updates -----------------------------------------------------------------------------------------


class StatusUpdatesListIn(BaseModel):
    parent: str = Field(description="Gid of the project, portfolio or goal to read the status updates of (required; Asana has no endpoint per resource type)")
    created_since: Optional[str] = Field(default=None, description="Returns only status updates created after this time in UTC, ISO 8601 format, for example 2026-01-01T00:00:00Z")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


class StatusUpdateItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the status update")
    title: Optional[str] = Field(default=None, description="Title of the status update")
    resource_subtype: str = Field(description="Type of status update: 'project_status_update', 'portfolio_status_update' or 'goal_status_update'")
    status_type: Optional[str] = Field(default=None, description="Numeric progress: 'on_track', 'off_track', 'at_risk', 'on_hold' or 'in_progress'")
    text: Optional[str] = Field(default=None, description="Text of the status update")
    html_text: Optional[str] = Field(default=None, description="HTML representation of the text of the status update")
    author: Optional[str] = Field(default=None, description="Gid of the user who wrote the status update")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the status update was created")
    parent: Optional[str] = Field(default=None, description="Gid of the project, portfolio or goal this status update belongs to")


class StatusUpdateList(BaseModel):
    items: list[StatusUpdateItem] = Field(description="Status updates of the requested parent, most recent first")
    has_more: bool = Field(description="True when more status updates are available in the next page")
    next_offset: Optional[str] = Field(default=None, description="Cursor to pass as `offset` to fetch the next page, or null when there are no more results")


@function(
    id="asana.status_updates.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the status updates posted in an Asana project, portfolio or goal: each update reports its gid, title, type "
        "and numeric progress status, the plain text and HTML text of the message, who wrote it, when it was created and "
        "the gid of its parent. Asana does not expose a separate endpoint per resource type, so a single `parent` gid is "
        "required; use it when the user asks what status updates a project, portfolio or goal has or which one was the last "
        "posted. Results are paginated with a limit of 1 to 100 updates per page and `created_since` filters by creation "
        "time. Read-only. It does not post status updates and to read one update use asana.status_updates.get."
    ),
    examples=[{"name": "default", "input": {"parent": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000006000", "title": "Ronda 1", "resource_subtype": "project_status_update",
                   "status_type": "on_track", "text": "Todo en fecha", "html_text": "<body>Todo en fecha</body>",
                   "author": "1200000000000001", "created_at": "2026-01-01T10:00:00Z", "parent": "1200000000000100"}],
        "has_more": False, "next_offset": None}}],
)
async def status_updates_list(ctx: Context, args: StatusUpdatesListIn) -> StatusUpdateList:
    params = {"limit": args.limit, "parent": args.parent,
              "opt_fields": "title,resource_subtype,status_type,text,html_text,author.name,created_at,parent.name"}
    if args.created_since:
        params["created_since"] = args.created_since
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, "/status_updates", params=params)
    return StatusUpdateList(items=[
        StatusUpdateItem(gid=str(item["gid"]), title=item.get("title"), resource_subtype=item.get("resource_subtype", ""),
                         status_type=item.get("status_type"), text=item.get("text"), html_text=item.get("html_text"),
                         author=_nested_gid(item, "author"), created_at=item.get("created_at"), parent=_nested_gid(item, "parent"))
        for item in body.get("data", [])], has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


class StatusUpdateGetIn(BaseModel):
    status_update_gid: str = Field(description="Gid of the status update to fetch")


class StatusUpdateDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the status update")
    title: Optional[str] = Field(default=None, description="Title of the status update")
    resource_subtype: str = Field(description="Type of status update: 'project_status_update', 'portfolio_status_update' or 'goal_status_update'")
    status_type: Optional[str] = Field(default=None, description="Numeric progress: 'on_track', 'off_track', 'at_risk', 'on_hold' or 'in_progress'")
    text: Optional[str] = Field(default=None, description="Text of the status update")
    html_text: Optional[str] = Field(default=None, description="HTML representation of the text of the status update")
    author: Optional[str] = Field(default=None, description="Gid of the user who wrote the status update")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the status update was created")
    modified_at: Optional[str] = Field(default=None, description="UTC date and time when the status update was last modified")
    parent: Optional[str] = Field(default=None, description="Gid of the project, portfolio or goal this status update belongs to")


@function(
    id="asana.status_updates.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns the details of a single Asana status update: its gid, title, resource type and numeric progress status, "
        "its plain text and HTML text, who wrote it, when it was created and last modified and the gid of its parent. "
        "Use it when the user references a specific status update and needs to read its full message or confirm who "
        "posted it and when, for example to check the last project progress report. It requires only the status update "
        "gid. Read-only. It does not create or edit status updates and to list the updates of a project, portfolio or "
        "goal use asana.status_updates.list."
    ),
    examples=[{"name": "default", "input": {"status_update_gid": "1200000000006000"}, "output": {
        "gid": "1200000000006000", "title": "Ronda 1", "resource_subtype": "project_status_update",
        "status_type": "on_track", "text": "Todo en fecha", "html_text": "<body>Todo en fecha</body>",
        "author": "1200000000000001", "created_at": "2026-01-01T10:00:00Z", "modified_at": "2026-01-01T10:00:00Z",
        "parent": "1200000000000100"}}],
)
async def status_updates_get(ctx: Context, args: StatusUpdateGetIn) -> StatusUpdateDetail:
    body = await _get_body(ctx, f"/status_updates/{args.status_update_gid}",
                           params={"opt_fields": "title,resource_subtype,status_type,text,html_text,author.name,created_at,modified_at,parent.name"})
    data = body.get("data") or {}
    return StatusUpdateDetail(gid=str(data["gid"]), title=data.get("title"), resource_subtype=data.get("resource_subtype", ""),
                              status_type=data.get("status_type"), text=data.get("text"), html_text=data.get("html_text"),
                              author=_nested_gid(data, "author"), created_at=data.get("created_at"),
                              modified_at=data.get("modified_at"), parent=_nested_gid(data, "parent"))


# --- asana.memberships --------------------------------------------------------------------------------------------


class MembershipsListIn(BaseModel):
    parent: str = Field(description="Gid of the goal, project, portfolio, custom type or custom field to read the memberships of (a single gid; Asana filters by this query)")
    member: Optional[str] = Field(default=None, description="If provided, returns only memberships whose member is this user gid, 'me' or an email")
    resource_subtype: Optional[str] = Field(default=None, description="If provided, limits results to memberships of this subtype: project_membership, portfolio_membership, goal_membership, custom_type_membership or custom_field_membership")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


class MembershipMember(BaseModel):
    gid: str = Field(description="Asana gid of the member")
    name: Optional[str] = Field(default=None, description="Name of the member")
    resource_type: Optional[str] = Field(default=None, description="Asana resource type of the member: user, team or custom field, for example")


class MembershipItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the membership")
    resource_type: Optional[str] = Field(default=None, description="Top level resource type: always 'membership'")
    resource_subtype: Optional[str] = Field(default=None, description="Kind of membership: 'project_membership', 'portfolio_membership', 'goal_membership', 'custom_type_membership' or 'custom_field_membership'")
    member: Optional[MembershipMember] = Field(default=None, description="Member of the membership: user, team or custom field, with gid and name")
    parent: Optional[str] = Field(default=None, description="Gid of the project, portfolio, goal or custom field the membership belongs to")
    access_level: Optional[str] = Field(default=None, description="Permission level granted to the member: commenter, editor, admin, full_access, can_edit, can_comment, custom_field_access_*... Asana calls this access_level, not role")


class MembershipList(BaseModel):
    items: list[MembershipItem] = Field(description="Memberships matching the requested filters")
    has_more: bool = Field(description="True when more memberships are available in the next page")
    next_offset: Optional[str] = Field(default=None, description="Cursor to pass as `offset` to fetch the next page, or null when there are no more results")


@function(
    id="asana.memberships.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the memberships of an Asana goal, project, portfolio, custom type or custom field: each item reports its "
        "gid, its subtype, the member with gid and name, the gid of its parent and the access level granted. A membership "
        "links who can work on a resource and with which permission, so use it to answer who is a member or collaborator "
        "of a resource and which access they have. Provide a single `parent` gid (the API has no parent_resource_type "
        "parameter) or combine `member` and `resource_subtype` to filter the other way. Results are paginated with a "
        "limit of 1 to 100 memberships per page. Read-only. To read one membership use asana.memberships.get."
    ),
    examples=[{"name": "default", "input": {"parent": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000006100", "resource_type": "membership", "resource_subtype": "project_membership",
                   "member": {"gid": "1200000000000001", "name": "Ana Perez", "resource_type": "user"},
                   "parent": "1200000000000100", "access_level": "admin"}],
        "has_more": False, "next_offset": None}}],
)
async def memberships_list(ctx: Context, args: MembershipsListIn) -> MembershipList:
    params = {"limit": args.limit, "parent": args.parent,
              "opt_fields": "resource_subtype,member.name,member.resource_type,parent.name,access_level"}
    if args.member:
        params["member"] = args.member
    if args.resource_subtype:
        params["resource_subtype"] = args.resource_subtype
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, "/memberships", params=params)
    return MembershipList(items=[
        MembershipItem(gid=str(item["gid"]), resource_type=item.get("resource_type"), resource_subtype=item.get("resource_subtype"),
                       member=MembershipMember(gid=str(me["gid"]), name=me.get("name"), resource_type=me.get("resource_type")) if (me := item.get("member")) else None,
                       parent=_nested_gid(item, "parent"), access_level=item.get("access_level"))
        for item in body.get("data", [])], has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


class MembershipGetIn(BaseModel):
    membership_gid: str = Field(description="Gid of the membership to fetch")


@function(
    id="asana.memberships.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns the details of a single Asana membership: its gid, its subtype, the member with gid and name, the gid "
        "of its parent and the access level granted to that member. A membership joins a member (user, team or custom "
        "field) with a goal, project, portfolio or custom field, so use it when the user references a specific "
        "membership, for example to confirm the permission a coworker has on a project or goal. It requires only the "
        "membership gid. Read-only. It does not grant or revoke access and to list memberships use asana.memberships.list."
    ),
    examples=[{"name": "default", "input": {"membership_gid": "1200000000006100"}, "output": {
        "gid": "1200000000006100", "resource_type": "membership", "resource_subtype": "project_membership",
        "member": {"gid": "1200000000000001", "name": "Ana Perez", "resource_type": "user"},
        "parent": "1200000000000100", "access_level": "admin"}}],
)
async def memberships_get(ctx: Context, args: MembershipGetIn) -> MembershipItem:
    body = await _get_body(ctx, f"/memberships/{args.membership_gid}",
                           params={"opt_fields": "resource_subtype,member.name,member.resource_type,parent.name,access_level"})
    data = body.get("data") or {}
    member = data.get("member")
    return MembershipItem(gid=str(data["gid"]), resource_type=data.get("resource_type"), resource_subtype=data.get("resource_subtype"),
                          member=MembershipMember(gid=str(member["gid"]), name=member.get("name"), resource_type=member.get("resource_type")) if member else None,
                          parent=_nested_gid(data, "parent"), access_level=data.get("access_level"))


# --- asana.time_tracking_entries ----------------------------------------------------------------------------------


class TimeTrackingCategoryRef(BaseModel):
    gid: str = Field(description="Asana gid of the time tracking category")
    name: str = Field(description="Name of the time tracking category, for example 'Development'")
    color: Optional[str] = Field(default=None, description="Color of the category")


class TimeTrackingEntryItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the time tracking entry")
    duration_minutes: int = Field(description="Time spent, in whole minutes, reported by the entry")
    entered_on: Optional[str] = Field(default=None, description="Day the entry is for, in YYYY-MM-DD format (Asana has no spent_at field)")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who entered the time (the author, not a 'user' field)")
    attributable_to: Optional[str] = Field(default=None, description="Gid of the project the time is attributed to, when the task belongs to one")
    categories: list[TimeTrackingCategoryRef] = Field(default_factory=list, description="Categories the entry is classified into, each with gid, name and color")


class TimeTrackingEntryDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the time tracking entry")
    description: Optional[str] = Field(default=None, description="Optional note explaining what the time was spent on")
    duration_minutes: int = Field(description="Time spent, in whole minutes, reported by the entry")
    entered_on: Optional[str] = Field(default=None, description="Day the entry is for, in YYYY-MM-DD format")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the entry was created")
    approval_status: Optional[str] = Field(default=None, description="Timesheet approval state: approved, pending or rejected")
    billable_status: Optional[str] = Field(default=None, description="Whether the entry is billable: billable, unbillable or non_billable")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who entered the time")
    task: Optional[str] = Field(default=None, description="Gid of the task the entry was reported on")
    attributable_to: Optional[str] = Field(default=None, description="Gid of the project the time is attributed to")
    categories: list[TimeTrackingCategoryRef] = Field(default_factory=list, description="Categories the entry is classified into")


class TimeTrackingEntryList(BaseModel):
    items: list[TimeTrackingEntryItem] = Field(description="Time tracking entries of the requested task, user or category")
    has_more: bool = Field(description="True when more entries are available in the next page")
    next_offset: Optional[str] = Field(default=None, description="Cursor to pass as `offset` to fetch the next page, or null when there are no more results")


_TIME_FIELDS = "duration_minutes,entered_on,created_by.name,attributable_to.name,attributable_to.resource_subtype,categories.name,categories.color"


def _entry_item(raw: dict) -> TimeTrackingEntryItem:
    return TimeTrackingEntryItem(gid=str(raw["gid"]), duration_minutes=int(raw.get("duration_minutes") or 0),
                                 entered_on=raw.get("entered_on"), created_by=_nested_gid(raw, "created_by"),
                                 attributable_to=_nested_gid(raw, "attributable_to"),
                                 categories=[TimeTrackingCategoryRef(gid=str(c["gid"]), name=c.get("name", ""), color=c.get("color"))
                                             for c in raw.get("categories", [])])


class TimeTrackTaskIn(BaseModel):
    task_gid: str = Field(description="Gid of the task to read the time tracking entries of")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.time_tracking_entries.list_task", version=1, verb=Verb.read, upstream_api="1.0", scopes=["time_tracking_entries:read"],
    description=(
        "Lists the time tracking entries reported on an Asana task: each entry reports how many minutes were spent, the "
        "day it is for, who entered the time, the project it is attributed to and the categories it was classified "
        "into. Use it when the user asks how much time was logged on a task, who logged it or how the hours are split "
        "into categories, for example to review the effort of a task before billing it. The API requires the task gid. "
        "Results are paginated with a limit of 1 to 100 entries per page and each entry is returned most recent first. "
        "Read-only. It does not add time and to read one entry use asana.time_tracking_entries.get."
    ),
    examples=[{"name": "default", "input": {"task_gid": "1200000000000500"}, "output": {
        "items": [{"gid": "1200000000006200", "duration_minutes": 150, "entered_on": "2026-10-05",
                   "created_by": "1200000000000001", "attributable_to": "1200000000000100",
                   "categories": [{"gid": "1200000000006300", "name": "Development", "color": "blue"}]}],
        "has_more": False, "next_offset": None}}],
)
async def time_tracking_entries_list_task(ctx: Context, args: TimeTrackTaskIn) -> TimeTrackingEntryList:
    params = {"limit": args.limit, "opt_fields": _TIME_FIELDS}
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, f"/tasks/{args.task_gid}/time_tracking_entries", params=params)
    return TimeTrackingEntryList(items=[_entry_item(item) for item in body.get("data", [])],
                                 has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


class TimeTrackGetIn(BaseModel):
    entry_gid: str = Field(description="Gid of the time tracking entry to fetch")


@function(
    id="asana.time_tracking_entries.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["time_tracking_entries:read"],
    description=(
        "Returns the details of a single Asana time tracking entry: the minutes spent, the day it was entered for, an "
        "optional description, its approval and billable status, who entered the time, the task it belongs to, the "
        "project it is attributed to and the categories it was classified into. Use it when the user references a "
        "specific time entry to verify how it was logged, approve or dispute hours or pass the details to billing. It "
        "requires only the entry gid. Read-only. It does not modify or delete the entry and to list the entries of a "
        "task use asana.time_tracking_entries.list_task."
    ),
    examples=[{"name": "default", "input": {"entry_gid": "1200000000006200"}, "output": {
        "gid": "1200000000006200", "description": "Payment flow design", "duration_minutes": 150,
        "entered_on": "2026-10-05", "created_at": "2026-10-05T12:00:00Z", "approval_status": "approved",
        "billable_status": "billable", "created_by": "1200000000000001", "task": "1200000000000500",
        "attributable_to": "1200000000000100",
        "categories": [{"gid": "1200000000006300", "name": "Development", "color": "blue"}]}}],
)
async def time_tracking_entries_get(ctx: Context, args: TimeTrackGetIn) -> TimeTrackingEntryDetail:
    body = await _get_body(ctx, f"/time_tracking_entries/{args.entry_gid}",
                           params={"opt_fields": "description,duration_minutes,entered_on,created_at,approval_status,billable_status,created_by.name,task.name,task.resource_subtype,attributable_to.name,attributable_to.resource_subtype,categories.name,categories.color"})
    data = body.get("data") or {}
    return TimeTrackingEntryDetail(gid=str(data["gid"]), description=data.get("description"),
                                   duration_minutes=int(data.get("duration_minutes") or 0), entered_on=data.get("entered_on"),
                                   created_at=data.get("created_at"), approval_status=data.get("approval_status"),
                                   billable_status=data.get("billable_status"), created_by=_nested_gid(data, "created_by"),
                                   task=_nested_gid(data, "task"), attributable_to=_nested_gid(data, "attributable_to"),
                                   categories=[TimeTrackingCategoryRef(gid=str(c["gid"]), name=c.get("name", ""), color=c.get("color"))
                                               for c in data.get("categories", [])])


class TimeTrackListIn(BaseModel):
    workspace_gid: Optional[str] = Field(default=None, description="Gid of the workspace whose time tracking entries to list; Asana needs this or task_gid to know where to look")
    task_gid: Optional[str] = Field(default=None, description="Gid of a task; lists only the time tracking entries logged on that task (an alternative to workspace_gid)")
    user_gid: Optional[str] = Field(default=None, description="Optional Asana user to filter the entries by: their gid, 'me' or an email; the API sends this as the `user` query")
    entered_on_start_date: Optional[str] = Field(default=None, description="Received entries from this day onwards, inclusive, in YYYY-MM-DD format")
    entered_on_end_date: Optional[str] = Field(default=None, description="Received entries until this day, inclusive, in YYYY-MM-DD format")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")

    @model_validator(mode="after")
    def _needs_a_scope(self):
        if not (self.workspace_gid or self.task_gid):
            raise ValueError("Provide workspace_gid or task_gid so Asana knows where to look for the time tracking entries")
        return self


@function(
    id="asana.time_tracking_entries.list", version=2, verb=Verb.read, upstream_api="1.0", scopes=["time_tracking_entries:read"],
    description=(
        "Lists the time tracking entries of an Asana workspace or task, optionally filtered by user and by the days they were entered for: each "
        "entry reports how many minutes were spent, the day it is for, who entered the time, the project it is "
        "attributed to and the categories it was classified into. Use it when the user asks how many hours a teammate "
        "logged in a period, for example daily or monthly effort for payroll or billing. Give workspace_gid (or task_gid) and, to keep one person, "
        "user_gid: their gid, 'me' or an email. The date range uses entered_on_start_date and entered_on_end_date in YYYY-MM-DD format. "
        "Results are paginated with a limit of 1 to 100 entries per page. Read-only. It does not add or edit time."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "user_gid": "me", "entered_on_start_date": "2026-10-01", "entered_on_end_date": "2026-10-31"}, "output": {
        "items": [{"gid": "1200000000006200", "duration_minutes": 150, "entered_on": "2026-10-05",
                   "created_by": "1200000000000001", "attributable_to": "1200000000000100",
                   "categories": [{"gid": "1200000000006300", "name": "Development", "color": "blue"}]}],
        "has_more": False, "next_offset": None}}],
)
async def time_tracking_entries_list(ctx: Context, args: TimeTrackListIn) -> TimeTrackingEntryList:
    params = {"limit": args.limit, "opt_fields": _TIME_FIELDS}
    for key, value in (("workspace", args.workspace_gid), ("task", args.task_gid), ("user", args.user_gid)):
        if value:
            params[key] = value
    if args.entered_on_start_date:
        params["entered_on_start_date"] = args.entered_on_start_date
    if args.entered_on_end_date:
        params["entered_on_end_date"] = args.entered_on_end_date
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, "/time_tracking_entries", params=params)
    return TimeTrackingEntryList(items=[_entry_item(item) for item in body.get("data", [])],
                                 has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


# --- asana.time_tracking_categories -------------------------------------------------------------------------------


class TimeTrackCatListIn(BaseModel):
    workspace: str = Field(description="Gid of the workspace or organization to read the time tracking categories of (the endpoint filters by the `workspace` query)")
    is_archived: Optional[bool] = Field(default=None, description="If true, returns only archived categories; if false, only active ones; if omitted, returns all")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


class TimeTrackingCategoryItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the time tracking category")
    name: str = Field(description="Name of the category, for example 'Development'")
    color: Optional[str] = Field(default=None, description="Color of the category, from a fixed set such as blue, green, red or yellow")
    is_archived: Optional[bool] = Field(default=None, description="Whether the category is archived and can no longer be used on new entries")


class TimeTrackingCategoryList(BaseModel):
    items: list[TimeTrackingCategoryItem] = Field(description="Time tracking categories of the workspace")
    has_more: bool = Field(description="True when more categories are available in the next page")
    next_offset: Optional[str] = Field(default=None, description="Cursor to pass as `offset` to fetch the next page, or null when there are no more results")


@function(
    id="asana.time_tracking_categories.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["time_tracking_categories:read"],
    description=(
        "Lists the time tracking categories of an Asana workspace or organization: each category reports its gid, its "
        "name, its color and whether it is archived. Categories group time tracking entries, for example by activity "
        "such as Development or Meetings, so use it when the user asks what categories exist, needs a category gid to "
        "filter entries or wants to know which categories are active. The API requires the workspace gid and filters "
        "by the `workspace` query (there is no per-workspace path). Results are paginated with a limit of 1 to 100 "
        "categories per page. Read-only. To read one category use asana.time_tracking_categories.get."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000006300", "name": "Development", "color": "blue", "is_archived": False}],
        "has_more": False, "next_offset": None}}],
)
async def time_tracking_categories_list(ctx: Context, args: TimeTrackCatListIn) -> TimeTrackingCategoryList:
    params = {"limit": args.limit, "workspace": args.workspace, "opt_fields": "name,color,is_archived"}
    if args.is_archived is not None:
        params["is_archived"] = "true" if args.is_archived else "false"
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, "/time_tracking_categories", params=params)
    return TimeTrackingCategoryList(items=[
        TimeTrackingCategoryItem(gid=str(item["gid"]), name=item.get("name", ""), color=item.get("color"), is_archived=item.get("is_archived"))
        for item in body.get("data", [])], has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


class TimeTrackCatGetIn(BaseModel):
    category_gid: str = Field(description="Gid of the time tracking category to fetch")


@function(
    id="asana.time_tracking_categories.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["time_tracking_categories:read"],
    description=(
        "Returns the details of a single Asana time tracking category: its gid, its name, its color and whether it is "
        "archived. Categories group time tracking entries by activity, so use it when the user references a specific "
        "category and needs to confirm its name, color or active state, for example to classify a new time entry or to "
        "report hours by category. It requires only the category gid. Read-only. It does not create, edit or archive "
        "categories and to list the categories of a workspace use asana.time_tracking_categories.list."
    ),
    examples=[{"name": "default", "input": {"category_gid": "1200000000006300"}, "output": {
        "gid": "1200000000006300", "name": "Development", "color": "blue", "is_archived": False}}],
)
async def time_tracking_categories_get(ctx: Context, args: TimeTrackCatGetIn) -> TimeTrackingCategoryItem:
    body = await _get_body(ctx, f"/time_tracking_categories/{args.category_gid}",
                           params={"opt_fields": "name,color,is_archived"})
    data = body.get("data") or {}
    return TimeTrackingCategoryItem(gid=str(data["gid"]), name=data.get("name", ""), color=data.get("color"),
                                    is_archived=data.get("is_archived"))


class TimeTrackCatEntriesIn(BaseModel):
    category_gid: str = Field(description="Gid of the time tracking category to read the entries of")
    start_date: Optional[str] = Field(default=None, description="Returns only entries entered for days from this date onwards, inclusive, in YYYY-MM-DD format")
    end_date: Optional[str] = Field(default=None, description="Returns only entries entered for days until this date, inclusive, in YYYY-MM-DD format")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


@function(
    id="asana.time_tracking_categories.list_entries", version=1, verb=Verb.read, upstream_api="1.0", scopes=["time_tracking_categories:read"],
    description=(
        "Lists the time tracking entries classified into an Asana time tracking category: each entry reports how many "
        "minutes were spent, the day it is for, who entered the time, the project it is attributed to and the "
        "categories it was classified into. Use it when the user asks how much time was logged in a category, for "
        "example hours invested in Development or in a client project over a period. The API requires the category gid "
        "and supports start_date and end_date filters in YYYY-MM-DD format. Results are paginated with a limit of 1 to "
        "100 entries per page. Read-only. It does not add or edit time entries."
    ),
    examples=[{"name": "default", "input": {"category_gid": "1200000000006300", "start_date": "2026-10-01", "end_date": "2026-10-31"}, "output": {
        "items": [{"gid": "1200000000006200", "duration_minutes": 150, "entered_on": "2026-10-05",
                   "created_by": "1200000000000001", "attributable_to": "1200000000000100",
                   "categories": [{"gid": "1200000000006300", "name": "Development", "color": "blue"}]}],
        "has_more": False, "next_offset": None}}],
)
async def time_tracking_categories_list_entries(ctx: Context, args: TimeTrackCatEntriesIn) -> TimeTrackingEntryList:
    params = {"limit": args.limit, "opt_fields": _TIME_FIELDS}
    if args.start_date:
        params["start_date"] = args.start_date
    if args.end_date:
        params["end_date"] = args.end_date
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, f"/time_tracking_categories/{args.category_gid}/time_tracking_entries", params=params)
    return TimeTrackingEntryList(items=[_entry_item(item) for item in body.get("data", [])],
                                 has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


# --- asana.webhooks -----------------------------------------------------------------------------------------------


class WebhookListIn(BaseModel):
    workspace: str = Field(description="Gid of the workspace or organization to read the webhooks of (required; Asana has no unscoped webhook list)")
    resource: Optional[str] = Field(default=None, description="If provided, returns only webhooks watching this resource gid")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


class WebhookFilter(BaseModel):
    action: Optional[str] = Field(default=None, description="Event action that triggers the webhook: add, changed, removed, deleted, moved or duplicate")
    fields: list[str] = Field(default_factory=list, description="Specific field names the webhook is subscribed to, if any")
    resource_subtype: Optional[str] = Field(default=None, description="Resource subtype the filters apply to, such as task, subtask or project")


class WebhookItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the webhook")
    target: str = Field(description="URL that receives the HTTP POST notification")
    resource: Optional[str] = Field(default=None, description="Gid of the resource the webhook watches")
    active: bool = Field(description="Whether the webhook is receiving deliveries")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the webhook was created")
    last_success_at: Optional[str] = Field(default=None, description="UTC date and time of the last successful delivery")
    last_failure_at: Optional[str] = Field(default=None, description="UTC date and time of the last failed delivery")
    filters: list[WebhookFilter] = Field(default_factory=list, description="Event filters the webhook is subscribed to")


class WebhookList(BaseModel):
    items: list[WebhookItem] = Field(description="Webhooks registered in the requested workspace, optionally for one resource")
    has_more: bool = Field(description="True when more webhooks are available in the next page")
    next_offset: Optional[str] = Field(default=None, description="Cursor to pass as `offset` to fetch the next page, or null when there are no more results")


@function(
    id="asana.webhooks.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["webhooks:read"],
    description=(
        "Lists the webhooks registered in an Asana workspace or organization, optionally filtered to one resource: each "
        "webhook reports its gid, the target URL that receives the notifications, the resource it watches, whether it "
        "is active, when it was created, the last successful and failed delivery and its event filters. Use it to audit "
        "which integrations or bots are subscribed to Asana events, verify a target URL is receiving posts or confirm a "
        "webhook is active on a project or task. The API requires the workspace gid and accepts an optional resource. "
        "Results are paginated with a limit of 1 to 100 webhooks per page. Read-only."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000006400", "target": "https://hooks.ejemplo.com/asana", "resource": "1200000000000100",
                   "active": True, "created_at": "2026-01-01T10:00:00Z", "last_success_at": "2026-01-01T11:00:00Z",
                   "last_failure_at": None, "filters": [{"action": "add", "fields": [], "resource_subtype": "task"}]}],
        "has_more": False, "next_offset": None}}],
)
async def webhooks_list(ctx: Context, args: WebhookListIn) -> WebhookList:
    params = {"limit": args.limit, "workspace": args.workspace,
              "opt_fields": "resource.name,target,active,created_at,last_success_at,last_failure_at,filters.action,filters.fields,filters.resource_subtype"}
    if args.resource:
        params["resource"] = args.resource
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, "/webhooks", params=params)
    return WebhookList(items=[
        WebhookItem(gid=str(item["gid"]), target=item.get("target", ""), resource=_nested_gid(item, "resource"),
                    active=bool(item.get("active")), created_at=item.get("created_at"),
                    last_success_at=item.get("last_success_at"), last_failure_at=item.get("last_failure_at"),
                    filters=[WebhookFilter(action=f.get("action"), fields=f.get("fields", []), resource_subtype=f.get("resource_subtype"))
                             for f in item.get("filters", [])])
        for item in body.get("data", [])], has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


class WebhookGetIn(BaseModel):
    webhook_gid: str = Field(description="Gid of the webhook to fetch")


class WebhookDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the webhook")
    target: str = Field(description="URL that receives the HTTP POST notification")
    resource: Optional[str] = Field(default=None, description="Gid of the resource the webhook watches")
    active: bool = Field(description="Whether the webhook is receiving deliveries")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the webhook was created")
    last_success_at: Optional[str] = Field(default=None, description="UTC date and time of the last successful delivery")
    last_failure_at: Optional[str] = Field(default=None, description="UTC date and time of the last failed delivery")
    next_attempt_after: Optional[str] = Field(default=None, description="UTC date and time of the next delivery attempt after a failure")
    delivery_retry_count: int = Field(description="How many times Asana retried a failed delivery")
    filters: list[WebhookFilter] = Field(default_factory=list, description="Event filters the webhook is subscribed to")


@function(
    id="asana.webhooks.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["webhooks:read"],
    description=(
        "Returns the details of a single Asana webhook: its gid, the target URL that receives the notifications, the "
        "resource it watches, whether it is active, when it was created, the last successful and failed delivery, when "
        "the next retry is scheduled and how many times a delivery was retried. Use it when the user references a "
        "specific webhook, for example to confirm an integration stopped receiving events, diagnose delivery failures "
        "or check its event filters. It requires only the webhook gid. Read-only. It does not create, update or delete "
        "webhooks and to list them use asana.webhooks.list."
    ),
    examples=[{"name": "default", "input": {"webhook_gid": "1200000000006400"}, "output": {
        "gid": "1200000000006400", "target": "https://hooks.ejemplo.com/asana", "resource": "1200000000000100",
        "active": True, "created_at": "2026-01-01T10:00:00Z", "last_success_at": "2026-01-01T11:00:00Z",
        "last_failure_at": None, "next_attempt_after": None, "delivery_retry_count": 0,
        "filters": [{"action": "add", "fields": [], "resource_subtype": "task"}]}}],
)
async def webhooks_get(ctx: Context, args: WebhookGetIn) -> WebhookDetail:
    body = await _get_body(ctx, f"/webhooks/{args.webhook_gid}",
                           params={"opt_fields": "resource.name,target,active,created_at,last_success_at,last_failure_at,next_attempt_after,delivery_retry_count,filters.action,filters.fields,filters.resource_subtype"})
    data = body.get("data") or {}
    return WebhookDetail(gid=str(data["gid"]), target=data.get("target", ""), resource=_nested_gid(data, "resource"),
                         active=bool(data.get("active")), created_at=data.get("created_at"),
                         last_success_at=data.get("last_success_at"), last_failure_at=data.get("last_failure_at"),
                         next_attempt_after=data.get("next_attempt_after"),
                         delivery_retry_count=int(data.get("delivery_retry_count") or 0),
                         filters=[WebhookFilter(action=f.get("action"), fields=f.get("fields", []), resource_subtype=f.get("resource_subtype"))
                                  for f in data.get("filters", [])])


# --- asana.audit_log ----------------------------------------------------------------------------------------------


class AuditLogListIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization to read the audit log events of")
    event_type: Optional[str] = Field(default=None, description="Comma separated event types to filter by, such as task_deleted or user_login")
    actor_type: Optional[str] = Field(default=None, description="Comma separated actor types to filter by: user, app or task")
    actor_gid: Optional[str] = Field(default=None, description="Gid of the actor (user or app) to filter the events by")
    resource_gid: Optional[str] = Field(default=None, description="Gid of the resource the events concern, such as a task or project")
    start_at: Optional[str] = Field(default=None, description="Returns only events created at or after this UTC time, ISO 8601")
    end_at: Optional[str] = Field(default=None, description="Returns only events created at or before this UTC time, ISO 8601")
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description="Offset token returned by a previous page to continue listing from there")


class AuditLogActor(BaseModel):
    actor_type: Optional[str] = Field(default=None, description="Kind of actor: 'user', 'app' or 'task'")
    gid: Optional[str] = Field(default=None, description="Gid of the actor")
    name: Optional[str] = Field(default=None, description="Name of the actor")
    email: Optional[str] = Field(default=None, description="Email of the actor, when it is a user")


class AuditLogResource(BaseModel):
    resource_type: Optional[str] = Field(default=None, description="Asana resource type of the affected resource, such as task or project")
    resource_subtype: Optional[str] = Field(default=None, description="Asana resource subtype of the affected resource, such as default_task")
    gid: Optional[str] = Field(default=None, description="Gid of the affected resource")
    name: Optional[str] = Field(default=None, description="Name of the affected resource")


class AuditLogEventItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the audit log event")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the event occurred")
    event_type: Optional[str] = Field(default=None, description="Type of event, such as task_deleted, project_added or user_login")
    event_category: Optional[str] = Field(default=None, description="Category of the event, such as creation, deletion or authentication")
    actor: Optional[AuditLogActor] = Field(default=None, description="Who performed the action: a user, an app or an automated task")
    resource: Optional[AuditLogResource] = Field(default=None, description="The resource the event acted on, when there is one")


class AuditLogList(BaseModel):
    items: list[AuditLogEventItem] = Field(description="Audit log events matching the requested workspace and filters")
    has_more: bool = Field(description="True when more events are available in the next page")
    next_offset: Optional[str] = Field(default=None, description="Cursor to pass as `offset` to fetch the next page, or null when there are no more results")


@function(
    id="asana.audit_log.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the security and activity events recorded in the Asana audit log of a workspace or organization: each "
        "event reports when it occurred, its event type and category, who performed the action (user, app or automated "
        "task, with gid, name and email) and the resource it acted on. Use it to investigate who changed, deleted or "
        "accessed resources, for security reviews and compliance. Asana restricts this endpoint to a Service Account "
        "with a Personal Access Token in Asana Enterprise or higher, so normal connections fail with an upstream error. "
        "Filters include event_type, actor_type, actor_gid, resource_gid and the start_at/end_at UTC range. Results are "
        "paginated by offset. Read-only. It is the only audit log function."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "event_type": "task_deleted"}, "output": {
        "items": [{"gid": "1200000000006500", "created_at": "2026-10-05T12:00:00.000Z", "event_type": "task_deleted",
                   "event_category": "deletion",
                   "actor": {"actor_type": "user", "gid": "1200000000000001", "name": "Ana Perez", "email": "ana@empresa.test"},
                   "resource": {"resource_type": "task", "resource_subtype": "default_task", "gid": "1200000000000500", "name": "Rediseno portada"}}],
        "has_more": False, "next_offset": None}}],
)
async def audit_log_list(ctx: Context, args: AuditLogListIn) -> AuditLogList:
    params = {"limit": args.limit}
    for key in ("event_type", "actor_type", "actor_gid", "resource_gid", "start_at", "end_at"):
        value = getattr(args, key)
        if value:
            params[key] = value
    if args.offset:
        params["offset"] = args.offset
    body = await _get_body(ctx, f"/workspaces/{args.workspace_gid}/audit_log_events", params=params)
    return AuditLogList(items=[
        AuditLogEventItem(gid=str(item["gid"]), created_at=item.get("created_at"), event_type=item.get("event_type"),
                          event_category=item.get("event_category"),
                          actor=AuditLogActor(**item.get("actor") or {}) if item.get("actor") else None,
                          resource=AuditLogResource(**item.get("resource") or {}) if item.get("resource") else None)
        for item in body.get("data", [])], has_more=bool(_next_offset(body)), next_offset=_next_offset(body))


# --- asana.organization_exports -----------------------------------------------------------------------------------


class OrganizationExportGetIn(BaseModel):
    organization_export_gid: str = Field(description="Gid of the organization export to fetch")


class OrganizationExportDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the organization export")
    state: Optional[str] = Field(default=None, description="State of the export request: pending, started, finished or error")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the export request was created")
    download_url: Optional[str] = Field(default=None, description="Temporary URL to download the export file once the state is 'finished'")
    organization: Optional[str] = Field(default=None, description="Gid of the organization the data was exported from")


@function(
    id="asana.organization_exports.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns the details of an Asana organization export request: its gid, its current state, when it was created, "
        "the temporary download URL of the generated file and the gid of the organization it was requested for. Use it "
        "when the user needs to check whether an organization-wide data export finished and fetch the download link to "
        "back up or migrate the workspace data. The export itself is requested from the Asana web interface; this "
        "function only reads the status and the download URL of an existing request. It requires only the export gid. "
        "Read-only. It does not start new exports."
    ),
    examples=[{"name": "default", "input": {"organization_export_gid": "1200000000006600"}, "output": {
        "gid": "1200000000006600", "state": "started", "created_at": "2026-01-01T10:00:00Z",
        "download_url": None, "organization": "1200000000000002"}}],
)
async def organization_exports_get(ctx: Context, args: OrganizationExportGetIn) -> OrganizationExportDetail:
    body = await _get_body(ctx, f"/organization_exports/{args.organization_export_gid}",
                           params={"opt_fields": "state,created_at,download_url,organization.name"})
    data = body.get("data") or {}
    return OrganizationExportDetail(gid=str(data["gid"]), state=data.get("state"), created_at=data.get("created_at"),
                                    download_url=data.get("download_url"), organization=_nested_gid(data, "organization"))

# Tareas 7 y 8 (lecturas avanzadas) y Tarea 9 (herramientas viejas migradas): se registran al final porque reutilizan modelos de este modulo.
from app.functions.apps.asana import f_advanced  # noqa: E402,F401
from app.functions.apps.asana import f_legacy  # noqa: E402,F401
