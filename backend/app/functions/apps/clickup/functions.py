"""Funciones de lectura de ClickUp.

Entrada de la app: registra whoami y carga los demas modulos (el registro solo importa `app_spec` y `functions`).
  f_workspace.py   Workspaces, plan, asientos, grupos, roles, invitados, jerarquia compartida, webhooks, tipos de post
  f_hierarchy.py   Spaces, carpetas, listas, etiquetas, campos personalizados, tipos de tarea y vistas
  f_tasks.py       Tareas, comentarios, adjuntos, tiempo en estado y miembros de tarea
  f_time_goals.py  Registros de tiempo, temporizador y metas
  f_chat_docs.py   Chat (canales y mensajes), Docs, paginas y registro de auditoria

Fuente de verdad de rutas y parametros: OpenAPI oficial v2 y v3 de ClickUp (2026-10-08). Donde el catalogo ATENCION/tareas/clickup.md
difiere de la API real, ver la seccion "Diferencias con el catalogo" de docs/funciones/sprints/clickup.md.
Las descripciones y los Field(description=...) estan en INGLES a proposito (las lee el agente; ver docs/funciones/CONTRATO.md).
"""
from typing import Optional

from pydantic import Field

from app.functions.apps.clickup._common import V2, Ident, NoArgs, Out, WorkspaceIn, get, items, obj
from app.functions.apps.clickup.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb


# --- clickup.user.get (whoami) ---------------------------------------------------------------------

class UserOut(Out):
    account_id: str = Field(description="ClickUp user id of the connected account (the same value stored when the account was connected)")
    display_name: Optional[str] = Field(default=None, description="Username (display name) of the connected ClickUp user")
    email: Optional[str] = Field(default=None, description="Email address of the connected ClickUp user")


@function(
    id="clickup.user.get", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the ClickUp user that owns the connected account: the user id, the username (display name) and the email address, plus profile details "
        "such as color, initials and time zone. Use it to confirm which ClickUp account is connected, to answer questions such as 'which ClickUp account do I "
        "have connected?', or to check that the connection still works before reading anything else. Read-only: it takes no parameters, does not list "
        "Workspaces (use clickup.workspaces.list for that) and does not change anything in ClickUp. If several ClickUp accounts are connected, one must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "123456", "display_name": "John Doe", "email": "john@example.com"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> UserOut:
    user = obj(obj(await get(ctx, f"{V2}/user")).get("user"))
    if user.get("id") is None:
        raise FunctionError(ErrorCode.upstream_changed, "ClickUp no devolvio el id del usuario.")
    rest = {k: v for k, v in user.items() if k not in ("id", "username", "email")}
    return UserOut(account_id=str(user["id"]), display_name=user.get("username"), email=user.get("email"), **rest)


# --- clickup.workspaces.list -----------------------------------------------------------------------

class WorkspaceItem(Out):
    id: Ident = Field(default=None, description="Workspace id (named team_id in other endpoints)")
    name: Optional[str] = Field(default=None, description="Name of the Workspace")
    color: Optional[str] = Field(default=None, description="Color of the Workspace as a hex string")
    avatar: Optional[str] = Field(default=None, description="URL of the Workspace avatar, if it has one")
    member_count: Optional[int] = Field(default=None, description="Number of members of the Workspace")


class WorkspacesOut(Out):
    teams: list[WorkspaceItem] = Field(default_factory=list, description="Workspaces the connected user authorized for this connection")


@function(
    id="clickup.workspaces.list", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Lists the ClickUp Workspaces (called teams in the API) that the connected user authorized for this connection. For each one it returns the Workspace id, "
        "name, color, avatar and the number of members. Use it first when the user asks 'which workspaces do I have?', or whenever another ClickUp function needs "
        "a workspace_id. Read-only and without parameters. It does not return the members themselves, the spaces or the tasks: use clickup.spaces.list for the "
        "spaces of a Workspace and clickup.lists.get_members for people."
    ),
    examples=[{"name": "default", "input": {}, "output": {"teams": [{"id": "9001", "name": "My Workspace", "color": "#7b68ee", "member_count": 4}]}}],
)
async def workspaces_list(ctx: Context, args: NoArgs) -> WorkspacesOut:
    teams = []
    for t in items(await get(ctx, f"{V2}/team"), "teams"):
        t = obj(t)
        rest = {k: v for k, v in t.items() if k not in ("id", "name", "color", "avatar", "members")}
        teams.append(WorkspaceItem(id=t.get("id"), name=t.get("name"), color=t.get("color"), avatar=t.get("avatar"),
                                   member_count=len(t["members"]) if isinstance(t.get("members"), list) else None, **rest))
    return WorkspacesOut(teams=teams)


# --- clickup.workspace.get_plan --------------------------------------------------------------------

class PlanOut(Out):
    plan_name: Optional[str] = Field(default=None, description="Name of the ClickUp plan of the Workspace, for example 'Business'")
    plan_id: Ident = Field(default=None, description="Numeric id of the ClickUp plan")


@function(
    id="clickup.workspace.get_plan", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the ClickUp subscription plan of a Workspace: the plan name (Free Forever, Unlimited, Business, Enterprise...) and the numeric plan id. Use it when "
        "the user asks which plan a Workspace is on, or to check whether plan-restricted features (goals, guests, audit logs, custom roles) are available before "
        "calling those functions. Requires workspace_id (see clickup.workspaces.list). Read-only. It does not return billing data, prices or seat usage: use "
        "clickup.workspace.get_seats for seats. ClickUp may answer with an error for Workspaces whose plan does not expose this information."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {"plan_name": "Business", "plan_id": 3}}],
)
async def workspace_get_plan(ctx: Context, args: WorkspaceIn) -> PlanOut:
    return PlanOut(**obj(await get(ctx, f"{V2}/team/{args.workspace_id}/plan")))


# --- clickup.workspace.get_seats -------------------------------------------------------------------

class SeatsOut(Out):
    members: Optional[dict] = Field(default=None, description="Member seats: filled_members_seats, total_member_seats and empty_member_seats")
    guests: Optional[dict] = Field(default=None, description="Guest seats: filled_guest_seats, total_guest_seats and empty_guest_seats")


@function(
    id="clickup.workspace.get_seats", version=1, verb=Verb.read, upstream_api="v2", scopes=[],
    description=(
        "Returns the seat usage of a ClickUp Workspace: for members and for guests, how many seats are filled, how many exist in total and how many are empty. "
        "Use it when the user asks 'how many licenses or seats are left?' or before inviting people. Requires workspace_id (see clickup.workspaces.list). "
        "Read-only: it does not invite or remove anyone and does not list the people who hold the seats (use clickup.lists.get_members or clickup.workspace.get_groups "
        "for people). The plan itself is returned by clickup.workspace.get_plan. Only Workspace owners and admins can see seats."
    ),
    examples=[{"name": "default", "input": {"workspace_id": "9001"}, "output": {
        "members": {"filled_members_seats": 3, "total_member_seats": 10, "empty_member_seats": 7},
        "guests": {"filled_guest_seats": 1, "total_guest_seats": 5, "empty_guest_seats": 4}}}],
)
async def workspace_get_seats(ctx: Context, args: WorkspaceIn) -> SeatsOut:
    return SeatsOut(**obj(await get(ctx, f"{V2}/team/{args.workspace_id}/seats")))


from app.functions.apps.clickup import f_workspace, f_hierarchy, f_tasks, f_time_goals, f_chat_docs, f_legacy  # noqa: E402,F401  (registran el resto)
