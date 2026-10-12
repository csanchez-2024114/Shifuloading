"""Funciones de lectura avanzadas de Asana (API 1.0): Tareas 7 y 8 del sprint (28 funciones).

Tarea 7: typeahead, reactions, allocations, project_briefs, project_portfolio_settings, ooo_entries, rates, roles, access_requests,
jobs, agents y ai_studio. Tarea 8: time_periods, timesheet_approval_statuses, custom_types y user_task_lists.

Fuente de verdad: OpenAPI oficial de Asana (github.com/Asana/openapi, defs/asana_oas.yaml, 2026-10-08). El catalogo
ATENCION/tareas/asana.md lo genero una IA y difiere de la API real en lo siguiente:
- asana.typeahead.search: el filtro obligatorio se llama `resource_type` (el `type` del catalogo esta deprecado) y la lista de tipos es
  actor, agent, custom_field, goal, project, project_template, portfolio, tag, task, team, user. No hay paginacion, solo `count` (1-100).
- asana.reactions.list: NO existe GET /{resource_path}/reactions; es GET /reactions con `target` (gid de un status update o de una story)
  y `emoji_base` (un emoji) obligatorios, y la reaccion trae {gid, emoji, user}.
- asana.allocations.*: los campos reales son start_date/end_date (no `from`/`to`) y `effort` es {type: hours|percent, value}; la lista
  filtra por parent (proyecto), assignee y workspace (no hay `user_gid`/`project_gid`).
- asana.project_briefs.get: el parametro de ruta es project_brief_gid y el cuerpo trae title/text/html_text/permalink_url/project.
- asana.ooo_entries.*: no existe GET /users/{user_gid}/ooo_entries; la lista es GET /ooo_entries con `user` y `workspace` obligatorios, y
  los campos son start_date/end_date (no start_on/end_on).
- asana.rates.*: la tasa se llama `rate` y trae `currency_code` (no `currency`); la lista filtra por parent (proyecto) y resource.
- asana.roles.list: `workspace` es OBLIGATORIO (y hay filtro `archived`). El detalle trae base_role_type, permissions y modified_at.
- asana.access_requests.list: `target` (gid del objeto) es OBLIGATORIO, no hay limit/offset y el campo es approval_status
  (pending|approved|denied) con requester y target.
- asana.jobs.get: el estado es `status` (not_started|in_progress|succeeded|failed) y trae los objetos nuevos (new_project, new_task...).
- asana.agents.*: sin scope granular publicado; solo existen name, description, behavior_guidance, workspace y resource_subtype.
- asana.ai_studio_usage.*: las rutas son /ai_studio/runs y /ai_studio/seats (con barra, no guion bajo); seats solo responde a una
  cuenta de servicio (Service Account) de una organizacion con licencia de AI Studio, y las dos son paginadas.
- asana.time_periods.*: `workspace` es obligatorio en la lista y el campo es `period` (FY, H1, H2, Q1..Q4) mas display_name.
- asana.timesheet_approval_statuses.*: `workspace` es obligatorio; los campos son start_date/end_date/approval_status
  (DRAFT|SUBMITTED|APPROVED|REJECTED), no `state`.
- asana.custom_types.list: filtra por `project` o `workspace`; cada tipo trae asana_created_type_identifier y status_options.
- asana.user_task_lists.get_user: GET /users/{user_gid}/user_task_list exige el query `workspace`. Los dos usan el scope tasks:read.
Las descripciones y los Field(description=...) estan en INGLES a proposito: el agente las usa para buscar la funcion y llenar sus
argumentos (ver doc/funciones/CONTRATO.md).
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.asana._common import PageIn, build_page, get_body, nested_gid, page_model, page_params
from app.functions.apps.asana.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

ResourceType = Literal["actor", "agent", "custom_field", "goal", "project", "project_template", "portfolio", "tag", "task", "team", "user"]


def _opt(*names: str) -> str:
    return ",".join(names)


# ==================================================================================================
# Tarea 7
# ==================================================================================================

# --- asana.typeahead.search -----------------------------------------------------------------------

class TypeaheadIn(BaseModel):
    workspace_gid: str = Field(description="Gid of the workspace or organization to search in")
    resource_type: ResourceType = Field(description="Kind of objects to return: actor, agent, custom_field, goal, project, project_template, portfolio, tag, task, team or user")
    query: str = Field(default="", description="Text to match against object names; an empty string returns a default set of results")
    count: int = Field(default=20, ge=1, le=100, description="Number of results to return, from 1 to 100 (default 20)")


class TypeaheadItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the matching object")
    resource_type: Optional[str] = Field(default=None, description="Kind of the matching object, for example 'project' or 'user'")
    name: Optional[str] = Field(default=None, description="Display name of the matching object")


TypeaheadOut = page_model(TypeaheadItem, "Matching objects")


@function(
    id="asana.typeahead.search", version=1, verb=Verb.read, upstream_api="1.0", scopes=["workspaces.typeahead:read"],
    description=(
        "Searches a workspace with Asana's fast autocomplete (typeahead) and returns the objects whose name matches a text: each result reports "
        "its gid, its resource type and its name. Use it to turn a name the user mentions into a gid, for example to find a project, task, tag, "
        "user, team, portfolio, goal or custom field called 'Marketing' before calling another function. It requires the workspace gid and the "
        "kind of object to look for; the query text is optional and count limits the results from 1 to 100. Read-only. Results are meant to be "
        "quick, not exhaustive, and there is no pagination; for precise filtering use asana.tasks.search or asana.projects.search."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "resource_type": "project", "query": "web"}, "output": {
        "items": [{"gid": "1200000000000100", "resource_type": "project", "name": "Web 2026"}], "has_more": False, "next_offset": None}}],
)
async def typeahead_search(ctx: Context, args: TypeaheadIn) -> TypeaheadOut:
    body = await get_body(ctx, f"/workspaces/{args.workspace_gid}/typeahead",
                          params={"resource_type": args.resource_type, "query": args.query, "count": args.count, "opt_fields": "name,resource_type"})
    return TypeaheadOut(items=[TypeaheadItem(gid=str(i["gid"]), resource_type=i.get("resource_type"), name=i.get("name")) for i in body.get("data") or []],
                        has_more=False, next_offset=None)


# --- asana.reactions.list -------------------------------------------------------------------------

class ReactionsListIn(PageIn):
    target: str = Field(description="Gid of the status update or story whose reactions should be listed")
    emoji_base: str = Field(description="Emoji character to filter by; only reactions that use this emoji are returned, for example a thumbs-up")


class ReactionItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the reaction")
    emoji: Optional[str] = Field(default=None, description="Emoji of the reaction, including any skin tone variation")
    user: Optional[str] = Field(default=None, description="Gid of the user who reacted")


ReactionsOut = page_model(ReactionItem, "Reactions")


@function(
    id="asana.reactions.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the emoji reactions that people left on an Asana status update or story (comment) for one given emoji: each reaction reports its "
        "gid, the emoji and the gid of the user who reacted. Use it when the user asks who liked, thumbs-upped or reacted with a specific emoji to a "
        "comment or a project status. It requires the gid of the status update or story (target) and the emoji to look for (emoji_base), because "
        "the API only returns one emoji at a time. Results are paginated with a limit of 1 to 100. Read-only. It does not add or remove "
        "reactions and it does not work on tasks or projects directly."
    ),
    examples=[{"name": "default", "input": {"target": "1200000000007000", "emoji_base": "👍"}, "output": {
        "items": [{"gid": "1200000000007100", "emoji": "👍", "user": "1200000000000001"}], "has_more": False, "next_offset": None}}],
)
async def reactions_list(ctx: Context, args: ReactionsListIn) -> ReactionsOut:
    body = await get_body(ctx, "/reactions", params={"target": args.target, "emoji_base": args.emoji_base, "limit": args.limit,
                                                      **({"offset": args.offset} if args.offset else {})})
    return build_page(ReactionsOut, body, lambda i: ReactionItem(gid=str(i["gid"]), emoji=i.get("emoji"), user=nested_gid(i, "user")))


# --- asana.allocations ----------------------------------------------------------------------------

ALLOCATION_FIELDS = _opt("start_date", "end_date", "effort.type", "effort.value", "assignee.name", "parent.name", "created_by.name", "resource_subtype")


class AllocationItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the allocation")
    start_date: Optional[str] = Field(default=None, description="First day of the allocation in YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="Last day of the allocation in YYYY-MM-DD")
    effort_type: Optional[str] = Field(default=None, description="Unit of the effort: 'hours' or 'percent'")
    effort_value: Optional[float] = Field(default=None, description="Amount of effort allocated, in the unit given by effort_type")
    assignee: Optional[str] = Field(default=None, description="Gid of the user or placeholder the time is allocated to")
    parent: Optional[str] = Field(default=None, description="Gid of the project the time is allocated on")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who created the allocation")
    resource_subtype: Optional[str] = Field(default=None, description="Subtype of the allocation, for example 'project_allocation'")


AllocationsOut = page_model(AllocationItem, "Allocations")


def _allocation(raw: dict) -> AllocationItem:
    effort = raw.get("effort") or {}
    return AllocationItem(gid=str(raw["gid"]), start_date=raw.get("start_date"), end_date=raw.get("end_date"),
                          effort_type=effort.get("type"), effort_value=effort.get("value"), assignee=nested_gid(raw, "assignee"),
                          parent=nested_gid(raw, "parent"), created_by=nested_gid(raw, "created_by"), resource_subtype=raw.get("resource_subtype"))


class AllocationGetIn(BaseModel):
    allocation_gid: str = Field(description="Gid of the allocation to fetch")


@function(
    id="asana.allocations.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns one Asana allocation, that is the planned effort of a person on a project: its gid, the start and end dates, the effort (hours or "
        "percent of capacity), the user or placeholder it is assigned to, the project it belongs to and who created it. Use it when the user "
        "asks how much time someone is planned to work on a project, or references an allocation gid from a list. It requires only the allocation "
        "gid. Read-only. It does not create or modify allocations and it does not list them; to list allocations of a project or a person use "
        "asana.allocations.list. Resource allocations are part of Asana's paid resource management features."
    ),
    examples=[{"name": "default", "input": {"allocation_gid": "1200000000007200"}, "output": {
        "gid": "1200000000007200", "start_date": "2026-10-01", "end_date": "2026-10-31", "effort_type": "hours", "effort_value": 20.0,
        "assignee": "1200000000000001", "parent": "1200000000000100", "created_by": "1200000000000001", "resource_subtype": "project_allocation"}}],
)
async def allocations_get(ctx: Context, args: AllocationGetIn) -> AllocationItem:
    body = await get_body(ctx, f"/allocations/{args.allocation_gid}", params={"opt_fields": ALLOCATION_FIELDS})
    return _allocation(body.get("data") or {})


class AllocationsListIn(PageIn):
    parent: Optional[str] = Field(default=None, description="Gid of the project to list allocations of")
    assignee: Optional[str] = Field(default=None, description="Gid of the user or placeholder to list allocations of")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace to restrict the allocations to")

    @model_validator(mode="after")
    def _needs_filter(self) -> "AllocationsListIn":
        if not (self.parent or self.assignee):
            raise ValueError("Provide parent (a project gid) or assignee (a user or placeholder gid) to filter the allocations")
        return self


@function(
    id="asana.allocations.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the Asana allocations (planned effort) of a project, a user or a placeholder: each one reports its gid, the date range, the effort in "
        "hours or percent, who it is assigned to and the project. Use it when the user asks who is planned to work on a project, how loaded a "
        "person is, or what the capacity plan looks like. At least one filter is required: parent (project gid) or assignee (user or placeholder "
        "gid); workspace can narrow the result. Results are paginated with a limit of 1 to 100. Read-only. It does not create allocations; "
        "for one allocation in detail use asana.allocations.get."
    ),
    examples=[{"name": "default", "input": {"parent": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000007200", "start_date": "2026-10-01", "end_date": "2026-10-31", "effort_type": "hours", "effort_value": 20.0,
                   "assignee": "1200000000000001", "parent": "1200000000000100", "created_by": "1200000000000001",
                   "resource_subtype": "project_allocation"}], "has_more": False, "next_offset": None}}],
)
async def allocations_list(ctx: Context, args: AllocationsListIn) -> AllocationsOut:
    body = await get_body(ctx, "/allocations", params=page_params(args.limit, args.offset, ALLOCATION_FIELDS, parent=args.parent,
                                                                  assignee=args.assignee, workspace=args.workspace))
    return build_page(AllocationsOut, body, _allocation)


# --- asana.project_briefs.get ---------------------------------------------------------------------

class ProjectBriefGetIn(BaseModel):
    project_brief_gid: str = Field(description="Gid of the project brief to fetch")


class ProjectBriefDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project brief")
    title: Optional[str] = Field(default=None, description="Title of the project brief")
    text: Optional[str] = Field(default=None, description="Plain text content of the project brief")
    html_text: Optional[str] = Field(default=None, description="Rich text content of the project brief as Asana HTML")
    permalink_url: Optional[str] = Field(default=None, description="URL of the project brief in the Asana web interface")
    project: Optional[str] = Field(default=None, description="Gid of the project the brief belongs to")


@function(
    id="asana.project_briefs.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns the brief of an Asana project: its gid, title, plain text, rich text (HTML), the link to open it in Asana and the gid of the "
        "project it belongs to. A project brief is the overview document that explains the goals, scope and context of a project. Use it when the "
        "user asks what a project is about or wants to read its brief. It requires the project brief gid, which can be found on the project. "
        "Read-only. It does not edit or create briefs and it does not return the tasks or the status updates of the project (use "
        "asana.tasks.list_project_tasks or asana.status_updates.list)."
    ),
    examples=[{"name": "default", "input": {"project_brief_gid": "1200000000007300"}, "output": {
        "gid": "1200000000007300", "title": "Web 2026 brief", "text": "Redesign of the corporate site.", "html_text": "<body>Redesign of the corporate site.</body>",
        "permalink_url": "https://app.asana.com/0/1200000000000100/overview", "project": "1200000000000100"}}],
)
async def project_briefs_get(ctx: Context, args: ProjectBriefGetIn) -> ProjectBriefDetail:
    body = await get_body(ctx, f"/project_briefs/{args.project_brief_gid}",
                          params={"opt_fields": _opt("title", "text", "html_text", "permalink_url", "project.name")})
    d = body.get("data") or {}
    return ProjectBriefDetail(gid=str(d["gid"]), title=d.get("title"), text=d.get("text"), html_text=d.get("html_text"),
                              permalink_url=d.get("permalink_url"), project=nested_gid(d, "project"))


# --- asana.project_portfolio_settings -------------------------------------------------------------

PPS_FIELDS = _opt("project.name", "portfolio.name", "is_access_control_inherited", "created_at")


class ProjectPortfolioSettingItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the project portfolio setting")
    project: Optional[str] = Field(default=None, description="Gid of the project the setting applies to")
    portfolio: Optional[str] = Field(default=None, description="Gid of the portfolio that contains the project")
    is_access_control_inherited: Optional[bool] = Field(default=None, description="True when the project inherits its access control from the portfolio")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the setting was created")


ProjectPortfolioSettingsOut = page_model(ProjectPortfolioSettingItem, "Project portfolio settings")


def _pps(raw: dict) -> ProjectPortfolioSettingItem:
    return ProjectPortfolioSettingItem(gid=str(raw["gid"]), project=nested_gid(raw, "project"), portfolio=nested_gid(raw, "portfolio"),
                                       is_access_control_inherited=raw.get("is_access_control_inherited"), created_at=raw.get("created_at"))


class PpsGetIn(BaseModel):
    project_portfolio_setting_gid: str = Field(description="Gid of the project portfolio setting to fetch")


@function(
    id="asana.project_portfolio_settings.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["project_portfolio_settings:read"],
    description=(
        "Returns one Asana project portfolio setting, the record that links a project to a portfolio: its gid, the gid of the project, the gid of "
        "the portfolio, whether the project inherits its access control from the portfolio and when the link was created. Use it when the user "
        "asks how a project is attached to a portfolio or whether it inherits permissions from it. It requires only the setting gid. Read-only. "
        "It does not change access control and it does not list settings; use asana.project_portfolio_settings.list_project or "
        "asana.project_portfolio_settings.list_portfolio to discover the gids."
    ),
    examples=[{"name": "default", "input": {"project_portfolio_setting_gid": "1200000000007400"}, "output": {
        "gid": "1200000000007400", "project": "1200000000000100", "portfolio": "1200000000007500",
        "is_access_control_inherited": True, "created_at": "2026-01-01T10:00:00.000Z"}}],
)
async def project_portfolio_settings_get(ctx: Context, args: PpsGetIn) -> ProjectPortfolioSettingItem:
    body = await get_body(ctx, f"/project_portfolio_settings/{args.project_portfolio_setting_gid}", params={"opt_fields": PPS_FIELDS})
    return _pps(body.get("data") or {})


class PpsForProjectIn(PageIn):
    project_gid: str = Field(description="Gid of the project whose portfolio settings should be listed")


@function(
    id="asana.project_portfolio_settings.list_project", version=1, verb=Verb.read, upstream_api="1.0", scopes=["project_portfolio_settings:read"],
    description=(
        "Lists the portfolio settings of an Asana project, that is the portfolios the project belongs to: each record reports its gid, the project, "
        "the portfolio, whether access control is inherited from the portfolio and its creation date. Use it when the user asks which portfolios "
        "include a given project. It requires the project gid and accepts the usual limit (1 to 100) and offset for pagination. Read-only. It "
        "does not modify portfolios; to see the settings from the portfolio side use asana.project_portfolio_settings.list_portfolio, and "
        "for the items of a portfolio use asana.portfolios.list_items."
    ),
    examples=[{"name": "default", "input": {"project_gid": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000007400", "project": "1200000000000100", "portfolio": "1200000000007500",
                   "is_access_control_inherited": True, "created_at": "2026-01-01T10:00:00.000Z"}], "has_more": False, "next_offset": None}}],
)
async def project_portfolio_settings_list_project(ctx: Context, args: PpsForProjectIn) -> ProjectPortfolioSettingsOut:
    body = await get_body(ctx, f"/projects/{args.project_gid}/project_portfolio_settings", params=page_params(args.limit, args.offset, PPS_FIELDS))
    return build_page(ProjectPortfolioSettingsOut, body, _pps)


class PpsForPortfolioIn(PageIn):
    portfolio_gid: str = Field(description="Gid of the portfolio whose project settings should be listed")


@function(
    id="asana.project_portfolio_settings.list_portfolio", version=1, verb=Verb.read, upstream_api="1.0", scopes=["project_portfolio_settings:read"],
    description=(
        "Lists the project settings of an Asana portfolio, that is how each project inside the portfolio is attached to it: each record reports "
        "its gid, the project, the portfolio, whether access control is inherited from the portfolio and its creation date. Use it when the user "
        "asks which projects a portfolio contains and how permissions flow down to them. It requires the portfolio gid and accepts the usual limit "
        "(1 to 100) and offset for pagination. Read-only. It does not move projects between portfolios; to see the portfolios of one project use "
        "asana.project_portfolio_settings.list_project."
    ),
    examples=[{"name": "default", "input": {"portfolio_gid": "1200000000007500"}, "output": {
        "items": [{"gid": "1200000000007400", "project": "1200000000000100", "portfolio": "1200000000007500",
                   "is_access_control_inherited": False, "created_at": "2026-01-01T10:00:00.000Z"}], "has_more": False, "next_offset": None}}],
)
async def project_portfolio_settings_list_portfolio(ctx: Context, args: PpsForPortfolioIn) -> ProjectPortfolioSettingsOut:
    body = await get_body(ctx, f"/portfolios/{args.portfolio_gid}/project_portfolio_settings", params=page_params(args.limit, args.offset, PPS_FIELDS))
    return build_page(ProjectPortfolioSettingsOut, body, _pps)


# --- asana.ooo_entries ----------------------------------------------------------------------------

OOO_FIELDS = _opt("start_date", "end_date", "user.name", "created_by.name")


class OooEntryItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the out-of-office entry")
    start_date: Optional[str] = Field(default=None, description="First day of the absence in YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="Last day of the absence in YYYY-MM-DD")
    user: Optional[str] = Field(default=None, description="Gid of the user who is out of office")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who created the entry")


OooEntriesOut = page_model(OooEntryItem, "Out-of-office entries")


def _ooo(raw: dict) -> OooEntryItem:
    return OooEntryItem(gid=str(raw["gid"]), start_date=raw.get("start_date"), end_date=raw.get("end_date"),
                        user=nested_gid(raw, "user"), created_by=nested_gid(raw, "created_by"))


class OooGetIn(BaseModel):
    ooo_entry_gid: str = Field(description="Gid of the out-of-office entry to fetch")


@function(
    id="asana.ooo_entries.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["ooo_entries:read"],
    description=(
        "Returns one out-of-office entry of Asana, that is a period of absence of a person: its gid, the first and last day of the absence, the "
        "gid of the user who is away and the gid of who created the entry. Use it when the user references an absence record or wants to "
        "confirm the dates of someone's time off. It requires only the entry gid. Read-only. It does not create, edit or delete absences; to "
        "find the entries of a person in a workspace use asana.ooo_entries.list."
    ),
    examples=[{"name": "default", "input": {"ooo_entry_gid": "1200000000007600"}, "output": {
        "gid": "1200000000007600", "start_date": "2026-12-22", "end_date": "2026-12-31", "user": "1200000000000001", "created_by": "1200000000000001"}}],
)
async def ooo_entries_get(ctx: Context, args: OooGetIn) -> OooEntryItem:
    body = await get_body(ctx, f"/ooo_entries/{args.ooo_entry_gid}", params={"opt_fields": OOO_FIELDS})
    return _ooo(body.get("data") or {})


class OooListIn(PageIn):
    user: str = Field(description="Gid of the user whose out-of-office entries should be listed")
    workspace: str = Field(description="Gid of the workspace or organization that contains the entries")
    start_date: Optional[str] = Field(default=None, description="ISO 8601 date (YYYY-MM-DD); keeps only entries that overlap with or end after this date")
    end_date: Optional[str] = Field(default=None, description="ISO 8601 date (YYYY-MM-DD); keeps only entries that overlap with or start before this date")


@function(
    id="asana.ooo_entries.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["ooo_entries:read"],
    description=(
        "Lists the out-of-office entries (periods of absence) of one Asana user in a workspace: each entry reports its gid, the first and last day "
        "of the absence, the user and who created it. Use it when the user asks whether a colleague is away, when someone returns, or who is on "
        "vacation in a date range. It requires the user gid and the workspace gid; start_date and end_date optionally keep only the entries that "
        "overlap that range. Results are paginated with a limit of 1 to 100. Read-only. It does not register absences and it does not list "
        "the entries of the whole team in one call."
    ),
    examples=[{"name": "default", "input": {"user": "1200000000000001", "workspace": "1200000000000002", "start_date": "2026-12-01"}, "output": {
        "items": [{"gid": "1200000000007600", "start_date": "2026-12-22", "end_date": "2026-12-31", "user": "1200000000000001",
                   "created_by": "1200000000000001"}], "has_more": False, "next_offset": None}}],
)
async def ooo_entries_list(ctx: Context, args: OooListIn) -> OooEntriesOut:
    body = await get_body(ctx, "/ooo_entries", params=page_params(args.limit, args.offset, OOO_FIELDS, user=args.user, workspace=args.workspace,
                                                                  start_date=args.start_date, end_date=args.end_date))
    return build_page(OooEntriesOut, body, _ooo)


# --- asana.rates ----------------------------------------------------------------------------------

RATE_FIELDS = _opt("parent.name", "resource.name", "rate", "currency_code", "created_by.name")


class RateItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the billing rate")
    parent: Optional[str] = Field(default=None, description="Gid of the project the rate applies to")
    resource: Optional[str] = Field(default=None, description="Gid of the user or placeholder the rate belongs to")
    rate: Optional[float] = Field(default=None, description="Amount charged per hour, in the currency of currency_code")
    currency_code: Optional[str] = Field(default=None, description="ISO 4217 currency code of the rate, for example 'USD'")
    created_by: Optional[str] = Field(default=None, description="Gid of the user who created the rate")


RatesOut = page_model(RateItem, "Billing rates")


def _rate(raw: dict) -> RateItem:
    return RateItem(gid=str(raw["gid"]), parent=nested_gid(raw, "parent"), resource=nested_gid(raw, "resource"), rate=raw.get("rate"),
                    currency_code=raw.get("currency_code"), created_by=nested_gid(raw, "created_by"))


class RatesListIn(PageIn):
    parent: Optional[str] = Field(default=None, description="Gid of the project to list the billing rates of")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace to list the billing rates of; an alternative to parent (Asana needs one of the two)")
    resource: Optional[str] = Field(default=None, description="Gid of a user or placeholder; keeps only the rate of that resource")

    @model_validator(mode="after")
    def _needs_a_scope(self):
        if not (self.parent or self.workspace):
            raise ValueError("Provide parent (a project gid) or workspace so Asana knows which billing rates to list")
        return self


@function(
    id="asana.rates.list", version=2, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the billing rates configured in Asana for a project or workspace: each rate reports its gid, the project, the user or placeholder it applies to, "
        "the amount per hour, the currency code and who created it. Use it when the user asks how much a person or role is billed per hour on a "
        "project, or wants to review the rates of a project. Give the parent project gid or the workspace gid (one of the two is required) and, to keep a single person, "
        "resource (a user or placeholder gid); results are paginated with a limit of 1 to 100. Read-only. It does not change rates and it needs the "
        "time-tracking and rates features of a paid Asana plan."
    ),
    examples=[{"name": "default", "input": {"parent": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000007700", "parent": "1200000000000100", "resource": "1200000000000001", "rate": 45.0,
                   "currency_code": "USD", "created_by": "1200000000000001"}], "has_more": False, "next_offset": None}}],
)
async def rates_list(ctx: Context, args: RatesListIn) -> RatesOut:
    body = await get_body(ctx, "/rates", params=page_params(args.limit, args.offset, RATE_FIELDS, parent=args.parent, workspace=args.workspace, resource=args.resource))
    return build_page(RatesOut, body, _rate)


class RateGetIn(BaseModel):
    rate_gid: str = Field(description="Gid of the billing rate to fetch")


@function(
    id="asana.rates.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns one billing rate of Asana: its gid, the project it applies to, the user or placeholder it belongs to, the amount charged per hour, "
        "the ISO currency code and who created it. Use it when the user references a rate gid from a list and wants its details, for example the "
        "hourly rate of a person on a project. It requires only the rate gid. Read-only. It does not create, update or delete rates and it does not "
        "list them; to find the rates of a project use asana.rates.list. Rates belong to the paid time-tracking and resource features."
    ),
    examples=[{"name": "default", "input": {"rate_gid": "1200000000007700"}, "output": {
        "gid": "1200000000007700", "parent": "1200000000000100", "resource": "1200000000000001", "rate": 45.0,
        "currency_code": "USD", "created_by": "1200000000000001"}}],
)
async def rates_get(ctx: Context, args: RateGetIn) -> RateItem:
    body = await get_body(ctx, f"/rates/{args.rate_gid}", params={"opt_fields": RATE_FIELDS})
    return _rate(body.get("data") or {})


# --- asana.roles ----------------------------------------------------------------------------------

class RoleItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the role")
    name: Optional[str] = Field(default=None, description="Name of the role")
    description: Optional[str] = Field(default=None, description="Description of what the role allows")
    is_standard_role: Optional[bool] = Field(default=None, description="True for the built-in roles (guest, member, admin, super admin), false for custom ones")


RolesOut = page_model(RoleItem, "Roles")


class RolesListIn(PageIn):
    workspace: str = Field(description="Gid of the workspace or organization whose roles should be listed")
    archived: bool = Field(default=False, description="When true, returns archived roles instead of active ones (default false)")


@function(
    id="asana.roles.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["roles:read"],
    description=(
        "Lists the role-based access control (RBAC) roles of an Asana workspace or organization: each role reports its gid, name, description and "
        "whether it is a built-in role or a custom one. Use it when the user asks which roles exist in the organization, what permission levels "
        "can be assigned or what custom roles an admin has created. It requires the workspace gid; the archived flag lists archived roles instead "
        "and results are paginated with a limit of 1 to 100. Read-only. It does not assign roles to people; for the permissions of a role "
        "use asana.roles.get. Custom roles need an Asana Enterprise plan."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000007800", "name": "Billing admin", "description": "Manages billing", "is_standard_role": False}],
        "has_more": False, "next_offset": None}}],
)
async def roles_list(ctx: Context, args: RolesListIn) -> RolesOut:
    body = await get_body(ctx, "/roles", params=page_params(args.limit, args.offset, _opt("name", "description", "is_standard_role"),
                                                            workspace=args.workspace, archived=args.archived))
    return build_page(RolesOut, body, lambda i: RoleItem(gid=str(i["gid"]), name=i.get("name"), description=i.get("description"),
                                                         is_standard_role=i.get("is_standard_role")))


class RoleGetIn(BaseModel):
    role_gid: str = Field(description="Gid of the role to fetch")


class RoleDetail(RoleItem):
    base_role_type: Optional[str] = Field(default=None, description="Built-in role the custom role is based on: guest, member, admin or super_admin")
    creation_time: Optional[str] = Field(default=None, description="UTC date and time when the role was created")
    modified_at: Optional[str] = Field(default=None, description="UTC date and time when the role was last modified")
    permissions: dict[str, Any] = Field(default_factory=dict, description="Permissions of the role as returned by Asana, for example assign_roles or export_project_data")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace or organization the role belongs to")


@function(
    id="asana.roles.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["roles:read"],
    description=(
        "Returns the full definition of one Asana role: its gid, name, description, whether it is a built-in role, the base role it is derived "
        "from (guest, member, admin or super admin), the creation and modification dates, the workspace and the map of permissions it grants, for "
        "example who can assign roles or export project data. Use it when the user asks what exactly a role can do. It requires only the role gid. "
        "Read-only. It does not create or edit roles and it does not list them; to discover role gids use asana.roles.list."
    ),
    examples=[{"name": "default", "input": {"role_gid": "1200000000007800"}, "output": {
        "gid": "1200000000007800", "name": "Billing admin", "description": "Manages billing", "is_standard_role": False, "base_role_type": "member",
        "creation_time": "2026-01-01T10:00:00.000Z", "modified_at": "2026-02-01T10:00:00.000Z", "permissions": {"assign_roles": False},
        "workspace": "1200000000000002"}}],
)
async def roles_get(ctx: Context, args: RoleGetIn) -> RoleDetail:
    body = await get_body(ctx, f"/roles/{args.role_gid}", params={"opt_fields": _opt(
        "name", "description", "is_standard_role", "base_role_type", "creation_time", "modified_at", "permissions", "workspace.name")})
    d = body.get("data") or {}
    return RoleDetail(gid=str(d["gid"]), name=d.get("name"), description=d.get("description"), is_standard_role=d.get("is_standard_role"),
                      base_role_type=d.get("base_role_type"), creation_time=d.get("creation_time"), modified_at=d.get("modified_at"),
                      permissions=d.get("permissions") or {}, workspace=nested_gid(d, "workspace"))


# --- asana.access_requests.list -------------------------------------------------------------------

class AccessRequestsListIn(BaseModel):
    target: str = Field(description="Gid of the project, portfolio or other object whose pending access requests should be listed")
    user: Optional[str] = Field(default=None, description="Keep only the requests of this user: 'me', an email or a user gid")


class AccessRequestItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the access request")
    message: Optional[str] = Field(default=None, description="Message the requester wrote when asking for access")
    approval_status: Optional[str] = Field(default=None, description="Status of the request: pending, approved or denied")
    requester: Optional[str] = Field(default=None, description="Gid of the user who asked for access")
    target: Optional[str] = Field(default=None, description="Gid of the object the access was requested on")


AccessRequestsOut = page_model(AccessRequestItem, "Access requests")


@function(
    id="asana.access_requests.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the pending access requests on an Asana object such as a project or a portfolio: each request reports its gid, the message the "
        "person wrote, its approval status, the gid of the requester and the gid of the target object. Use it when the user, as an admin or owner, "
        "asks who is waiting to be let into a project, or whether a given person already asked for access. It requires the gid of the target "
        "object and can be narrowed to one user (me, an email or a gid). Not paginated. Read-only. It does not approve or reject requests "
        "and it does not list the members of the object (use asana.memberships.list)."
    ),
    examples=[{"name": "default", "input": {"target": "1200000000000100"}, "output": {
        "items": [{"gid": "1200000000007900", "message": "Please add me", "approval_status": "pending", "requester": "1200000000000010",
                   "target": "1200000000000100"}], "has_more": False, "next_offset": None}}],
)
async def access_requests_list(ctx: Context, args: AccessRequestsListIn) -> AccessRequestsOut:
    body = await get_body(ctx, "/access_requests", params={"target": args.target, **({"user": args.user} if args.user else {}),
                                                            "opt_fields": _opt("message", "approval_status", "requester.name", "target")})
    return AccessRequestsOut(items=[AccessRequestItem(gid=str(i["gid"]), message=i.get("message"), approval_status=i.get("approval_status"),
                                                      requester=nested_gid(i, "requester"), target=nested_gid(i, "target"))
                                    for i in body.get("data") or []], has_more=False, next_offset=None)


# --- asana.jobs.get -------------------------------------------------------------------------------

class JobGetIn(BaseModel):
    job_gid: str = Field(description="Gid of the asynchronous job to fetch, as returned by an operation such as duplicating a project")


class JobDetail(BaseModel):
    gid: str = Field(description="Asana unique identifier of the job")
    resource_subtype: Optional[str] = Field(default=None, description="Kind of job, for example 'duplicate_task' or 'duplicate_project'")
    status: Optional[str] = Field(default=None, description="State of the job: not_started, in_progress, succeeded or failed")
    new_project: Optional[str] = Field(default=None, description="Gid of the project created by the job, once it finished")
    new_task: Optional[str] = Field(default=None, description="Gid of the task created by the job, once it finished")
    new_portfolio: Optional[str] = Field(default=None, description="Gid of the portfolio created by the job, once it finished")
    new_project_template: Optional[str] = Field(default=None, description="Gid of the project template created by the job, once it finished")
    download_url: Optional[str] = Field(default=None, description="URL to download the generated export file when the job is an export")


@function(
    id="asana.jobs.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["jobs:read"],
    description=(
        "Returns the status of an asynchronous Asana job, the background operation Asana starts for heavy actions such as duplicating a task or a "
        "project or generating an export: its gid, the kind of job, the state (not started, in progress, succeeded or failed) and, once it "
        "finished, the gid of the new project, task, portfolio or template it produced, or the download URL of an export. Use it to follow up a "
        "duplication started with asana.tasks.duplicate until the copy is ready. It requires only the job gid. Read-only. It does not cancel or "
        "retry jobs."
    ),
    examples=[{"name": "default", "input": {"job_gid": "1200000000008000"}, "output": {
        "gid": "1200000000008000", "resource_subtype": "duplicate_task", "status": "succeeded", "new_project": None,
        "new_task": "1200000000000900", "new_portfolio": None, "new_project_template": None, "download_url": None}}],
)
async def jobs_get(ctx: Context, args: JobGetIn) -> JobDetail:
    body = await get_body(ctx, f"/jobs/{args.job_gid}", params={"opt_fields": _opt(
        "resource_subtype", "status", "new_project.name", "new_task.name", "new_portfolio.name", "new_project_template.name",
        "new_graph_export.download_url", "new_resource_export.download_url")})
    d = body.get("data") or {}
    export = d.get("new_resource_export") or d.get("new_graph_export") or {}
    return JobDetail(gid=str(d["gid"]), resource_subtype=d.get("resource_subtype"), status=d.get("status"), new_project=nested_gid(d, "new_project"),
                     new_task=nested_gid(d, "new_task"), new_portfolio=nested_gid(d, "new_portfolio"),
                     new_project_template=nested_gid(d, "new_project_template"), download_url=export.get("download_url"))


# --- asana.agents ---------------------------------------------------------------------------------

class AgentItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the AI agent")
    name: Optional[str] = Field(default=None, description="Name of the AI agent")
    description: Optional[str] = Field(default=None, description="Short description of what the AI agent does")
    resource_subtype: Optional[str] = Field(default=None, description="Kind of agent, for example 'asana_teammate'")


AgentsOut = page_model(AgentItem, "AI agents")


class AgentsListIn(PageIn):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose AI agents should be listed")


@function(
    id="asana.agents.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the AI agents (AI teammates) that exist in an Asana workspace or organization: each one reports its gid, name, description and kind. "
        "Use it when the user asks which AI teammates are available in Asana, or needs an agent gid to read its details. It requires the workspace "
        "gid and results are paginated with a limit of 1 to 100 and an offset token. Read-only. It does not run, create, edit or delete agents "
        "and it does not return the instructions of each agent (use asana.agents.get for the behavior guidance of one)."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000008100", "name": "Triage helper", "description": "Sorts new requests", "resource_subtype": "asana_teammate"}],
        "has_more": False, "next_offset": None}}],
)
async def agents_list(ctx: Context, args: AgentsListIn) -> AgentsOut:
    body = await get_body(ctx, f"/workspaces/{args.workspace_gid}/agents", params=page_params(args.limit, args.offset, _opt("name", "description", "resource_subtype")))
    return build_page(AgentsOut, body, lambda i: AgentItem(gid=str(i["gid"]), name=i.get("name"), description=i.get("description"),
                                                           resource_subtype=i.get("resource_subtype")))


class AgentGetIn(BaseModel):
    agent_gid: str = Field(description="Gid of the AI agent to fetch")


class AgentDetail(AgentItem):
    behavior_guidance: Optional[str] = Field(default=None, description="Instructions that define how the AI agent behaves")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace or organization the agent belongs to")


@function(
    id="asana.agents.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns the details of one Asana AI agent (AI teammate): its gid, name, description, kind, the behavior guidance that defines how it "
        "acts and the workspace it belongs to. Use it when the user asks what a given AI teammate does or how it was configured. It requires only "
        "the agent gid, which can be found with asana.agents.list. Read-only. It does not run the agent, does not change its instructions and does "
        "not return its activity or credit usage (see asana.ai_studio_usage.get_runs for usage)."
    ),
    examples=[{"name": "default", "input": {"agent_gid": "1200000000008100"}, "output": {
        "gid": "1200000000008100", "name": "Triage helper", "description": "Sorts new requests", "resource_subtype": "asana_teammate",
        "behavior_guidance": "Label every new request by urgency.", "workspace": "1200000000000002"}}],
)
async def agents_get(ctx: Context, args: AgentGetIn) -> AgentDetail:
    body = await get_body(ctx, f"/agents/{args.agent_gid}", params={"opt_fields": _opt("name", "description", "resource_subtype", "behavior_guidance", "workspace.name")})
    d = body.get("data") or {}
    return AgentDetail(gid=str(d["gid"]), name=d.get("name"), description=d.get("description"), resource_subtype=d.get("resource_subtype"),
                       behavior_guidance=d.get("behavior_guidance"), workspace=nested_gid(d, "workspace"))


# --- asana.ai_studio_usage ------------------------------------------------------------------------

class AiStudioRunsIn(PageIn):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose AI Studio runs should be listed")
    start_at: Optional[str] = Field(default=None, description="Inclusive lower bound as an ISO 8601 date-time; runs are filtered by when their usage was recorded")
    end_at: Optional[str] = Field(default=None, description="Exclusive upper bound as an ISO 8601 date-time; defaults to the time of the request")
    division_gid: Optional[str] = Field(default=None, description="Gid of a single division to scope the results to; omitted means the first licensed division")


class AiStudioRunItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the AI Studio run")
    rule: Optional[str] = Field(default=None, description="Gid of the AI Studio rule that ran")
    rule_name: Optional[str] = Field(default=None, description="Name of the AI Studio rule that ran")
    rule_owner: Optional[str] = Field(default=None, description="Gid of the user who owns the rule")
    triggered_by: Optional[str] = Field(default=None, description="Gid of the user the run is attributed to")
    division: Optional[str] = Field(default=None, description="Gid of the division the run is billed to")
    run_started_at: Optional[str] = Field(default=None, description="UTC date and time when the run started")
    run_completed_at: Optional[str] = Field(default=None, description="UTC date and time when the run finished")
    status: Optional[str] = Field(default=None, description="Result of the run: success, failed or cancelled")
    model: Optional[str] = Field(default=None, description="Name of the AI model used by the run")
    credits_used: Optional[float] = Field(default=None, description="Credits consumed by the run")
    credit_source: Optional[str] = Field(default=None, description="Whether the credits were 'paid' or 'free'")


AiStudioRunsOut = page_model(AiStudioRunItem, "AI Studio runs")


@function(
    id="asana.ai_studio_usage.get_runs", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns the AI Studio usage history of an Asana organization, one row per rule execution, oldest first: each row reports the run gid, the "
        "rule that ran, its owner, who triggered it, the division, start and end times, the result, the AI model used and the credits consumed "
        "(paid or free). Use it when the user asks how many AI credits were spent, by which rules or by whom in a period. It requires the "
        "workspace gid; start_at and end_at bound the period by when usage was recorded, division_gid scopes it, and results are paginated. "
        "Read-only. Credit data exists from January 8th, 2025 onwards and the endpoint needs an organization licensed for AI Studio."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "start_at": "2026-10-01T00:00:00Z"}, "output": {
        "items": [{"gid": "1200000000008200", "rule": "1200000000008210", "rule_name": "Triage new tasks", "rule_owner": "1200000000000001",
                   "triggered_by": "1200000000000001", "division": None, "run_started_at": "2026-10-02T10:00:00Z",
                   "run_completed_at": "2026-10-02T10:00:05Z", "status": "success", "model": "claude", "credits_used": 1.5,
                   "credit_source": "paid"}], "has_more": False, "next_offset": None}}],
)
async def ai_studio_usage_get_runs(ctx: Context, args: AiStudioRunsIn) -> AiStudioRunsOut:
    params = {"limit": args.limit, **({"offset": args.offset} if args.offset else {}), **({"start_at": args.start_at} if args.start_at else {}),
              **({"end_at": args.end_at} if args.end_at else {}), **({"division_gid": args.division_gid} if args.division_gid else {})}
    body = await get_body(ctx, f"/workspaces/{args.workspace_gid}/ai_studio/runs", params=params)
    return build_page(AiStudioRunsOut, body, lambda i: AiStudioRunItem(
        gid=str(i["gid"]), rule=nested_gid(i, "rule"), rule_name=(i.get("rule") or {}).get("name"), rule_owner=nested_gid(i, "rule_owner"),
        triggered_by=nested_gid(i, "triggered_by"), division=nested_gid(i, "division"), run_started_at=i.get("run_started_at"),
        run_completed_at=i.get("run_completed_at"), status=i.get("status"), model=i.get("model"), credits_used=i.get("credits_used"),
        credit_source=i.get("credit_source")))


class AiStudioSeatsIn(PageIn):
    workspace_gid: str = Field(description="Gid of the workspace or organization whose AI Studio seats should be listed")
    state: Optional[Literal["active", "revoked"]] = Field(default=None, description="Keep only seats in this state: active or revoked")
    division_gid: Optional[str] = Field(default=None, description="Gid of a single division to scope the results to; omitted means the first licensed division")


class AiStudioSeatItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the AI Studio seat")
    user: Optional[str] = Field(default=None, description="Gid of the user who holds the seat")
    user_email: Optional[str] = Field(default=None, description="Email address of the user who holds the seat")
    license: Optional[str] = Field(default=None, description="License tier of the seat: ai_studio_plus, ai_studio_pro or ai_studio_max")
    state: Optional[str] = Field(default=None, description="State of the seat: active, revoked or expired")
    assigned_at: Optional[str] = Field(default=None, description="UTC date and time when the seat was assigned")
    revoked_at: Optional[str] = Field(default=None, description="UTC date and time when the seat was revoked, if it was")
    assigned_by: Optional[str] = Field(default=None, description="Gid of the user who assigned the seat")


AiStudioSeatsOut = page_model(AiStudioSeatItem, "AI Studio seats")


@function(
    id="asana.ai_studio_usage.get_seats", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns a snapshot of the AI Studio seats of an Asana organization, that is who has access to AI Studio: each seat reports its gid, the user "
        "and email, the license tier (plus, pro or max), the state (active, revoked or expired), when it was assigned or revoked and who assigned "
        "it. Use it when the user asks how many AI Studio seats are used, who holds one or which are free to reassign. It requires the workspace "
        "gid and can filter by state and division; results are paginated. Read-only. The endpoint is restricted to Asana service accounts in an "
        "organization licensed for AI Studio, so other accounts get a permission error. It does not assign or revoke seats."
    ),
    examples=[{"name": "default", "input": {"workspace_gid": "1200000000000002", "state": "active"}, "output": {
        "items": [{"gid": "1200000000008300", "user": "1200000000000001", "user_email": "ana@empresa.test", "license": "ai_studio_pro",
                   "state": "active", "assigned_at": "2026-09-01T10:00:00Z", "revoked_at": None, "assigned_by": "1200000000000003"}],
        "has_more": False, "next_offset": None}}],
)
async def ai_studio_usage_get_seats(ctx: Context, args: AiStudioSeatsIn) -> AiStudioSeatsOut:
    params = {"limit": args.limit, **({"offset": args.offset} if args.offset else {}), **({"state": args.state} if args.state else {}),
              **({"division_gid": args.division_gid} if args.division_gid else {})}
    body = await get_body(ctx, f"/workspaces/{args.workspace_gid}/ai_studio/seats", params=params)
    return build_page(AiStudioSeatsOut, body, lambda i: AiStudioSeatItem(
        gid=str(i["gid"]), user=nested_gid(i, "user"), user_email=(i.get("user") or {}).get("email"), license=i.get("license"), state=i.get("state"),
        assigned_at=i.get("assigned_at"), revoked_at=i.get("revoked_at"), assigned_by=nested_gid(i, "assigned_by")))


# ==================================================================================================
# Tarea 8
# ==================================================================================================

# --- asana.time_periods ---------------------------------------------------------------------------

TIME_PERIOD_FIELDS = _opt("start_on", "end_on", "period", "display_name", "parent.display_name")


class TimePeriodItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the time period")
    display_name: Optional[str] = Field(default=None, description="Human readable name of the period, for example 'Q3 FY26'")
    period: Optional[str] = Field(default=None, description="Kind of period: FY, H1, H2, Q1, Q2, Q3 or Q4")
    start_on: Optional[str] = Field(default=None, description="First day of the period in YYYY-MM-DD")
    end_on: Optional[str] = Field(default=None, description="Last day of the period in YYYY-MM-DD")
    parent: Optional[str] = Field(default=None, description="Gid of the parent period, for example the fiscal year of a quarter")


TimePeriodsOut = page_model(TimePeriodItem, "Time periods")


def _time_period(raw: dict) -> TimePeriodItem:
    return TimePeriodItem(gid=str(raw["gid"]), display_name=raw.get("display_name"), period=raw.get("period"), start_on=raw.get("start_on"),
                          end_on=raw.get("end_on"), parent=nested_gid(raw, "parent"))


class TimePeriodGetIn(BaseModel):
    time_period_gid: str = Field(description="Gid of the time period to fetch")


@function(
    id="asana.time_periods.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Returns one Asana time period, the fiscal or calendar span used by goals: its gid, display name (for example Q3 FY26), the kind of period "
        "(fiscal year, half or quarter), the first and last day and the parent period it belongs to. Use it when the user asks which dates a goal "
        "period covers or references a time period gid found on a goal. It requires only the time period gid. Read-only. It does not create or "
        "change periods and it does not list them; to list the periods of a workspace use asana.time_periods.list."
    ),
    examples=[{"name": "default", "input": {"time_period_gid": "1200000000008400"}, "output": {
        "gid": "1200000000008400", "display_name": "Q3 FY26", "period": "Q3", "start_on": "2026-07-01", "end_on": "2026-09-30",
        "parent": "1200000000008410"}}],
)
async def time_periods_get(ctx: Context, args: TimePeriodGetIn) -> TimePeriodItem:
    body = await get_body(ctx, f"/time_periods/{args.time_period_gid}", params={"opt_fields": TIME_PERIOD_FIELDS})
    return _time_period(body.get("data") or {})


class TimePeriodsListIn(PageIn):
    workspace: str = Field(description="Gid of the workspace or organization whose time periods should be listed")
    start_on: Optional[str] = Field(default=None, description="ISO 8601 date (YYYY-MM-DD); keeps periods that start on or after this date")
    end_on: Optional[str] = Field(default=None, description="ISO 8601 date (YYYY-MM-DD); keeps periods that end on or before this date")


@function(
    id="asana.time_periods.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=(),
    description=(
        "Lists the time periods of an Asana workspace or organization, the fiscal years, halves and quarters that goals are measured against: each "
        "period reports its gid, display name, kind, first and last day and parent period. Use it when the user asks which periods exist, which "
        "one is current, or needs a time period gid to filter goals. It requires the workspace gid; start_on and end_on narrow the date range and "
        "results are paginated with a limit of 1 to 100. Read-only. It does not create periods and it does not return the goals of a period "
        "(use asana.goals.list)."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002", "start_on": "2026-01-01"}, "output": {
        "items": [{"gid": "1200000000008400", "display_name": "Q3 FY26", "period": "Q3", "start_on": "2026-07-01", "end_on": "2026-09-30",
                   "parent": "1200000000008410"}], "has_more": False, "next_offset": None}}],
)
async def time_periods_list(ctx: Context, args: TimePeriodsListIn) -> TimePeriodsOut:
    body = await get_body(ctx, "/time_periods", params=page_params(args.limit, args.offset, TIME_PERIOD_FIELDS, workspace=args.workspace,
                                                                   start_on=args.start_on, end_on=args.end_on))
    return build_page(TimePeriodsOut, body, _time_period)


# --- asana.timesheet_approval_statuses ------------------------------------------------------------

TIMESHEET_FIELDS = _opt("user.name", "workspace.name", "start_date", "end_date", "approval_status", "created_at")


class TimesheetApprovalStatusItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the timesheet approval status")
    user: Optional[str] = Field(default=None, description="Gid of the user whose timesheet this is")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace the timesheet belongs to")
    start_date: Optional[str] = Field(default=None, description="First day of the timesheet week in YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="Last day of the timesheet week in YYYY-MM-DD")
    approval_status: Optional[str] = Field(default=None, description="Approval state of the timesheet: DRAFT, SUBMITTED, APPROVED or REJECTED")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the status record was created")


TimesheetStatusesOut = page_model(TimesheetApprovalStatusItem, "Timesheet approval statuses")


def _timesheet(raw: dict) -> TimesheetApprovalStatusItem:
    return TimesheetApprovalStatusItem(gid=str(raw["gid"]), user=nested_gid(raw, "user"), workspace=nested_gid(raw, "workspace"),
                                       start_date=raw.get("start_date"), end_date=raw.get("end_date"),
                                       approval_status=raw.get("approval_status"), created_at=raw.get("created_at"))


class TimesheetGetIn(BaseModel):
    timesheet_approval_status_gid: str = Field(description="Gid of the timesheet approval status to fetch")


@function(
    id="asana.timesheet_approval_statuses.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["timesheet_approval_statuses:read"],
    description=(
        "Returns one timesheet approval status of Asana: whether the timesheet of a person for a given week is a draft, submitted, approved or "
        "rejected. It reports the gid, the user, the workspace, the first and last day of the week, the approval state and the creation date. Use it "
        "when the user asks if a timesheet was approved or references a status gid from a list. It requires only that gid. Read-only. It does "
        "not approve or reject timesheets and it does not list them; to find the statuses of a workspace or a person use "
        "asana.timesheet_approval_statuses.list. Time tracking is a paid Asana feature."
    ),
    examples=[{"name": "default", "input": {"timesheet_approval_status_gid": "1200000000008500"}, "output": {
        "gid": "1200000000008500", "user": "1200000000000001", "workspace": "1200000000000002", "start_date": "2026-10-05", "end_date": "2026-10-11",
        "approval_status": "SUBMITTED", "created_at": "2026-10-11T18:00:00.000Z"}}],
)
async def timesheet_approval_statuses_get(ctx: Context, args: TimesheetGetIn) -> TimesheetApprovalStatusItem:
    body = await get_body(ctx, f"/timesheet_approval_statuses/{args.timesheet_approval_status_gid}", params={"opt_fields": TIMESHEET_FIELDS})
    return _timesheet(body.get("data") or {})


class TimesheetListIn(PageIn):
    workspace: str = Field(description="Gid of the workspace or organization whose timesheet approval statuses should be listed")
    user: Optional[str] = Field(default=None, description="Gid of a user; keeps only the timesheets of that person")
    from_date: Optional[str] = Field(default=None, description="Start of the date range to filter by, in YYYY-MM-DD")
    to_date: Optional[str] = Field(default=None, description="End of the date range to filter by, in YYYY-MM-DD")
    approval_statuses: Optional[str] = Field(default=None, description="Comma separated approval states to keep: draft, submitted, approved and/or rejected")


@function(
    id="asana.timesheet_approval_statuses.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["timesheet_approval_statuses:read"],
    description=(
        "Lists the timesheet approval statuses of an Asana workspace: for each person and week it reports the gid, the user, the week dates and "
        "whether the timesheet is a draft, submitted, approved or rejected. Use it when a manager asks which timesheets are still pending approval, "
        "who has not submitted their week or what was rejected. It requires the workspace gid and can be narrowed by user, date range "
        "(from_date and to_date) and a comma separated list of approval states; results are paginated with a limit of 1 to 100. Read-only. It "
        "does not approve timesheets and it does not return the time entries (use asana.time_tracking_entries.list)."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002", "approval_statuses": "submitted"}, "output": {
        "items": [{"gid": "1200000000008500", "user": "1200000000000001", "workspace": "1200000000000002", "start_date": "2026-10-05",
                   "end_date": "2026-10-11", "approval_status": "SUBMITTED", "created_at": "2026-10-11T18:00:00.000Z"}],
        "has_more": False, "next_offset": None}}],
)
async def timesheet_approval_statuses_list(ctx: Context, args: TimesheetListIn) -> TimesheetStatusesOut:
    body = await get_body(ctx, "/timesheet_approval_statuses", params=page_params(
        args.limit, args.offset, TIMESHEET_FIELDS, workspace=args.workspace, user=args.user, from_date=args.from_date, to_date=args.to_date,
        approval_statuses=args.approval_statuses))
    return build_page(TimesheetStatusesOut, body, _timesheet)


# --- asana.custom_types ---------------------------------------------------------------------------

CUSTOM_TYPE_FIELDS = _opt("name", "asana_created_type_identifier", "status_options.name", "status_options.completion_state",
                          "status_options.enabled", "status_options.color")


class CustomTypeStatus(BaseModel):
    gid: str = Field(description="Asana unique identifier of the status option")
    name: Optional[str] = Field(default=None, description="Name of the status option")
    completion_state: Optional[str] = Field(default=None, description="Whether tasks in this status count as 'incomplete' or 'complete'")
    enabled: Optional[bool] = Field(default=None, description="True when the status option can currently be chosen")
    color: Optional[str] = Field(default=None, description="Color of the status option, when one is set")


class CustomTypeItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the custom type")
    name: Optional[str] = Field(default=None, description="Name of the custom type, for example 'Bug' or 'Release'")
    asana_created_type_identifier: Optional[str] = Field(default=None, description="Identifier of the built-in type Asana created it from, when it has one")
    status_options: list[CustomTypeStatus] = Field(default_factory=list, description="Status options tasks of this custom type can have")


CustomTypesOut = page_model(CustomTypeItem, "Custom types")


def _custom_type(raw: dict) -> CustomTypeItem:
    return CustomTypeItem(gid=str(raw["gid"]), name=raw.get("name"), asana_created_type_identifier=raw.get("asana_created_type_identifier"),
                          status_options=[CustomTypeStatus(gid=str(s["gid"]), name=s.get("name"), completion_state=s.get("completion_state"),
                                                           enabled=s.get("enabled"), color=s.get("color")) for s in raw.get("status_options") or []])


class CustomTypesListIn(PageIn):
    project: Optional[str] = Field(default=None, description="Gid of a project; keeps only the custom types available in that project")
    workspace: Optional[str] = Field(default=None, description="Gid of a workspace or organization; keeps only the custom types defined there")


@function(
    id="asana.custom_types.list", version=1, verb=Verb.read, upstream_api="1.0", scopes=["custom_types:read"],
    description=(
        "Lists the custom types of Asana, the user-defined kinds of objects such as Bug, Release or Ticket that tasks and projects can have: each "
        "type reports its gid, its name, the built-in type it derives from and its status options with their completion state. Use it when the "
        "user asks which task types exist in a workspace or project, or needs a custom type gid to filter tasks or projects. It can be filtered by "
        "project or by workspace and results are paginated with a limit of 1 to 100. Read-only. It does not create or edit types; for the "
        "detail of a single type use asana.custom_types.get."
    ),
    examples=[{"name": "default", "input": {"workspace": "1200000000000002"}, "output": {
        "items": [{"gid": "1200000000008600", "name": "Bug", "asana_created_type_identifier": None,
                   "status_options": [{"gid": "1200000000008610", "name": "Open", "completion_state": "incomplete", "enabled": True, "color": "red"}]}],
        "has_more": False, "next_offset": None}}],
)
async def custom_types_list(ctx: Context, args: CustomTypesListIn) -> CustomTypesOut:
    body = await get_body(ctx, "/custom_types", params=page_params(args.limit, args.offset, CUSTOM_TYPE_FIELDS, project=args.project, workspace=args.workspace))
    return build_page(CustomTypesOut, body, _custom_type)


class CustomTypeGetIn(BaseModel):
    custom_type_gid: str = Field(description="Gid of the custom type to fetch")


@function(
    id="asana.custom_types.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["custom_types:read"],
    description=(
        "Returns one Asana custom type, a user-defined kind of task or project such as Bug or Release: its gid, name, the built-in type it derives "
        "from and the list of status options, each with name, completion state, enabled flag and color. Use it when the user asks what statuses a "
        "type allows or references a custom type gid found on a task. It requires only the custom type gid. Read-only. It does not create or "
        "modify types and it does not list them; to find the types of a workspace or project use asana.custom_types.list."
    ),
    examples=[{"name": "default", "input": {"custom_type_gid": "1200000000008600"}, "output": {
        "gid": "1200000000008600", "name": "Bug", "asana_created_type_identifier": None,
        "status_options": [{"gid": "1200000000008610", "name": "Open", "completion_state": "incomplete", "enabled": True, "color": "red"}]}}],
)
async def custom_types_get(ctx: Context, args: CustomTypeGetIn) -> CustomTypeItem:
    body = await get_body(ctx, f"/custom_types/{args.custom_type_gid}", params={"opt_fields": CUSTOM_TYPE_FIELDS})
    return _custom_type(body.get("data") or {})


# --- asana.user_task_lists ------------------------------------------------------------------------

USER_TASK_LIST_FIELDS = _opt("name", "owner.name", "workspace.name")


class UserTaskListItem(BaseModel):
    gid: str = Field(description="Asana unique identifier of the user task list")
    name: Optional[str] = Field(default=None, description="Name of the user task list, usually 'My tasks'")
    owner: Optional[str] = Field(default=None, description="Gid of the user who owns the task list")
    workspace: Optional[str] = Field(default=None, description="Gid of the workspace the task list belongs to")


def _user_task_list(raw: dict) -> UserTaskListItem:
    return UserTaskListItem(gid=str(raw["gid"]), name=raw.get("name"), owner=nested_gid(raw, "owner"), workspace=nested_gid(raw, "workspace"))


class UserTaskListGetIn(BaseModel):
    user_task_list_gid: str = Field(description="Gid of the user task list to fetch")


@function(
    id="asana.user_task_lists.get", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Returns one Asana user task list, the personal 'My tasks' list of a person in a workspace: its gid, name, the owner and the workspace. Use "
        "it when the user references a user task list gid and wants to know whose it is and where it lives. It requires only the user task list "
        "gid. Read-only. It does not return the tasks of the list (use asana.tasks.list_user_task_list with the same gid) and it cannot find a "
        "list from a person; for that use asana.user_task_lists.get_user."
    ),
    examples=[{"name": "default", "input": {"user_task_list_gid": "1200000000000300"}, "output": {
        "gid": "1200000000000300", "name": "My tasks in Mi equipo", "owner": "1200000000000001", "workspace": "1200000000000002"}}],
)
async def user_task_lists_get(ctx: Context, args: UserTaskListGetIn) -> UserTaskListItem:
    body = await get_body(ctx, f"/user_task_lists/{args.user_task_list_gid}", params={"opt_fields": USER_TASK_LIST_FIELDS})
    return _user_task_list(body.get("data") or {})


class UserTaskListForUserIn(BaseModel):
    user_gid: str = Field(description="Asana user to look up: 'me', an email or the user gid")
    workspace: str = Field(description="Gid of the workspace or organization in which to find the user's task list")


@function(
    id="asana.user_task_lists.get_user", version=1, verb=Verb.read, upstream_api="1.0", scopes=["tasks:read"],
    description=(
        "Returns the personal 'My tasks' list (user task list) of a given Asana user in a given workspace: its gid, name, owner and workspace. Use it "
        "when the user asks for their own task list, or someone else's, and a gid is needed to then list the tasks in it with "
        "asana.tasks.list_user_task_list. It requires the user (me, an email or a gid) and the workspace gid, because a person has one task list per "
        "workspace. Read-only. It does not return the tasks themselves and it does not create or change the list."
    ),
    examples=[{"name": "default", "input": {"user_gid": "me", "workspace": "1200000000000002"}, "output": {
        "gid": "1200000000000300", "name": "My tasks in Mi equipo", "owner": "1200000000000001", "workspace": "1200000000000002"}}],
)
async def user_task_lists_get_user(ctx: Context, args: UserTaskListForUserIn) -> UserTaskListItem:
    body = await get_body(ctx, f"/users/{args.user_gid}/user_task_list", params={"workspace": args.workspace, "opt_fields": USER_TASK_LIST_FIELDS})
    return _user_task_list(body.get("data") or {})
