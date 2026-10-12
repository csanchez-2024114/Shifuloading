"""Funciones de lectura de monday.com (API GraphQL, version 2026-10).

Verificado en developer.monday.com (2026-10-07):
- Todo va por POST https://api.monday.com/v2 con {"query", "variables"} y el header API-Version.
- Los errores de aplicacion llegan con HTTP 200 y un arreglo `errors` (codigo en extensions.code): `missingRequiredPermissions` = falta
  un scope, `ResourceNotFoundException`/`Invalid*IdException` = no existe, `InvalidArgumentException` = entrada mala. Por eso `_gql` los
  revisa siempre; los de transporte (401, 403 UserUnauthorizedException, 429, 5xx) ya los traduce la conexion.
- Scopes: me -> me:read, account -> account:read, users -> users:read, boards/items -> boards:read, workspaces -> workspaces:read.
- items: boards(ids){items_page(limit, cursor)} para la primera pagina y next_items_page(cursor) para las siguientes (limite 500,
  el cursor vence a los 60 minutos).
POR COMPROBAR en una prueba real: los campos de `account.plan` en una cuenta gratis y `Board.type` (para distinguir subitems).

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente los usa para buscar la funcion
y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.functions.apps.monday.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

API_URL = "https://api.monday.com/v2"
API = "2026-10"

_ERROR_CODES = {
    "missingRequiredPermissions": ErrorCode.missing_scope,
    "UserUnauthorizedException": ErrorCode.missing_scope,
    "USER_ACCESS_DENIED": ErrorCode.missing_scope,
    "ResourceNotFoundException": ErrorCode.not_found,
    "InvalidBoardIdException": ErrorCode.not_found,
    "InvalidItemIdException": ErrorCode.not_found,
    "InvalidUserIdException": ErrorCode.not_found,
    "COMPLEXITY_BUDGET_EXHAUSTED": ErrorCode.rate_limited,
    "maxConcurrencyExceeded": ErrorCode.rate_limited,
    "API_TEMPORARILY_BLOCKED": ErrorCode.upstream_down,
}


async def _gql(ctx: Context, query: str, variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Ejecuta una consulta GraphQL y convierte el arreglo `errors` (que llega con HTTP 200) en FunctionError."""
    body = (await ctx.conn.request("POST", API_URL, json={"query": query, "variables": variables or {}},
                                   headers={"API-Version": API})).json()
    errors = body.get("errors") or []
    if errors:
        first = errors[0]
        code = (first.get("extensions") or {}).get("code") or ""
        raise FunctionError(_ERROR_CODES.get(code, ErrorCode.invalid_input),
                            f"monday rechazo la consulta ({code or 'sin codigo'}): {str(first.get('message', ''))[:150]}")
    if body.get("error_code") or body.get("error_message"):  # formato viejo de error, por si una version lo devuelve
        code = str(body.get("error_code") or "")
        raise FunctionError(_ERROR_CODES.get(code, ErrorCode.invalid_input),
                            f"monday rechazo la consulta ({code or 'sin codigo'}): {str(body.get('error_message', ''))[:150]}")
    return body.get("data") or {}


# --- monday.user.get (whoami) --------------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="monday user id of the person who connected, the same value stored when the account was connected")
    display_name: str = Field(description="Full name of the connected monday user")
    email: Optional[str] = Field(default=None, description="Email address of the connected monday user")
    title: Optional[str] = Field(default=None, description="Job title set in the user's monday profile")
    status: Optional[str] = Field(default=None, description="Activation status of the user: ACTIVE, INACTIVE or PENDING (invitation not accepted yet)")
    monday_account_id: Optional[str] = Field(default=None, description="Id of the monday account (organization) the user belongs to")
    monday_account_name: Optional[str] = Field(default=None, description="Name of the monday account (organization)")
    monday_account_slug: Optional[str] = Field(default=None, description="Subdomain of the monday account, as in <slug>.monday.com")


@function(
    id="monday.user.get", version=1, verb=Verb.read, upstream_api=API, scopes=["me:read"],
    description=(
        "Returns the monday.com user who is connected: the user id, full name, email address, job title, activation status, and "
        "the monday account (organization) it belongs to with its id, name and subdomain. Use it to confirm which monday.com user and account are being "
        "used, to answer questions such as 'which monday account do I have connected?', or to check that the connection still works before reading "
        "boards. Read-only: it takes no parameters and does not change anything in monday.com. If the user has several monday accounts connected, one "
        "of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "4012689", "display_name": "Ana Perez", "email": "ana@empresa.test", "title": "Manager", "status": "ACTIVE",
        "monday_account_id": "18888528", "monday_account_name": "Empresa Demo", "monday_account_slug": "empresademo"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    data = await _gql(ctx, "query { me { id name email title status account { id name slug } } }")
    me = data["me"]
    account = me.get("account") or {}
    return Me(account_id=str(me["id"]), display_name=me.get("name") or str(me["id"]), email=me.get("email"), title=me.get("title"),
              status=me.get("status"),
              monday_account_id=str(account["id"]) if account.get("id") is not None else None,
              monday_account_name=account.get("name"), monday_account_slug=account.get("slug"))


# --- monday.account.get --------------------------------------------------------------------------

class Account(BaseModel):
    id: str = Field(description="Id of the monday account (organization)")
    name: Optional[str] = Field(default=None, description="Name of the monday account")
    slug: Optional[str] = Field(default=None, description="Subdomain of the account, as in <slug>.monday.com")
    country_code: Optional[str] = Field(default=None, description="Two letter country code of the account")
    active_members_count: Optional[int] = Field(default=None, description="Number of active members in the account")
    plan_tier: Optional[str] = Field(default=None, description="Plan tier, for example free, basic, standard, pro or enterprise")
    plan_max_users: Optional[int] = Field(default=None, description="Maximum number of seats included in the plan")
    plan_period: Optional[str] = Field(default=None, description="Billing period of the plan, for example monthly or yearly")


@function(
    id="monday.account.get", version=1, verb=Verb.read, upstream_api=API, scopes=["account:read"],
    description=(
        "Returns the monday.com account (organization) of the connected user: its id, name, subdomain, country code, number of active members and the "
        "plan details (tier such as free, standard, pro or enterprise, the maximum number of seats and the billing period). Use it when the user asks "
        "about their monday plan, how many members the account has, or which features the plan may include. Read-only: it takes no parameters and "
        "does not change anything. To know who the connected person is use monday.user.get instead."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "id": "18888528", "name": "Empresa Demo", "slug": "empresademo", "country_code": "GT", "active_members_count": 4,
        "plan_tier": "standard", "plan_max_users": 5, "plan_period": "monthly"}}],
)
async def account_get(ctx: Context, args: NoArgs) -> Account:
    data = await _gql(ctx, "query { account { id name slug country_code active_members_count plan { tier max_users period } } }")
    acc = data["account"]
    plan = acc.get("plan") or {}
    return Account(id=str(acc["id"]), name=acc.get("name"), slug=acc.get("slug"), country_code=acc.get("country_code"),
                   active_members_count=acc.get("active_members_count"), plan_tier=plan.get("tier"),
                   plan_max_users=plan.get("max_users"), plan_period=plan.get("period"))


# --- monday.user.list ----------------------------------------------------------------------------

class ListUsersIn(BaseModel):
    kind: Literal["all", "non_guests", "guests", "non_pending"] = Field(default="all", description="Which users to include: all (default), non_guests, guests, or non_pending (accepted invitations only)")
    emails: list[str] = Field(default_factory=list, max_length=100, description="Return only the users with these email addresses; leave empty to not filter by email")
    name: Optional[str] = Field(default=None, description="Return only users whose name contains this text; leave empty to not filter by name")
    limit: int = Field(default=50, ge=1, le=100, description="How many users to return in this page, from 1 to 100 (default 50)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1; ask for the next page while a full page comes back")


class User(BaseModel):
    id: str = Field(description="monday user id")
    name: str = Field(description="Full name of the user")
    email: Optional[str] = Field(default=None, description="Email address of the user")
    title: Optional[str] = Field(default=None, description="Job title of the user")
    kind: Optional[str] = Field(default=None, description="Role of the user in the account, for example admin, member, guest or view_only")
    status: Optional[str] = Field(default=None, description="Activation status of the user: ACTIVE, INACTIVE or PENDING (invitation not accepted yet)")


class ListUsersOut(BaseModel):
    users: list[User] = Field(description="Users of this page")


@function(
    id="monday.user.list", version=1, verb=Verb.read, upstream_api=API, scopes=["users:read"],
    description=(
        "Lists the users of the connected monday.com account, optionally filtered by kind (members, guests, pending), by email addresses or by part of "
        "the name, with page-based pagination. Each user has the id, full name, email, job title, role (admin, member, guest or viewer) and activation "
        "status; deactivated users are not included. Use it when the user asks who is in their monday account, needs the id of a teammate to filter or assign items, or wants to find a "
        "person by email. At most 100 users per page; ask for page 2, 3 and so on while a full page comes back. Read-only: it does not invite, change or "
        "deactivate users."
    ),
    examples=[{"name": "default", "input": {"limit": 2}, "output": {"users": [
        {"id": "4012689", "name": "Ana Perez", "email": "ana@empresa.test", "title": "Manager", "kind": "admin", "status": "ACTIVE"}]}}],
)
async def user_list(ctx: Context, args: ListUsersIn) -> ListUsersOut:
    query = ("query ($limit: Int, $page: Int, $kind: UserKind, $emails: [String!], $name: String) { "
             "users(limit: $limit, page: $page, kind: $kind, emails: $emails, name: $name) { id name email title status user_config { kind } } }")
    data = await _gql(ctx, query, {"limit": args.limit, "page": args.page, "kind": args.kind, "emails": args.emails or None, "name": args.name})
    return ListUsersOut(users=[
        User(id=str(u["id"]), name=u.get("name") or "", email=u.get("email"), title=u.get("title"),
             kind=(u.get("user_config") or {}).get("kind"), status=u.get("status"))
        for u in data.get("users") or []])


# --- monday.workspace.list -----------------------------------------------------------------------

class ListWorkspacesIn(BaseModel):
    state: Literal["active", "archived", "deleted", "all"] = Field(default="active", description="Which workspaces to include: active (default), archived, deleted or all")
    limit: int = Field(default=25, ge=1, le=100, description="How many workspaces to return in this page, from 1 to 100 (default 25)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1; ask for the next page while a full page comes back")


class Workspace(BaseModel):
    id: Optional[str] = Field(default=None, description="Workspace id, usable to list the boards of that workspace")
    name: str = Field(description="Name of the workspace")
    kind: Optional[str] = Field(default=None, description="open (visible to the whole account) or closed (members only)")
    state: Optional[str] = Field(default=None, description="active, archived or deleted")
    description: Optional[str] = Field(default=None, description="Description of the workspace, if any")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the workspace was created")


class ListWorkspacesOut(BaseModel):
    workspaces: list[Workspace] = Field(description="Workspaces of this page")


@function(
    id="monday.workspace.list", version=1, verb=Verb.read, upstream_api=API, scopes=["workspaces:read"],
    description=(
        "Lists the workspaces of the connected monday.com account that the user can see, with page-based pagination. Each workspace has its id, name, "
        "kind (open or closed), state, description and creation date. Use it when the user asks how their monday account is organized, wants to see "
        "their workspaces, or needs a workspace id to list only the boards of one workspace with monday.board.list. By default only active "
        "workspaces are returned; at most 100 per page. Read-only: it does not create, rename or delete workspaces."
    ),
    examples=[{"name": "default", "input": {}, "output": {"workspaces": [
        {"id": "551234", "name": "Ventas", "kind": "open", "state": "active", "description": None, "created_at": "2026-01-02T10:00:00Z"}]}}],
)
async def workspace_list(ctx: Context, args: ListWorkspacesIn) -> ListWorkspacesOut:
    query = ("query ($limit: Int, $page: Int, $state: State) { "
             "workspaces(limit: $limit, page: $page, state: $state) { id name kind state description created_at } }")
    data = await _gql(ctx, query, {"limit": args.limit, "page": args.page, "state": args.state})
    return ListWorkspacesOut(workspaces=[
        Workspace(id=str(w["id"]) if w.get("id") is not None else None, name=w["name"], kind=w.get("kind"), state=w.get("state"),
                  description=w.get("description"), created_at=w.get("created_at"))
        for w in data.get("workspaces") or []])


# --- monday.board.list ---------------------------------------------------------------------------

class ListBoardsIn(BaseModel):
    workspace_ids: list[str] = Field(default_factory=list, max_length=50, description="Return only boards of these workspace ids; leave empty for boards of every workspace")
    state: Literal["active", "archived", "deleted", "all"] = Field(default="active", description="Which boards to include: active (default), archived, deleted or all")
    order_by: Literal["created_at", "used_at"] = Field(default="used_at", description="Sort order: used_at (most recently used first, default) or created_at (newest first)")
    limit: int = Field(default=25, ge=1, le=100, description="How many boards to return in this page, from 1 to 100 (default 25)")
    page: int = Field(default=1, ge=1, description="Page number starting at 1; ask for the next page while a full page comes back")


class Board(BaseModel):
    id: str = Field(description="Board id, usable to list its items with monday.item.list")
    name: str = Field(description="Name of the board")
    state: Optional[str] = Field(default=None, description="active, archived or deleted")
    board_kind: Optional[str] = Field(default=None, description="public, private or share (shareable with guests)")
    board_type: Optional[str] = Field(default=None, description="board, sub_items_board (holds the subitems of another board) or document")
    description: Optional[str] = Field(default=None, description="Description of the board, if any")
    workspace_id: Optional[str] = Field(default=None, description="Id of the workspace that contains the board")
    items_count: Optional[int] = Field(default=None, description="Number of items on the board")
    updated_at: Optional[str] = Field(default=None, description="UTC date and time of the last change to the board")
    url: Optional[str] = Field(default=None, description="Link to open the board in monday.com")


class ListBoardsOut(BaseModel):
    boards: list[Board] = Field(description="Boards of this page")


@function(
    id="monday.board.list", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Lists the boards of the connected monday.com account that the user can see, optionally only those of some workspaces, sorted by last use or "
        "creation date, with page-based pagination. Each board has its id, name, state, kind (public, private or shareable), type (a normal board or "
        "the subitems board of another one), description, workspace id, number of items, last update and link. Use it when the user asks which boards "
        "or projects they have, wants to find a board by name, or needs a board id to read its items with monday.item.list. By default only active "
        "boards; at most 100 per page. Read-only: it does not create, change or archive boards and it does not return the items."
    ),
    examples=[{"name": "default", "input": {"limit": 1}, "output": {"boards": [
        {"id": "1234567890", "name": "Pipeline de ventas", "state": "active", "board_kind": "public", "board_type": "board", "description": None,
         "workspace_id": "551234", "items_count": 12, "updated_at": "2026-03-01T09:00:00Z", "url": "https://empresademo.monday.com/boards/1234567890"}]}}],
)
async def board_list(ctx: Context, args: ListBoardsIn) -> ListBoardsOut:
    query = ("query ($limit: Int, $page: Int, $state: State, $order_by: BoardsOrderBy, $workspace_ids: [ID]) { "
             "boards(limit: $limit, page: $page, state: $state, order_by: $order_by, workspace_ids: $workspace_ids) { "
             "id name state board_kind type description workspace_id items_count updated_at url } }")
    data = await _gql(ctx, query, {"limit": args.limit, "page": args.page, "state": args.state, "order_by": args.order_by,
                                   "workspace_ids": args.workspace_ids or None})
    return ListBoardsOut(boards=[
        Board(id=str(b["id"]), name=b["name"], state=b.get("state"), board_kind=b.get("board_kind"), board_type=b.get("type"),
              description=b.get("description"), workspace_id=str(b["workspace_id"]) if b.get("workspace_id") is not None else None,
              items_count=b.get("items_count"), updated_at=b.get("updated_at"), url=b.get("url"))
        for b in data.get("boards") or []])


# --- monday.item.list ----------------------------------------------------------------------------

class ListItemsIn(BaseModel):
    board_id: str = Field(pattern=r"^\d+$", description="Id of the board whose items are listed, as returned by monday.board.list (digits only)")
    limit: int = Field(default=25, ge=1, le=500, description="How many items to return in this page, from 1 to 500 (default 25)")
    cursor: Optional[str] = Field(default=None, description="Cursor returned by a previous call to read the next page; it expires after 60 minutes. Leave empty for the first page")


class ColumnValue(BaseModel):
    id: str = Field(description="Column id on the board, for example 'status' or 'date4'")
    type: Optional[str] = Field(default=None, description="Column type, for example status, date, people, numbers or text")
    text: Optional[str] = Field(default=None, description="Value of the column as the user sees it, empty if not set")


class Item(BaseModel):
    id: str = Field(description="Item id")
    name: str = Field(description="Name of the item")
    state: Optional[str] = Field(default=None, description="active, archived or deleted")
    group_id: Optional[str] = Field(default=None, description="Id of the group (section) of the board that holds the item")
    group_title: Optional[str] = Field(default=None, description="Title of that group, for example 'This week' or 'Done'")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the item was created")
    updated_at: Optional[str] = Field(default=None, description="UTC date and time of the last change to the item")
    column_values: list[ColumnValue] = Field(default_factory=list, description="Value of each column of the board for this item")


class ListItemsOut(BaseModel):
    items: list[Item] = Field(description="Items of this page")
    cursor: Optional[str] = Field(default=None, description="Cursor for the next page; empty when there are no more items")


_ITEM_FIELDS = "id name state created_at updated_at group { id title } column_values { id type text }"


def _item(raw: dict[str, Any]) -> Item:
    group = raw.get("group") or {}
    return Item(id=str(raw["id"]), name=raw["name"], state=raw.get("state"), group_id=group.get("id"), group_title=group.get("title"),
                created_at=raw.get("created_at"), updated_at=raw.get("updated_at"),
                column_values=[ColumnValue(id=c["id"], type=c.get("type"), text=c.get("text")) for c in raw.get("column_values") or []])


@function(
    id="monday.item.list", version=1, verb=Verb.read, upstream_api=API, scopes=["boards:read"],
    description=(
        "Lists the items (rows) of one monday.com board with cursor pagination. Each item has its id, name, state, the group (section) it belongs to, "
        "its creation and update dates, and the value of every column as the user sees it (for example status 'Working on it', a date, an owner or a "
        "number). Use it when the user asks what is on a board, wants to review tasks, deals or projects tracked in monday, or needs item ids for a later "
        "step. Up to 500 items per page; pass the returned cursor to read the next page within 60 minutes. Read-only: it does not create, change or "
        "move items, and it does not list boards (use monday.board.list to find the board id first)."
    ),
    examples=[{"name": "default", "input": {"board_id": "1234567890", "limit": 1}, "output": {"items": [
        {"id": "987654321", "name": "Cliente Demo", "state": "active", "group_id": "topics", "group_title": "Nuevos",
         "created_at": "2026-02-01T10:00:00Z", "updated_at": "2026-03-01T09:00:00Z",
         "column_values": [{"id": "status", "type": "status", "text": "Working on it"}]}], "cursor": "MSw5NzI4MDA5MDAsaV9Yd"}}],
)
async def item_list(ctx: Context, args: ListItemsIn) -> ListItemsOut:
    if args.cursor:
        query = f"query ($cursor: String!, $limit: Int!) {{ next_items_page(cursor: $cursor, limit: $limit) {{ cursor items {{ {_ITEM_FIELDS} }} }} }}"
        page = (await _gql(ctx, query, {"cursor": args.cursor, "limit": args.limit}))["next_items_page"]
    else:
        query = f"query ($ids: [ID!], $limit: Int!) {{ boards(ids: $ids) {{ items_page(limit: $limit) {{ cursor items {{ {_ITEM_FIELDS} }} }} }} }}"
        boards = (await _gql(ctx, query, {"ids": [args.board_id], "limit": args.limit})).get("boards") or []
        if not boards:
            raise FunctionError(ErrorCode.not_found, f"No existe el tablero {args.board_id} en monday o no tienes acceso.")
        page = boards[0]["items_page"]
    return ListItemsOut(items=[_item(i) for i in page.get("items") or []], cursor=page.get("cursor"))


from app.functions.apps.monday import reads  # noqa: E402,F401  (load_all solo importa functions.py)
