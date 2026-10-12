"""Lecturas de monday.com de las tareas 3 y 4 (equipos, columnas, grupos, subelementos, comentarios, docs, webhooks, carpetas, notificaciones,
busqueda, agregados, actividad, auditoria, relaciones, formularios, plantillas y exportaciones). Las importa functions.py al final.

Verificado en developer.monday.com/api-reference (2026-10-07). Diferencias con el catalogo generado por IA:
- `columns`, `groups` y `activity_logs` van anidados en `boards(ids)`; `subitems` va anidado en `items(ids)`; no existen en la raiz.
- La exportacion se consulta con `export_job_status(job_id)` (no `get_export_job_status`) y es solo plan Enterprise, igual que `audit_logs`
  (que ademas pide el permiso de cuenta manage_account_security, no un scope OAuth).
- `search` devuelve un objeto por tipo (items, boards, docs, users, workspaces, updates) con `results { id indexed_data }`; maximo 20.
- `notifications`, `template_installation_status`, `form` y `object_relations` no piden un scope OAuth concreto.
- `doc_version_history`/`doc_version_diff` (2026-04+), `object_relations` (2026-04+) y `template_installation_status` (2026-10+).
"""
import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.monday.functions import API, _gql
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

BOARD_ID = Field(pattern=r"^\d+$", description="Id of the board, as returned by monday.board.list (digits only)")


class Person(BaseModel):
    id: str = Field(description="monday user id of the person")
    name: Optional[str] = Field(default=None, description="Full name of the person")


def _person(raw: Optional[dict[str, Any]]) -> Optional[Person]:
    return Person(id=str(raw["id"]), name=raw.get("name")) if raw and raw.get("id") is not None else None


def _sid(value: Any) -> Optional[str]:
    return str(value) if value is not None else None


def _args(enums: Optional[dict[str, Optional[str]]] = None, **values: Any) -> str:
    """Argumentos GraphQL en linea (sin None ni listas vacias) para no depender del nombre exacto de cada tipo de variable.
    json.dumps produce literales GraphQL validos; los enums ya vienen validados por un Literal."""
    parts = [f"{k}: {json.dumps(v)}" for k, v in values.items() if v is not None and v != []]
    parts += [f"{k}: {v}" for k, v in (enums or {}).items() if v]
    return f"({', '.join(parts)})" if parts else ""


async def _one_board(ctx: Context, query: str, variables: dict[str, Any], board_id: str) -> dict[str, Any]:
    boards = (await _gql(ctx, query, variables)).get("boards") or []
    if not boards:
        raise FunctionError(ErrorCode.not_found, f"No existe el tablero {board_id} en monday o no tienes acceso.")
    return boards[0]


async def _one_item(ctx: Context, query: str, variables: dict[str, Any], item_id: str) -> dict[str, Any]:
    items = (await _gql(ctx, query, variables)).get("items") or []
    if not items:
        raise FunctionError(ErrorCode.not_found, f"No existe el elemento {item_id} en monday o no tienes acceso.")
    return items[0]


# --- monday.team.list ----------------------------------------------------------------------------

class ListTeamsIn(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=100, description="Return only the teams with these ids; leave empty to list every team")


class Team(BaseModel):
    id: str = Field(description="Team id")
    name: str = Field(description="Name of the team")
    picture_url: Optional[str] = Field(default=None, description="Link to the picture of the team, if any")
    owners: list[Person] = Field(default_factory=list, description="Users who own (manage) the team")
    members: list[Person] = Field(default_factory=list, description="Users who belong to the team")


class ListTeamsOut(BaseModel):
    teams: list[Team] = Field(description="Teams of the account")


@function(
    id="monday.team.list", version=1, verb=Verb.read, upstream_api=API, scopes=["teams:read"],
    description=(
        "Lists the teams of the connected monday.com account, optionally only some team ids. Each team has its id, name, picture link, its owners and "
        "its members (id and name of each user). Use it when the user asks which teams exist in monday, who belongs to a team, or needs a team id to "
        "assign or filter work. Read-only: it does not create teams, add or remove members or change owners. To list every user of the account "
        "use monday.user.list instead."
    ),
    examples=[{"name": "default", "input": {}, "output": {"teams": [
        {"id": "112233", "name": "Ventas", "picture_url": None, "owners": [{"id": "4012689", "name": "Ana Perez"}],
         "members": [{"id": "4012689", "name": "Ana Perez"}]}]}}],
)
async def team_list(ctx: Context, args: ListTeamsIn) -> ListTeamsOut:
    query = "query ($ids: [ID!]) { teams(ids: $ids) { id name picture_url owners { id name } users { id name } } }"
    data = await _gql(ctx, query, {"ids": args.ids or None})
    return ListTeamsOut(teams=[
        Team(id=str(t["id"]), name=t["name"], picture_url=t.get("picture_url"),
             owners=[p for p in (_person(o) for o in t.get("owners") or []) if p],
             members=[p for p in (_person(u) for u in t.get("users") or []) if p])
        for t in data.get("teams") or []])


# --- monday.board.export_status ------------------------------------------------------------------

class ExportStatusIn(BaseModel):
    job_id: str = Field(min_length=1, description="Job id returned by the board export mutation (create_board_export)")


class ExportStatusOut(BaseModel):
    status: str = Field(description="RUNNING, COMPLETED, FAILED or CANCELLED")
    download_url: Optional[str] = Field(default=None, description="Temporary link to download the CSV file once COMPLETED; treat it as a secret")
    failure_reason: Optional[str] = Field(default=None, description="Why the export failed, when status is FAILED")
    failure_message: Optional[str] = Field(default=None, description="Extra detail about the failure, when available")


@function(
    id="monday.board.export_status", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Returns the state of an asynchronous monday.com board export (CSV) started earlier: RUNNING, COMPLETED, FAILED or CANCELLED, and once it is "
        "completed a temporary download link. Use it to poll a job id returned when a large board export was started; wait a few seconds between "
        "calls. Board exports are only available on the monday Enterprise plan; other accounts get an error. Read-only: it does not start a new "
        "export. An unknown or expired job id is reported as not found."
    ),
    examples=[{"name": "default", "input": {"job_id": "a1b2c3d4-0000-0000-0000-000000000000"}, "output": {
        "status": "COMPLETED", "download_url": "https://files.monday.com/exports/board.csv", "failure_reason": None, "failure_message": None}}],
)
async def board_export_status(ctx: Context, args: ExportStatusIn) -> ExportStatusOut:
    query = "query ($job: ID!) { export_job_status(job_id: $job) { status download_url failure_reason failure_message } }"
    job = (await _gql(ctx, query, {"job": args.job_id})).get("export_job_status")
    if not job:
        raise FunctionError(ErrorCode.not_found, f"No existe la exportacion {args.job_id} (o vencio, o es de otra cuenta).")
    return ExportStatusOut(status=job["status"], download_url=job.get("download_url"), failure_reason=job.get("failure_reason"),
                           failure_message=job.get("failure_message"))


# --- monday.subitem.list -------------------------------------------------------------------------

class ListSubitemsIn(BaseModel):
    item_id: str = Field(pattern=r"^\d+$", description="Id of the parent item whose subitems are listed, as returned by monday.item.list")


class SubitemValue(BaseModel):
    id: str = Field(description="Column id on the subitems board")
    type: Optional[str] = Field(default=None, description="Column type, for example status, date, people or text")
    text: Optional[str] = Field(default=None, description="Value of the column as the user sees it, empty if not set")


class Subitem(BaseModel):
    id: str = Field(description="Subitem id")
    name: str = Field(description="Name of the subitem")
    state: Optional[str] = Field(default=None, description="active, archived or deleted")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the subitem was created")
    updated_at: Optional[str] = Field(default=None, description="UTC date and time of the last change to the subitem")
    column_values: list[SubitemValue] = Field(default_factory=list, description="Value of each column of the subitem")


class ListSubitemsOut(BaseModel):
    subitems: list[Subitem] = Field(description="Subitems of the parent item, in board order")


@function(
    id="monday.subitem.list", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Lists the subitems (child rows) of one monday.com item, with the id, name, state, creation and update dates and the value of every column of "
        "each subitem as the user sees it. Use it when the user asks for the subtasks or checklist of a task, deal or project, or needs subitem ids "
        "for a later step. Find the parent item id first with monday.item.list. Read-only: it does not create, change or delete subitems. Returns "
        "an empty list when the item has no subitems."
    ),
    examples=[{"name": "default", "input": {"item_id": "987654321"}, "output": {"subitems": [
        {"id": "987654400", "name": "Enviar propuesta", "state": "active", "created_at": "2026-02-02T10:00:00Z", "updated_at": "2026-02-03T10:00:00Z",
         "column_values": [{"id": "status", "type": "status", "text": "Done"}]}]}}],
)
async def subitem_list(ctx: Context, args: ListSubitemsIn) -> ListSubitemsOut:
    query = ("query ($ids: [ID!]) { items(ids: $ids) { subitems { id name state created_at updated_at "
             "column_values { id type text } } } }")
    item = await _one_item(ctx, query, {"ids": [args.item_id]}, args.item_id)
    return ListSubitemsOut(subitems=[
        Subitem(id=str(s["id"]), name=s["name"], state=s.get("state"), created_at=s.get("created_at"), updated_at=s.get("updated_at"),
                column_values=[SubitemValue(id=c["id"], type=c.get("type"), text=c.get("text")) for c in s.get("column_values") or []])
        for s in item.get("subitems") or []])


# --- monday.column.list --------------------------------------------------------------------------

class ListColumnsIn(BaseModel):
    board_id: str = BOARD_ID


class Column(BaseModel):
    id: str = Field(description="Column id, used to read or filter its values, for example 'status' or 'date4'")
    title: str = Field(description="Title of the column shown on the board")
    type: str = Field(description="Column type, for example status, date, people, numbers, text or dropdown")
    description: Optional[str] = Field(default=None, description="Description of the column, if any")
    width: Optional[int] = Field(default=None, description="Width of the column in pixels")
    archived: bool = Field(default=False, description="True if the column is archived")
    settings: Optional[Any] = Field(default=None, description="Type specific settings of the column, for example the labels of a status column")


class ListColumnsOut(BaseModel):
    columns: list[Column] = Field(description="Visible columns of the board, in board order")


@function(
    id="monday.column.list", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Lists the columns of one monday.com board: id, title, type (status, date, people, numbers, text...), description, width, whether it is "
        "archived, and its settings (for example the labels and colors of a status column). Use it when the user asks what fields a board tracks, or "
        "to learn the column ids and status labels needed to read, filter or aggregate items. Read-only: it does not create, rename or delete "
        "columns and it does not return item values (use monday.item.list for that)."
    ),
    examples=[{"name": "default", "input": {"board_id": "1234567890"}, "output": {"columns": [
        {"id": "status", "title": "Status", "type": "status", "description": None, "width": 120, "archived": False,
         "settings": {"labels": {"0": "Working on it", "1": "Done"}}}]}}],
)
async def column_list(ctx: Context, args: ListColumnsIn) -> ListColumnsOut:
    query = "query ($ids: [ID!]) { boards(ids: $ids) { columns { id title type description width archived settings } } }"
    board = await _one_board(ctx, query, {"ids": [args.board_id]}, args.board_id)
    return ListColumnsOut(columns=[
        Column(id=c["id"], title=c["title"], type=c["type"], description=c.get("description"), width=c.get("width"),
               archived=bool(c.get("archived")), settings=c.get("settings"))
        for c in board.get("columns") or []])


# --- monday.group.list ---------------------------------------------------------------------------

class ListGroupsIn(BaseModel):
    board_id: str = BOARD_ID


class Group(BaseModel):
    id: str = Field(description="Group id, for example 'topics' or 'new_group12345'")
    title: str = Field(description="Title of the group shown on the board, for example 'This week'")
    color: Optional[str] = Field(default=None, description="Color of the group as a HEX code")
    position: Optional[str] = Field(default=None, description="Position of the group on the board; lower values sit higher")
    archived: bool = Field(default=False, description="True if the group is archived")


class ListGroupsOut(BaseModel):
    groups: list[Group] = Field(description="Groups (sections) of the board")


@function(
    id="monday.group.list", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Lists the groups (sections) of one monday.com board, such as 'This week', 'Next week' or 'Done', with their id, title, color, position and "
        "whether they are archived. Use it when the user asks how a board is organized, or needs a group id to filter, move or create items in a "
        "specific section. Read-only: it does not create, rename, move or delete groups, and it does not return the items of each group (use "
        "monday.item.list, where each item carries its group)."
    ),
    examples=[{"name": "default", "input": {"board_id": "1234567890"}, "output": {"groups": [
        {"id": "topics", "title": "Nuevos", "color": "#579bfc", "position": "65536", "archived": False}]}}],
)
async def group_list(ctx: Context, args: ListGroupsIn) -> ListGroupsOut:
    query = "query ($ids: [ID!]) { boards(ids: $ids) { groups { id title color position archived } } }"
    board = await _one_board(ctx, query, {"ids": [args.board_id]}, args.board_id)
    return ListGroupsOut(groups=[
        Group(id=g["id"], title=g["title"], color=g.get("color"), position=_sid(g.get("position")), archived=bool(g.get("archived")))
        for g in board.get("groups") or []])


# --- monday.update.list --------------------------------------------------------------------------

class ListUpdatesIn(BaseModel):
    item_id: Optional[str] = Field(default=None, pattern=r"^\d+$", description="Return only the updates of this item; leave empty to not filter by item")
    board_id: Optional[str] = Field(default=None, pattern=r"^\d+$", description="Return only the updates of this board; leave empty to not filter by board")
    limit: int = Field(default=25, ge=1, le=100, description="How many updates to return in this page, from 1 to 100 (default 25)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1; ask for the next page while a full page comes back")

    @model_validator(mode="after")
    def _one_scope(self) -> "ListUpdatesIn":
        if self.item_id and self.board_id:
            raise ValueError("give item_id or board_id, not both")
        return self


class Reply(BaseModel):
    id: str = Field(description="Reply id")
    text: Optional[str] = Field(default=None, description="Plain text of the reply")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the reply was written")
    creator: Optional[Person] = Field(default=None, description="User who wrote the reply")


class Update(BaseModel):
    id: str = Field(description="Update (comment) id")
    text: Optional[str] = Field(default=None, description="Plain text of the update, without HTML")
    item_id: Optional[str] = Field(default=None, description="Id of the item the update was posted on")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the update was posted")
    updated_at: Optional[str] = Field(default=None, description="UTC date and time of the last edit of the update")
    creator: Optional[Person] = Field(default=None, description="User who posted the update")
    replies: list[Reply] = Field(default_factory=list, description="Replies written under the update")


class ListUpdatesOut(BaseModel):
    updates: list[Update] = Field(description="Updates of this page, newest first")


@function(
    id="monday.update.list", version=1, verb=Verb.read, upstream_api=API, scopes=["updates:read"],
    description=(
        "Lists updates (the comments posted on items) of the connected monday.com account, newest first, optionally only those of one item or of one "
        "board, with page-based pagination. Each update has its id, plain text, item id, dates, author and its replies. Use it when the user asks what "
        "was said about a task or deal, wants the latest comments, or needs an update id. At most 100 per page. Read-only: it does not post, edit, "
        "like, pin or delete updates. Give item_id or board_id, not both."
    ),
    examples=[{"name": "default", "input": {"item_id": "987654321", "limit": 1}, "output": {"updates": [
        {"id": "3301", "text": "Cliente pidio otra cotizacion", "item_id": "987654321", "created_at": "2026-03-01T09:00:00Z",
         "updated_at": "2026-03-01T09:00:00Z", "creator": {"id": "4012689", "name": "Ana Perez"},
         "replies": [{"id": "3302", "text": "Listo, enviada", "created_at": "2026-03-01T10:00:00Z", "creator": {"id": "4012690", "name": "Luis"}}]}]}}],
)
async def update_list(ctx: Context, args: ListUpdatesIn) -> ListUpdatesOut:
    fields = ("updates(limit: $limit, page: $page) { id text_body item_id created_at updated_at creator { id name } "
              "replies { id text_body created_at creator { id name } } }")
    variables: dict[str, Any] = {"limit": args.limit, "page": args.page}
    if args.item_id:
        raw = (await _one_item(ctx, f"query ($ids: [ID!], $limit: Int, $page: Int) {{ items(ids: $ids) {{ {fields} }} }}",
                               {**variables, "ids": [args.item_id]}, args.item_id)).get("updates")
    elif args.board_id:
        raw = (await _one_board(ctx, f"query ($ids: [ID!], $limit: Int, $page: Int) {{ boards(ids: $ids) {{ {fields} }} }}",
                                {**variables, "ids": [args.board_id]}, args.board_id)).get("updates")
    else:
        raw = (await _gql(ctx, f"query ($limit: Int, $page: Int) {{ {fields} }}", variables)).get("updates")
    return ListUpdatesOut(updates=[
        Update(id=str(u["id"]), text=u.get("text_body"), item_id=_sid(u.get("item_id")), created_at=u.get("created_at"),
               updated_at=u.get("updated_at"), creator=_person(u.get("creator")),
               replies=[Reply(id=str(r["id"]), text=r.get("text_body"), created_at=r.get("created_at"), creator=_person(r.get("creator")))
                        for r in u.get("replies") or []])
        for u in raw or []])


# --- monday.doc.list -----------------------------------------------------------------------------

class ListDocsIn(BaseModel):
    workspace_ids: list[str] = Field(default_factory=list, max_length=50, description="Return only docs of these workspace ids; leave empty for every workspace")
    order_by: Literal["created_at", "used_at"] = Field(default="created_at", description="Sort order: created_at (newest first, default) or used_at (most recently used first)")
    limit: int = Field(default=25, ge=1, le=100, description="How many docs to return in this page, from 1 to 100 (default 25)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1; ask for the next page while a full page comes back")


class Doc(BaseModel):
    id: str = Field(description="Internal doc id, used by the version history and version diff functions")
    object_id: Optional[str] = Field(default=None, description="Doc id shown in its link (object id)")
    name: str = Field(description="Title of the doc")
    doc_kind: Optional[str] = Field(default=None, description="public, private or share")
    workspace_id: Optional[str] = Field(default=None, description="Id of the workspace that contains the doc; empty for the main workspace")
    folder_id: Optional[str] = Field(default=None, description="Id of the folder that contains the doc; empty at the top level")
    created_at: Optional[str] = Field(default=None, description="Date when the doc was created")
    updated_at: Optional[str] = Field(default=None, description="Date of the last change to the doc")
    created_by: Optional[Person] = Field(default=None, description="User who created the doc")
    url: Optional[str] = Field(default=None, description="Link to open the doc in monday.com")


class ListDocsOut(BaseModel):
    docs: list[Doc] = Field(description="Docs of this page")


@function(
    id="monday.doc.list", version=1, verb=Verb.read, upstream_api=API, scopes=["docs:read"],
    description=(
        "Lists the monday.com docs (workdocs) the user can see, optionally only those of some workspaces, sorted by creation or last use, with "
        "page-based pagination. Each doc has its internal id, the id shown in its link, title, kind, workspace, folder, dates, author and link. Use "
        "it when the user asks which documents they have in monday, wants to find a doc by title, or needs a doc id to read its version history. "
        "Read-only: it does not create, rename or delete docs and it does not return the content of the doc."
    ),
    examples=[{"name": "default", "input": {"limit": 1}, "output": {"docs": [
        {"id": "5544", "object_id": "1234500000", "name": "Plan de ventas", "doc_kind": "public", "workspace_id": "551234", "folder_id": None,
         "created_at": "2026-01-10T10:00:00Z", "updated_at": "2026-02-10T10:00:00Z", "created_by": {"id": "4012689", "name": "Ana Perez"},
         "url": "https://empresademo.monday.com/docs/1234500000"}]}}],
)
async def doc_list(ctx: Context, args: ListDocsIn) -> ListDocsOut:
    filters = _args({"order_by": args.order_by}, limit=args.limit, page=args.page, workspace_ids=args.workspace_ids)
    query = (f"query {{ docs{filters} {{ "
             "id object_id name doc_kind workspace_id doc_folder_id created_at updated_at url created_by { id name } } }")
    data = await _gql(ctx, query, {})
    return ListDocsOut(docs=[
        Doc(id=str(d["id"]), object_id=_sid(d.get("object_id")), name=d["name"], doc_kind=d.get("doc_kind"),
            workspace_id=_sid(d.get("workspace_id")), folder_id=_sid(d.get("doc_folder_id")), created_at=d.get("created_at"),
            updated_at=d.get("updated_at"), created_by=_person(d.get("created_by")), url=d.get("url"))
        for d in data.get("docs") or []])


# --- monday.doc.version_history ------------------------------------------------------------------

class DocHistoryIn(BaseModel):
    doc_id: str = Field(pattern=r"^\d+$", description="Id of the doc (the object id shown in its link), as returned by monday.doc.list")
    since: Optional[str] = Field(default=None, description="Only snapshots on or after this ISO 8601 date and time, for example 2026-01-01T00:00:00Z")
    until: Optional[str] = Field(default=None, description="Only snapshots on or before this ISO 8601 date and time")


class RestoringPoint(BaseModel):
    date: str = Field(description="ISO 8601 date and time of the snapshot")
    user_ids: list[str] = Field(default_factory=list, description="Ids of the users who changed the doc in that 5 minute window")
    type: Optional[str] = Field(default=None, description="publish for publish events, otherwise empty")


class DocHistoryOut(BaseModel):
    doc_id: str = Field(description="Id of the doc whose history was read")
    restoring_points: list[RestoringPoint] = Field(description="Snapshots of the doc, grouped in 5 minute windows")


@function(
    id="monday.doc.version_history", version=1, verb=Verb.read, upstream_api=API, scopes=["docs:read"],
    description=(
        "Returns the version history of one monday.com doc: a list of snapshots (restoring points) grouped in 5 minute windows, each with its date, "
        "the ids of the users who made changes and whether it was a publish event, optionally limited to a date range. Use it when the user asks who "
        "changed a doc and when, or to pick two dates to compare with monday.doc.version_diff. Read-only: it does not restore versions or return the "
        "content of the doc."
    ),
    examples=[{"name": "default", "input": {"doc_id": "1234500000"}, "output": {"doc_id": "1234500000", "restoring_points": [
        {"date": "2026-02-10T10:05:00Z", "user_ids": ["4012689"], "type": None}]}}],
)
async def doc_version_history(ctx: Context, args: DocHistoryIn) -> DocHistoryOut:
    filters = _args(doc_id=args.doc_id, since=args.since, until=args.until)
    query = f"query {{ doc_version_history{filters} {{ doc_id restoring_points {{ date user_ids type }} }} }}"
    hist = (await _gql(ctx, query, {})).get("doc_version_history")
    if not hist:
        raise FunctionError(ErrorCode.not_found, f"No existe el doc {args.doc_id} en monday o no tienes acceso.")
    return DocHistoryOut(doc_id=str(hist.get("doc_id") or args.doc_id), restoring_points=[
        RestoringPoint(date=p["date"], user_ids=[str(u) for u in p.get("user_ids") or []], type=p.get("type"))
        for p in hist.get("restoring_points") or [] if p.get("date")])


# --- monday.doc.version_diff ---------------------------------------------------------------------

class DocDiffIn(BaseModel):
    doc_id: str = Field(pattern=r"^\d+$", description="Id of the doc (the object id shown in its link), as returned by monday.doc.list")
    date: str = Field(min_length=10, description="Newer snapshot date (ISO 8601), taken from monday.doc.version_history")
    prev_date: str = Field(min_length=10, description="Older snapshot date (ISO 8601) to compare against")


class DiffBlock(BaseModel):
    id: Optional[str] = Field(default=None, description="Id of the changed block")
    type: Optional[str] = Field(default=None, description="Block type, for example normal text, title or table")
    summary: Optional[str] = Field(default=None, description="Human readable summary of the change")
    content: Optional[str] = Field(default=None, description="Content of the block after the change")
    added: bool = Field(default=False, description="True if the block was added")
    deleted: bool = Field(default=False, description="True if the block was deleted")
    changed: bool = Field(default=False, description="True if the content of the block changed")


class DocDiffOut(BaseModel):
    doc_id: str = Field(description="Id of the doc that was compared")
    blocks: list[DiffBlock] = Field(description="Blocks that were added, deleted or changed between the two dates")


@function(
    id="monday.doc.version_diff", version=1, verb=Verb.read, upstream_api=API, scopes=["docs:read"],
    description=(
        "Compares two versions of one monday.com doc and returns only the blocks that were added, deleted or changed between an older and a newer "
        "snapshot date, each with its type, a short human readable summary and its content. Use it when the user asks what changed in a doc between "
        "two moments; get valid snapshot dates first with monday.doc.version_history. Read-only: it does not restore or edit the doc."
    ),
    examples=[{"name": "default", "input": {"doc_id": "1234500000", "date": "2026-02-10T10:05:00Z", "prev_date": "2026-02-01T10:00:00Z"},
               "output": {"doc_id": "1234500000", "blocks": [{"id": "b1", "type": "normal text", "summary": "Text edited", "content": "Meta Q2: 50",
                                                              "added": False, "deleted": False, "changed": True}]}}],
)
async def doc_version_diff(ctx: Context, args: DocDiffIn) -> DocDiffOut:
    query = ("query ($doc: ID!, $date: String!, $prev: String!) { doc_version_diff(doc_id: $doc, date: $date, prev_date: $prev) { "
             "doc_id blocks { id type content summary changes { added deleted changed } } } }")
    diff = (await _gql(ctx, query, {"doc": args.doc_id, "date": args.date, "prev": args.prev_date})).get("doc_version_diff")
    if not diff:
        raise FunctionError(ErrorCode.not_found, f"No existe el doc {args.doc_id} o esas versiones en monday.")
    return DocDiffOut(doc_id=str(diff.get("doc_id") or args.doc_id), blocks=[
        DiffBlock(id=b.get("id"), type=b.get("type"), summary=b.get("summary"), content=b.get("content"),
                  added=bool((b.get("changes") or {}).get("added")), deleted=bool((b.get("changes") or {}).get("deleted")),
                  changed=bool((b.get("changes") or {}).get("changed")))
        for b in diff.get("blocks") or []])


# --- monday.webhook.list -------------------------------------------------------------------------

class ListWebhooksIn(BaseModel):
    board_id: str = BOARD_ID
    app_webhooks_only: bool = Field(default=False, description="True to return only the webhooks created by this app (BunnyDrop)")


class Webhook(BaseModel):
    id: str = Field(description="Webhook id")
    board_id: str = Field(description="Id of the board the webhook listens to")
    event: str = Field(description="Event that triggers the webhook, for example create_item or change_status_column_value")
    config: Optional[str] = Field(default=None, description="Extra configuration of the event, for example which column or group it watches")


class ListWebhooksOut(BaseModel):
    webhooks: list[Webhook] = Field(description="Webhooks subscribed to the board")


@function(
    id="monday.webhook.list", version=1, verb=Verb.read, upstream_api=API, scopes=["webhooks:read"],
    description=(
        "Lists the webhooks subscribed to one monday.com board, optionally only those created by this app. Each webhook has its id, board id, the "
        "event that triggers it (for example create_item, change_status_column_value or create_update) and its extra configuration. Use it to check "
        "which integrations are listening to a board or to find a webhook id. The target link of each webhook is not returned by monday. Read-only: "
        "it does not create or delete webhooks."
    ),
    examples=[{"name": "default", "input": {"board_id": "1234567890"}, "output": {"webhooks": [
        {"id": "12", "board_id": "1234567890", "event": "create_item", "config": None}]}}],
)
async def webhook_list(ctx: Context, args: ListWebhooksIn) -> ListWebhooksOut:
    query = "query ($board: ID!, $mine: Boolean) { webhooks(board_id: $board, app_webhooks_only: $mine) { id board_id event config } }"
    data = await _gql(ctx, query, {"board": args.board_id, "mine": args.app_webhooks_only})
    return ListWebhooksOut(webhooks=[
        Webhook(id=str(w["id"]), board_id=str(w["board_id"]), event=w["event"], config=w.get("config"))
        for w in data.get("webhooks") or []])


# --- monday.folder.list --------------------------------------------------------------------------

class ListFoldersIn(BaseModel):
    workspace_ids: list[str] = Field(default_factory=list, max_length=50, description="Return only folders of these workspace ids; leave empty for every workspace")
    limit: int = Field(default=25, ge=1, le=100, description="How many folders to return in this page, from 1 to 100 (default 25)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1; ask for the next page while a full page comes back")


class FolderEntry(BaseModel):
    id: str = Field(description="Id of the board, doc or subfolder")
    name: Optional[str] = Field(default=None, description="Name of the board, doc or subfolder")


class Folder(BaseModel):
    id: str = Field(description="Folder id")
    name: str = Field(description="Name of the folder")
    color: Optional[str] = Field(default=None, description="Color of the folder in the left menu")
    workspace_id: Optional[str] = Field(default=None, description="Id of the workspace that contains the folder")
    parent_id: Optional[str] = Field(default=None, description="Id of the parent folder; empty at the top level")
    owner_id: Optional[str] = Field(default=None, description="Id of the user who owns the folder")
    created_at: Optional[str] = Field(default=None, description="Date when the folder was created")
    boards: list[FolderEntry] = Field(default_factory=list, description="Boards and docs inside the folder, without subfolders")
    sub_folders: list[FolderEntry] = Field(default_factory=list, description="Folders nested inside this folder")


class ListFoldersOut(BaseModel):
    folders: list[Folder] = Field(description="Folders of this page")


@function(
    id="monday.folder.list", version=1, verb=Verb.read, upstream_api=API, scopes=["workspaces:read"],
    description=(
        "Lists the folders of the connected monday.com account, optionally only those of some workspaces, with page-based pagination. Each folder has "
        "its id, name, color, workspace, parent folder, owner, creation date, the boards and docs inside it and its subfolders. Use it when the user "
        "asks how their boards are organized in the left menu or needs a folder id. At most 100 per page. Read-only: it does not create, rename, "
        "move or delete folders."
    ),
    examples=[{"name": "default", "input": {"limit": 1}, "output": {"folders": [
        {"id": "7788", "name": "Clientes", "color": "AQUAMARINE", "workspace_id": "551234", "parent_id": None, "owner_id": "4012689",
         "created_at": "2026-01-05", "boards": [{"id": "1234567890", "name": "Pipeline de ventas"}], "sub_folders": []}]}}],
)
async def folder_list(ctx: Context, args: ListFoldersIn) -> ListFoldersOut:
    query = ("query ($limit: Int, $page: Int, $workspace_ids: [ID]) { folders(limit: $limit, page: $page, workspace_ids: $workspace_ids) { "
             "id name color owner_id created_at workspace { id } parent { id } children { id name } sub_folders { id name } } }")
    data = await _gql(ctx, query, {"limit": args.limit, "page": args.page, "workspace_ids": args.workspace_ids or None})
    return ListFoldersOut(folders=[
        Folder(id=str(f["id"]), name=f["name"], color=f.get("color"), workspace_id=_sid((f.get("workspace") or {}).get("id")),
               parent_id=_sid((f.get("parent") or {}).get("id")), owner_id=_sid(f.get("owner_id")), created_at=f.get("created_at"),
               boards=[FolderEntry(id=str(b["id"]), name=b.get("name")) for b in f.get("children") or [] if b],
               sub_folders=[FolderEntry(id=str(s["id"]), name=s.get("name")) for s in f.get("sub_folders") or [] if s])
        for f in data.get("folders") or []])


# --- monday.notification.list --------------------------------------------------------------------

class ListNotificationsIn(BaseModel):
    unread_only: bool = Field(default=False, description="True to return only the notifications the user has not read yet")
    since: Optional[str] = Field(default=None, description="Only notifications from this ISO 8601 date and time on, for example 2026-03-01T00:00:00Z")
    limit: int = Field(default=25, ge=1, le=100, description="How many notifications to return, from 1 to 100 (default 25)")
    cursor: Optional[str] = Field(default=None, description="Id of the last notification of the previous page, to read the next page")


class Notification(BaseModel):
    id: str = Field(description="Notification id; pass the last one as cursor to read the next page")
    title: Optional[str] = Field(default=None, description="Title of the notification")
    text: Optional[str] = Field(default=None, description="Text of the notification")
    read: bool = Field(default=False, description="True if the user already read it")
    created_at: Optional[str] = Field(default=None, description="Date when the notification was created")
    board: Optional[FolderEntry] = Field(default=None, description="Board the notification refers to, if any")
    item: Optional[FolderEntry] = Field(default=None, description="Item the notification refers to, if any")


class ListNotificationsOut(BaseModel):
    notifications: list[Notification] = Field(description="Notifications of the connected user, newest first")


@function(
    id="monday.notification.list", version=1, verb=Verb.read, upstream_api=API, scopes=[],
    description=(
        "Lists the bell notifications of the connected monday.com user, newest first, optionally only unread ones or only those since a date. Each "
        "notification has its id, title, text, whether it was read, its date and the board and item it refers to. Use it when the user asks what is "
        "new in monday, what they were mentioned or assigned in, or what they have not read yet. To read the next page pass the id of the last "
        "notification as cursor. Read-only: it does not mark notifications as read or send new ones."
    ),
    examples=[{"name": "default", "input": {"unread_only": True, "limit": 1}, "output": {"notifications": [
        {"id": "998877", "title": "Ana te menciono", "text": "Revisa la propuesta", "read": False, "created_at": "2026-03-02T09:00:00Z",
         "board": {"id": "1234567890", "name": "Pipeline de ventas"}, "item": {"id": "987654321", "name": "Cliente Demo"}}]}}],
)
async def notification_list(ctx: Context, args: ListNotificationsIn) -> ListNotificationsOut:
    filters = _args(limit=args.limit, filter_read=args.unread_only or None, since=args.since, cursor=args.cursor)
    query = f"query {{ notifications{filters} {{ id title text read created_at board {{ id name }} item {{ id name }} }} }}"
    data = await _gql(ctx, query, {})

    def entry(raw: Optional[dict[str, Any]]) -> Optional[FolderEntry]:
        return FolderEntry(id=str(raw["id"]), name=raw.get("name")) if raw and raw.get("id") is not None else None

    return ListNotificationsOut(notifications=[
        Notification(id=str(n["id"]), title=n.get("title"), text=n.get("text"), read=bool(n.get("read")), created_at=n.get("created_at"),
                     board=entry(n.get("board")), item=entry(n.get("item")))
        for n in data.get("notifications") or []])


# --- monday.template.install_status --------------------------------------------------------------

class TemplateStatusIn(BaseModel):
    process_id: str = Field(min_length=1, description="Process id returned when the template installation (use_template) was started")


class TemplateStatusOut(BaseModel):
    status: str = Field(description="PENDING, IN_PROGRESS, COMPLETE or FAILED")
    is_complete: bool = Field(description="True once the installation finished well")
    is_failed: bool = Field(description="True if the installation failed")
    board_ids: list[str] = Field(default_factory=list, description="Ids of the boards created so far; their content is ready only when COMPLETE")


@function(
    id="monday.template.install_status", version=1, verb=Verb.read, upstream_api=API, scopes=[],
    description=(
        "Returns the progress of a monday.com template installation started earlier: PENDING, IN_PROGRESS, COMPLETE or FAILED, and the ids of the "
        "boards created so far. Use it to poll a process id every few seconds until it is complete or failed; board content is only ready once the "
        "status is COMPLETE. Installation records expire one hour after they start, and an unknown or expired process id is reported as not found. "
        "Read-only: it does not start or cancel an installation."
    ),
    examples=[{"name": "default", "input": {"process_id": "c072acaf68e0be9fd0e451f0884383b6"}, "output": {
        "status": "COMPLETE", "is_complete": True, "is_failed": False, "board_ids": ["1234567890"]}}],
)
async def template_install_status(ctx: Context, args: TemplateStatusIn) -> TemplateStatusOut:
    query = "query ($pid: ID!) { template_installation_status(process_id: $pid) { status is_complete is_failed board_ids } }"
    st = (await _gql(ctx, query, {"pid": args.process_id})).get("template_installation_status")
    if not st:
        raise FunctionError(ErrorCode.not_found, f"No existe la instalacion {args.process_id} (o vencio, o es de otra cuenta).")
    return TemplateStatusOut(status=st["status"], is_complete=bool(st.get("is_complete")), is_failed=bool(st.get("is_failed")),
                             board_ids=[str(b) for b in st.get("board_ids") or [] if b is not None])


# --- monday.form.get -----------------------------------------------------------------------------

class FormGetIn(BaseModel):
    form_token: str = Field(pattern=r"^[A-Za-z0-9_-]+$", description="Token of the form, the text right after /forms/ in its share link")


class FormQuestion(BaseModel):
    id: str = Field(description="Question id")
    title: Optional[str] = Field(default=None, description="Text of the question")
    type: Optional[str] = Field(default=None, description="Question type, for example ShortText, Email, Rating or Name")
    required: bool = Field(default=False, description="True if the question must be answered")
    visible: bool = Field(default=True, description="True if the question is shown on the form")


class FormGetOut(BaseModel):
    id: str = Field(description="Id of the form (its board view id)")
    token: str = Field(description="Token of the form")
    title: str = Field(description="Title shown at the top of the form")
    description: Optional[str] = Field(default=None, description="Description shown under the title")
    active: bool = Field(description="True if the form is visible and accepting answers")
    is_anonymous: bool = Field(default=False, description="True if answers are collected anonymously")
    owner_id: Optional[str] = Field(default=None, description="Id of the user who owns the form")
    questions: list[FormQuestion] = Field(default_factory=list, description="Questions of the form in display order")


@function(
    id="monday.form.get", version=1, verb=Verb.read, upstream_api=API, scopes=[],
    description=(
        "Returns one monday.com WorkForm by its token: id, title, description, whether it is active and anonymous, its owner and its questions in "
        "display order (title, type, required and visible). The token is the text right after /forms/ in the share link of the form. Use it when the "
        "user asks what a form asks, whether it is still accepting answers, or before reading its answers on the board behind it. The user needs "
        "access to that board. Read-only: it does not change the form."
    ),
    examples=[{"name": "default", "input": {"form_token": "abc123def456ghi789"}, "output": {
        "id": "12345", "token": "abc123def456ghi789", "title": "Encuesta de clientes", "description": None, "active": True, "is_anonymous": False,
        "owner_id": "4012689", "questions": [{"id": "q1", "title": "Nombre completo", "type": "Name", "required": True, "visible": True}]}}],
)
async def form_get(ctx: Context, args: FormGetIn) -> FormGetOut:
    query = ("query ($token: String!) { form(formToken: $token) { id token title description active isAnonymous ownerId "
             "questions { id title type required visible } } }")
    form = (await _gql(ctx, query, {"token": args.form_token})).get("form")
    if not form:
        raise FunctionError(ErrorCode.not_found, f"No existe el formulario {args.form_token} en monday o no tienes acceso.")
    return FormGetOut(id=str(form["id"]), token=form.get("token") or args.form_token, title=form["title"], description=form.get("description"),
                      active=bool(form.get("active")), is_anonymous=bool(form.get("isAnonymous")), owner_id=_sid(form.get("ownerId")),
                      questions=[FormQuestion(id=str(q["id"]), title=q.get("title"), type=q.get("type"), required=bool(q.get("required")),
                                              visible=q.get("visible") is not False) for q in form.get("questions") or []])


# --- monday.search.query -------------------------------------------------------------------------

_SEARCH_FIELDS = {
    "items": ("name board_id url", True, True),
    "boards": ("name url", True, True),
    "docs": ("name", False, True),
    "users": ("name email", False, False),
    "workspaces": ("name", False, False),
    "updates": ("body item_id board_id", True, False),
}


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=200, description="Words to search for, matched by keyword and by meaning")
    types: list[Literal["items", "boards", "docs", "users", "workspaces", "updates"]] = Field(
        default_factory=lambda: ["items", "boards", "docs"], min_length=1,
        description="Which kinds of results to search: items, boards, docs, users, workspaces or updates (default items, boards and docs)")
    limit: int = Field(default=10, ge=1, le=20, description="Maximum results per kind, from 1 to 20 (default 10)")
    board_ids: list[str] = Field(default_factory=list, max_length=50, description="Search items, boards and updates only in these board ids; leave empty for all")
    workspace_ids: list[str] = Field(default_factory=list, max_length=50, description="Search items, boards and docs only in these workspace ids; leave empty for all")


class SearchHit(BaseModel):
    type: str = Field(description="Kind of result: item, board, doc, user, workspace or update")
    id: str = Field(description="Id of the result, usable with the matching list or get function")
    name: Optional[str] = Field(default=None, description="Name or title of the result (for updates, the start of its text)")
    url: Optional[str] = Field(default=None, description="Link to open the result in monday.com, when available")
    board_id: Optional[str] = Field(default=None, description="Board that holds the result, for items and updates")
    item_id: Optional[str] = Field(default=None, description="Item the update was posted on, for updates")
    email: Optional[str] = Field(default=None, description="Email address, for users")


class SearchOut(BaseModel):
    hits: list[SearchHit] = Field(description="Results grouped by kind, most relevant first within each kind")


@function(
    id="monday.search.query", version=1, verb=Verb.read, upstream_api=API,
    scopes=["boards:read", "docs:read", "users:read", "workspaces:read", "updates:read"],
    description=(
        "Searches the whole connected monday.com account by words and meaning and returns the most relevant items, boards, docs, users, workspaces "
        "or updates, up to 20 of each kind, optionally only in some boards or workspaces. Each hit has its kind, id, name, link and, for items and "
        "updates, its board. Use it when the user mentions something by name and you do not know where it is in monday, for example 'find the "
        "Acme deal' or 'which doc talks about the Q2 plan'. Search results may lag a few seconds behind recent changes. Read-only."
    ),
    examples=[{"name": "default", "input": {"query": "Cliente Demo", "types": ["items"], "limit": 1}, "output": {"hits": [
        {"type": "item", "id": "987654321", "name": "Cliente Demo", "url": "https://empresademo.monday.com/boards/1234567890/pulses/987654321",
         "board_id": "1234567890", "item_id": None, "email": None}]}}],
)
async def search_query(ctx: Context, args: SearchIn) -> SearchOut:
    parts = []
    for kind in dict.fromkeys(args.types):
        fields, by_board, by_workspace = _SEARCH_FIELDS[kind]
        filters = _args(query=args.query, limit=args.limit, board_ids=args.board_ids if by_board else None,
                        workspace_ids=args.workspace_ids if by_workspace else None)
        parts.append(f"{kind}{filters} {{ results {{ id indexed_data {{ {fields} }} }} }}")
    data = await _gql(ctx, f"query {{ search {{ {' '.join(parts)} }} }}", {})
    found = data.get("search") or {}
    hits = []
    for kind in dict.fromkeys(args.types):
        for r in (found.get(kind) or {}).get("results") or []:
            d = r.get("indexed_data") or {}
            name = d.get("name") if kind != "updates" else (d.get("body") or "")[:120] or None
            hits.append(SearchHit(type=kind.rstrip("s"), id=str(r["id"]), name=name, url=d.get("url"), board_id=_sid(d.get("board_id")),
                                  item_id=_sid(d.get("item_id")), email=d.get("email")))
    return SearchOut(hits=hits)


# --- monday.aggregate.calculate ------------------------------------------------------------------

_COLUMN_ID = r"^[a-z0-9_]{1,40}$"


class AggregateIn(BaseModel):
    board_id: str = BOARD_ID
    function: Literal["COUNT_ITEMS", "COUNT_SUBITEMS", "COUNT", "COUNT_DISTINCT", "SUM", "AVERAGE", "MEDIAN", "MIN", "MAX"] = Field(
        default="COUNT_ITEMS", description="What to calculate: COUNT_ITEMS (default), COUNT_SUBITEMS, COUNT, COUNT_DISTINCT, SUM, AVERAGE, MEDIAN, MIN or MAX")
    column_id: Optional[str] = Field(default=None, pattern=_COLUMN_ID, description="Column to calculate on (from monday.column.list); required except for COUNT_ITEMS and COUNT_SUBITEMS")
    group_by_column_id: Optional[str] = Field(default=None, pattern=_COLUMN_ID, description="Column to group the result by, for example a status or people column; leave empty for one total")
    group_limit: int = Field(default=10, ge=1, le=100, description="Maximum number of groups to return when grouping, from 1 to 100 (default 10)")

    @model_validator(mode="after")
    def _needs_column(self) -> "AggregateIn":
        if self.function not in ("COUNT_ITEMS", "COUNT_SUBITEMS") and not self.column_id:
            raise ValueError(f"{self.function} needs column_id")
        return self


class AggregateGroup(BaseModel):
    group: Optional[Any] = Field(default=None, description="Raw value of the group column (status color, person-<id>, date in ms...); empty without grouping")
    result: Optional[float] = Field(default=None, description="Calculated value for that group, or the total without grouping")


class AggregateOut(BaseModel):
    groups: list[AggregateGroup] = Field(description="One entry per group, or a single entry with the total when not grouping")


@function(
    id="monday.aggregate.calculate", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Calculates a summary over the items of one monday.com board without reading every item: count of items or subitems, count, distinct count, "
        "sum, average, median, minimum or maximum of one column, optionally grouped by another column (for example total deal value per owner, or "
        "number of tasks per status). Use it when the user asks for totals, averages or breakdowns of a board. Group values come raw: status columns "
        "give a color code, people columns give person-<id>, dates give milliseconds. Read-only."
    ),
    examples=[{"name": "default", "input": {"board_id": "1234567890", "function": "SUM", "column_id": "numbers", "group_by_column_id": "status"},
               "output": {"groups": [{"group": "#00c875", "result": 1500.0}, {"group": "#fdab3d", "result": 700.0}]}}],
)
async def aggregate_calculate(ctx: Context, args: AggregateIn) -> AggregateOut:
    func: dict[str, Any] = {"function": args.function}
    if args.column_id:
        func["params"] = [{"type": "COLUMN", "column": {"column_id": args.column_id}, "as": args.column_id}]
    select: list[dict[str, Any]] = [{"type": "FUNCTION", "function": func, "as": "result"}]
    spec: dict[str, Any] = {"from": {"type": "TABLE", "id": args.board_id}, "select": select}
    if args.group_by_column_id:
        select.append({"type": "COLUMN", "column": {"column_id": args.group_by_column_id}, "as": "group"})
        spec["group_by"] = [{"column_id": args.group_by_column_id, "limit": args.group_limit}]
    query = ("query ($q: AggregateQueryInput!) { aggregate(query: $q) { results { entries { alias value { "
             "... on AggregateGroupByResult { value } ... on AggregateBasicAggregationResult { result } } } } } }")
    data = await _gql(ctx, query, {"q": spec})
    groups = []
    for rs in (data.get("aggregate") or {}).get("results") or []:
        entries = {e.get("alias"): e.get("value") or {} for e in rs.get("entries") or []}
        res = entries.get("result", {}).get("result")
        groups.append(AggregateGroup(group=entries.get("group", {}).get("value"), result=float(res) if res is not None else None))
    return AggregateOut(groups=groups)


# --- monday.activity.list_board ------------------------------------------------------------------

class ListActivityIn(BaseModel):
    board_id: str = BOARD_ID
    from_date: Optional[str] = Field(default=None, description="Only events on or after this ISO 8601 date and time, for example 2026-03-01T00:00:00Z")
    to_date: Optional[str] = Field(default=None, description="Only events on or before this ISO 8601 date and time")
    item_ids: list[str] = Field(default_factory=list, max_length=100, description="Only events of these item ids; leave empty for every item")
    user_ids: list[str] = Field(default_factory=list, max_length=100, description="Only events made by these user ids; leave empty for every user")
    limit: int = Field(default=25, ge=1, le=100, description="How many events to return in this page, from 1 to 100 (default 25)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1; ask for the next page while a full page comes back")


class ActivityEvent(BaseModel):
    id: str = Field(description="Id of the activity event")
    event: str = Field(description="What happened, for example update_column_value, create_pulse or move_pulse_into_group")
    entity: Optional[str] = Field(default=None, description="What was changed: board or pulse (item)")
    user_id: Optional[str] = Field(default=None, description="Id of the user who made the change")
    created_at: Optional[str] = Field(default=None, description="Time of the event as monday 17 digit timestamp (divide by 10000 for milliseconds)")
    data: Optional[str] = Field(default=None, description="JSON text with the details of the change, for example the old and new column value")


class ListActivityOut(BaseModel):
    events: list[ActivityEvent] = Field(description="Activity events of the board, newest first")


@function(
    id="monday.activity.list_board", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Lists the activity log of one monday.com board, newest first: who changed what and when (column value changes, items created, moved or "
        "deleted...), optionally only between two dates, for some items or for some users, with page-based pagination. Each event has its id, kind, "
        "entity, user, time and a JSON text with the details. Use it when the user asks what changed on a board, who moved a deal or when a status "
        "changed. monday keeps up to 10,000 events per board. Read-only."
    ),
    examples=[{"name": "default", "input": {"board_id": "1234567890", "limit": 1}, "output": {"events": [
        {"id": "a1b2", "event": "update_column_value", "entity": "pulse", "user_id": "4012689", "created_at": "17409456000000000",
         "data": "{\"column_id\":\"status\",\"value\":{\"label\":{\"text\":\"Done\"}}}"}]}}],
)
async def activity_list_board(ctx: Context, args: ListActivityIn) -> ListActivityOut:
    filters = _args(**{"from": args.from_date}, to=args.to_date, item_ids=args.item_ids, user_ids=args.user_ids, limit=args.limit, page=args.page)
    query = f"query ($ids: [ID!]) {{ boards(ids: $ids) {{ activity_logs{filters} {{ id event entity user_id created_at data }} }} }}"
    board = await _one_board(ctx, query, {"ids": [args.board_id]}, args.board_id)
    return ListActivityOut(events=[
        ActivityEvent(id=str(e["id"]), event=e["event"], entity=e.get("entity"), user_id=_sid(e.get("user_id")),
                      created_at=_sid(e.get("created_at")), data=e.get("data"))
        for e in board.get("activity_logs") or []])


# --- monday.audit.list ---------------------------------------------------------------------------

class ListAuditIn(BaseModel):
    start_time: Optional[str] = Field(default=None, description="Only events from this ISO 8601 date and time on")
    end_time: Optional[str] = Field(default=None, description="Only events up to this ISO 8601 date and time")
    events: list[str] = Field(default_factory=list, max_length=50, description="Only these event kinds, for example login or logout; leave empty for all")
    user_id: Optional[str] = Field(default=None, pattern=r"^\d+$", description="Only events of this user id; leave empty for every user")
    ip_address: Optional[str] = Field(default=None, max_length=64, description="Only events from this IP address; leave empty for any address")
    limit: int = Field(default=25, ge=1, le=1000, description="How many events to return in this page, from 1 to 1000 (default 25)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1")


class AuditEntry(BaseModel):
    timestamp: Optional[str] = Field(default=None, description="Date and time of the security event")
    event: Optional[str] = Field(default=None, description="Kind of security event, for example login or export_board")
    user: Optional[Person] = Field(default=None, description="User who caused the event")
    user_email: Optional[str] = Field(default=None, description="Email address of that user")
    ip_address: Optional[str] = Field(default=None, description="IP address the event came from")
    user_agent: Optional[str] = Field(default=None, description="Browser or client that was used")


class ListAuditOut(BaseModel):
    logs: list[AuditEntry] = Field(description="Security events of this page")
    next_page: Optional[int] = Field(default=None, description="Number of the next page, empty when there are no more pages")


@function(
    id="monday.audit.list", version=1, verb=Verb.read, upstream_api=API, scopes=[],
    description=(
        "Lists the security audit log of the connected monday.com account (logins, logouts, board exports and other security events), optionally "
        "filtered by dates, event kinds, user or IP address, with page-based pagination. Each entry has its time, event, user, IP address and client. "
        "Only works for account admins with the manage account security permission on the monday Enterprise plan; other accounts get an error. Use "
        "it when an admin asks who logged in or exported data. Read-only."
    ),
    examples=[{"name": "default", "input": {"events": ["login"], "limit": 1}, "output": {"logs": [
        {"timestamp": "2026-03-02T09:00:00Z", "event": "login", "user": {"id": "4012689", "name": "Ana Perez"}, "user_email": "ana@empresa.test",
         "ip_address": "203.0.113.5", "user_agent": "Chrome"}], "next_page": 2}}],
)
async def audit_list(ctx: Context, args: ListAuditIn) -> ListAuditOut:
    filters = _args(start_time=args.start_time, end_time=args.end_time, events=args.events, user_id=args.user_id, ip_address=args.ip_address,
                    limit=args.limit, page=args.page)
    query = (f"query {{ audit_logs{filters} {{ "
             "logs { timestamp event user_agent ip_address user { id name email } } pagination { has_more_pages next_page_number } } }")
    data = (await _gql(ctx, query, {})).get("audit_logs") or {}
    pag = data.get("pagination") or {}
    return ListAuditOut(logs=[
        AuditEntry(timestamp=_sid(entry.get("timestamp")), event=entry.get("event"), user=_person(entry.get("user")),
                   user_email=(entry.get("user") or {}).get("email"), ip_address=entry.get("ip_address"), user_agent=entry.get("user_agent"))
        for entry in data.get("logs") or []], next_page=pag.get("next_page_number") if pag.get("has_more_pages") else None)


# --- monday.object_relation.list -----------------------------------------------------------------

class ListRelationsIn(BaseModel):
    object_id: str = Field(pattern=r"^\d+$", description="Id of the board or dashboard whose relations are listed")
    kind: Optional[Literal["ALIAS", "DEPENDENCY"]] = Field(default=None, description="Only relations of this kind: ALIAS or DEPENDENCY; leave empty for both")
    direction: Literal["OUTGOING", "INCOMING"] = Field(default="OUTGOING", description="OUTGOING (default) for relations that start at the object, INCOMING for those that point to it")


class Relation(BaseModel):
    id: Optional[str] = Field(default=None, description="Relation id")
    source_object_id: Optional[str] = Field(default=None, description="Object the relation starts from")
    target_id: Optional[str] = Field(default=None, description="Object the relation points to")
    target_object_type: Optional[str] = Field(default=None, description="Type of the target: BOARD or DASHBOARD")
    kind: Optional[str] = Field(default=None, description="Kind of relation, for example dependency or alias")


class ListRelationsOut(BaseModel):
    relations: list[Relation] = Field(description="Relations of the object")


@function(
    id="monday.object_relation.list", version=1, verb=Verb.read, upstream_api=API, scopes=[],
    description=(
        "Lists the relations of one monday.com board or dashboard with other boards or dashboards: dependencies and aliases, either the ones that "
        "start at the object (outgoing, default) or the ones that point to it (incoming), optionally only one kind. Each relation has its id, source, "
        "target, target type and kind. Use it when the user asks which boards depend on another one or what is linked to a dashboard. Read-only: it "
        "does not create or delete relations."
    ),
    examples=[{"name": "default", "input": {"object_id": "1234567890"}, "output": {"relations": [
        {"id": "27", "source_object_id": "1234567890", "target_id": "9876543210", "target_object_type": "BOARD", "kind": "dependency"}]}}],
)
async def object_relation_list(ctx: Context, args: ListRelationsIn) -> ListRelationsOut:
    filters = _args({"kind": args.kind, "direction": args.direction}, object_id=args.object_id)
    query = f"query {{ object_relations{filters} {{ id source_object_id target_id target_object_type kind }} }}"
    data = await _gql(ctx, query, {})
    return ListRelationsOut(relations=[
        Relation(id=_sid(r.get("id")), source_object_id=_sid(r.get("source_object_id")), target_id=_sid(r.get("target_id")),
                 target_object_type=r.get("target_object_type"), kind=r.get("kind"))
        for r in data.get("object_relations") or []])
