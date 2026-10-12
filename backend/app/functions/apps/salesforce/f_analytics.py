"""Lecturas de informes y paneles (Reports and Dashboards) de Salesforce.

Verificado con la API real (2026-10-09), v62.0:
- `GET /analytics/reports` y `GET /analytics/dashboards` devuelven solo los VISTOS RECIENTEMENTE (en la org de prueba, `[]`), no "todos" como decia el
  catalogo. Para listar todos se usa SOQL sobre los objetos `Report` y `Dashboard` (Id, Name/Title, DeveloperName, FolderName, Description, ...).
- `GET /analytics/reports/{id}?includeDetails=false` ejecuta el informe al momento y devuelve {reportMetadata, factMap, groupingsDown, groupingsAcross,
  allData, hasDetailRows}; con `includeDetails=true` agrega las filas de detalle. Responde 403 FORBIDDEN (`specificErrorCode` 103) si el usuario
  no puede ejecutar ese informe (pasa con los informes de Enablement de la org de prueba; los de "Informes publicos" si funcionan).
- `POST /analytics/reports/{id}/instances` (cuerpo `{}` o `{"reportMetadata": {...}}`) crea una EJECUCION ASINCRONA y responde {id, status, requestDate,
  ownerId, url, hasDetailRows, queryable, completionDate}. No cambia datos de la org; el catalogo la lista como lectura.
- `GET /analytics/dashboards/{id}/describe` da el detalle (name, description, folderName, dashboardType, runningUser, components[{id, header, title,
  type, reportId, footer, lastModifiedDate}], filters, layout). `GET /analytics/dashboards/{id}` da los DATOS: {componentData[{componentId,
  reportResult, status}], dashboardMetadata}.
- NO existe `.../dashboards/{id}/dashboard_components/{componentId}` (el catalogo lo inventa): los datos de un componente salen de `componentData`.
Todas piden el permiso `api`. Las descripciones y los Field(description=...) estan en INGLES y completos a proposito.
"""
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.functions.apps.salesforce._common import ID_PATTERN, UPSTREAM_API, clean_record, get_json, post_json, soql_like
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

MAX_OFFSET = 2000  # tope de OFFSET en SOQL

LIMIT_KW = dict(default=50, ge=1, le=200, description="How many items to return, from 1 to 200 (default 50)")
OFFSET_KW = dict(default=0, ge=0, le=MAX_OFFSET, description="How many items to skip, from 0 to 2000; use the next_offset value of a previous result to continue")


async def _list(ctx: Context, sobject: str, fields: str, where: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], bool]:
    soql = f"SELECT {fields} FROM {sobject}" + (f" WHERE {where}" if where else "") + f" ORDER BY LastModifiedDate DESC LIMIT {limit + 1} OFFSET {offset}"
    rows = (await get_json(ctx, "/query", params={"q": soql})).get("records", [])
    return [clean_record(r) for r in rows[:limit]], len(rows) > limit


def _next(offset: int, limit: int, has_more: bool) -> Optional[int]:
    nxt = offset + limit
    return nxt if has_more and nxt <= MAX_OFFSET else None


# --- salesforce.analytics.reports_list -----------------------------------------------------------

class ReportItem(BaseModel):
    id: str = Field(description="Salesforce id of the report, usable in report_get and report_run")
    name: Optional[str] = Field(default=None, description="Name of the report as shown in Salesforce, in the language of the org")
    developer_name: Optional[str] = Field(default=None, description="API name of the report, stable across languages")
    format: Optional[str] = Field(default=None, description="Report format: 'Tabular', 'Summary', 'Matrix' or 'MultiBlock'")
    folder_name: Optional[str] = Field(default=None, description="Name of the folder that holds the report")
    description: Optional[str] = Field(default=None, description="Description of the report, if one was written")
    last_run_date: Optional[str] = Field(default=None, description="Date and time when the report was last run, in ISO 8601 format")
    last_modified_date: Optional[str] = Field(default=None, description="Date and time of the last change to the report definition, in ISO 8601 format")


class ReportsListIn(BaseModel):
    name_contains: Optional[str] = Field(default=None, min_length=1, max_length=100, description="Optional text contained in the report name, ignoring upper and lower case, for example 'pipeline'")
    limit: int = Field(**LIMIT_KW)
    offset: int = Field(**OFFSET_KW)


class ReportsListOut(BaseModel):
    reports: list[ReportItem] = Field(description="The reports returned in this page, most recently modified first")
    has_more: bool = Field(description="True when there are more reports than were returned and a next page can be requested")
    next_offset: Optional[int] = Field(default=None, description="Offset to pass as input to get the next page of reports; empty when there is no next page or Salesforce cannot skip that far")


@function(
    id="salesforce.analytics.reports_list", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the reports stored in the connected Salesforce org, most recently modified first, each with its id, name, API name, format (tabular, summary, "
        "matrix), folder, description and the dates it was last run and modified. It can filter by text in the name. Use it when the user asks which "
        "reports exist, wants to find a report, or needs a report id to run it. It returns up to 200 reports per call and continues with next_offset. "
        "Read-only: it does not run the report, which is done with salesforce.analytics.report_get (data now) or salesforce.analytics.report_run (new "
        "background run)."
    ),
    examples=[{"name": "default", "input": {"name_contains": "pipeline", "limit": 1}, "output": {"reports": [
        {"id": "00Ofj000005WXcTEAW", "name": "Pipeline by Stage", "developer_name": "Pipeline_by_Stage", "format": "Summary", "folder_name": "Public Reports",
         "description": None, "last_run_date": "2026-10-01T10:00:00.000+0000", "last_modified_date": "2026-09-01T10:00:00.000+0000"}], "has_more": False}}],
)
async def analytics_reports_list(ctx: Context, args: ReportsListIn) -> ReportsListOut:
    where = f"Name LIKE {soql_like(args.name_contains)}" if args.name_contains else ""
    rows, has_more = await _list(ctx, "Report", "Id,Name,DeveloperName,Format,FolderName,Description,LastRunDate,LastModifiedDate", where, args.limit, args.offset)
    reports = [ReportItem(id=r["Id"], name=r.get("Name"), developer_name=r.get("DeveloperName"), format=r.get("Format"), folder_name=r.get("FolderName"),
                          description=r.get("Description"), last_run_date=r.get("LastRunDate"), last_modified_date=r.get("LastModifiedDate")) for r in rows]
    return ReportsListOut(reports=reports, has_more=has_more, next_offset=_next(args.offset, args.limit, has_more))


# --- salesforce.analytics.report_get -------------------------------------------------------------

class ReportGetIn(BaseModel):
    report_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the report, 15 or 18 letters and digits, usually starting with 00O")
    include_details: bool = Field(default=False, description="When true, the detail rows of the report are included (can be large); default false returns only totals and groupings")


class ReportDataOut(BaseModel):
    report_metadata: dict[str, Any] = Field(description="Definition of the report: name, format, columns, filters, groupings and aggregates, as Salesforce describes them")
    fact_map: dict[str, Any] = Field(description="The report values: for each grouping key (such as 'T!T' for the grand total) its aggregates and, if requested, its detail rows")
    groupings_down: Any = Field(description="Row groupings of the report with their keys and labels, which the fact_map keys refer to")
    groupings_across: Any = Field(description="Column groupings of a matrix report with their keys and labels; empty for other formats")
    all_data: Optional[bool] = Field(default=None, description="True when the result holds all the rows, false when Salesforce truncated it")
    has_detail_rows: Optional[bool] = Field(default=None, description="True when the result includes detail rows and not only totals")


@function(
    id="salesforce.analytics.report_get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Runs one Salesforce report right now and returns its definition (name, format, columns, filters, groupings) together with its results: the "
        "totals and subtotals by grouping and, when asked, the detail rows. Use it when the user wants the numbers of a report, for example 'show me the "
        "pipeline report'. Give the report id; results come back in the same call, up to the first 2000 detail rows. Read-only: it does not change the "
        "report. It fails with missing_scope when the connected user is not allowed to run that report, and with not_found when the id does not exist. "
        "To find report ids use salesforce.analytics.reports_list."
    ),
    examples=[{"name": "default", "input": {"report_id": "00Ofj000005WXcTEAW"}, "output": {
        "report_metadata": {"id": "00Ofj000005WXcTEAW", "name": "Pipeline by Stage", "reportFormat": "SUMMARY"},
        "fact_map": {"T!T": {"aggregates": [{"label": "12", "value": 12}]}}, "groupings_down": {"groupings": []}, "groupings_across": {"groupings": []},
        "all_data": True, "has_detail_rows": False}}],
)
async def analytics_report_get(ctx: Context, args: ReportGetIn) -> ReportDataOut:
    body = await get_json(ctx, f"/analytics/reports/{args.report_id}", params={"includeDetails": "true" if args.include_details else "false"})
    return ReportDataOut(report_metadata=body.get("reportMetadata") or {}, fact_map=body.get("factMap") or {}, groupings_down=body.get("groupingsDown"),
                         groupings_across=body.get("groupingsAcross"), all_data=body.get("allData"), has_detail_rows=body.get("hasDetailRows"))


# --- salesforce.analytics.report_run -------------------------------------------------------------

class ReportRunIn(BaseModel):
    report_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the report to run, 15 or 18 letters and digits, usually starting with 00O")
    report_metadata: Optional[dict[str, Any]] = Field(default=None, description="Optional report definition overrides for this run only, for example {'reportFilters': [{'column': 'STAGE_NAME', 'operator': 'equals', 'value': 'Closed Won'}]}; the saved report is not changed")


class ReportRunOut(BaseModel):
    instance_id: str = Field(description="Salesforce id of the report run (instance), usually starting with 0LG")
    status: Optional[str] = Field(default=None, description="State of the run when it was requested, for example 'New' or 'Running'; it finishes in the background")
    request_date: Optional[str] = Field(default=None, description="Date and time when the run was requested, in ISO 8601 format")
    owner_id: Optional[str] = Field(default=None, description="Salesforce user id of the user who requested the run")
    instance_url: Optional[str] = Field(default=None, description="Path of the run in the Salesforce API, relative to the org URL")


@function(
    id="salesforce.analytics.report_run", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Starts a background run (instance) of one Salesforce report and returns the run id, its state and when it was requested. Optionally it applies "
        "filters or other definition changes to that run only, without modifying the saved report. Use it for large reports that take time or when the user "
        "wants the report run with different filters; the run is asynchronous and completes in Salesforce. It never changes records or the saved report, "
        "although each call creates a run that counts toward the org's report limits. It fails with missing_scope when the user cannot run the report. For "
        "immediate results use salesforce.analytics.report_get."
    ),
    examples=[{"name": "default", "input": {"report_id": "00Ofj000005WXcTEAW"}, "output": {
        "instance_id": "0LGfj0000016hEbGAI", "status": "New", "request_date": "2026-10-09T15:42:07Z", "owner_id": "005fj000009fDddAAE",
        "instance_url": "/services/data/v62.0/analytics/reports/00Ofj000005WXcTEAW/instances/0LGfj0000016hEbGAI"}}],
)
async def analytics_report_run(ctx: Context, args: ReportRunIn) -> ReportRunOut:
    body = await post_json(ctx, f"/analytics/reports/{args.report_id}/instances", {"reportMetadata": args.report_metadata} if args.report_metadata else {})
    if not body.get("id"):
        raise FunctionError(ErrorCode.upstream_changed, "Salesforce did not return the id of the report run.")
    return ReportRunOut(instance_id=body["id"], status=body.get("status"), request_date=body.get("requestDate"), owner_id=body.get("ownerId"), instance_url=body.get("url"))


# --- salesforce.analytics.dashboards_list --------------------------------------------------------

class DashboardItem(BaseModel):
    id: str = Field(description="Salesforce id of the dashboard, usable in dashboard_get and dashboard_component, usually starting with 01Z")
    title: Optional[str] = Field(default=None, description="Title of the dashboard as shown in Salesforce, in the language of the org")
    developer_name: Optional[str] = Field(default=None, description="API name of the dashboard, stable across languages")
    folder_name: Optional[str] = Field(default=None, description="Name of the folder that holds the dashboard")
    description: Optional[str] = Field(default=None, description="Description of the dashboard, if one was written")
    type: Optional[str] = Field(default=None, description="Who the dashboard runs as: 'LoggedInUser', 'SpecifiedUser' or 'MyTeamUser'")
    last_modified_date: Optional[str] = Field(default=None, description="Date and time of the last change to the dashboard, in ISO 8601 format")


class DashboardsListIn(BaseModel):
    name_contains: Optional[str] = Field(default=None, min_length=1, max_length=100, description="Optional text contained in the dashboard title, ignoring upper and lower case, for example 'sales'")
    limit: int = Field(**LIMIT_KW)
    offset: int = Field(**OFFSET_KW)


class DashboardsListOut(BaseModel):
    dashboards: list[DashboardItem] = Field(description="The dashboards returned in this page, most recently modified first")
    has_more: bool = Field(description="True when there are more dashboards than were returned and a next page can be requested")
    next_offset: Optional[int] = Field(default=None, description="Offset to pass as input to get the next page of dashboards; empty when there is no next page or Salesforce cannot skip that far")


@function(
    id="salesforce.analytics.dashboards_list", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the dashboards stored in the connected Salesforce org, most recently modified first, each with its id, title, API name, folder, description, "
        "the kind of running user and the date of its last change. It can filter by text in the title. Use it when the user asks which dashboards exist, "
        "wants to find one, or needs a dashboard id to see its detail. It returns up to 200 dashboards per call and continues with next_offset. Read-only: "
        "it does not refresh or change dashboards. For the components of one dashboard use salesforce.analytics.dashboard_get, and for the numbers of a "
        "component use salesforce.analytics.dashboard_component."
    ),
    examples=[{"name": "default", "input": {"limit": 1}, "output": {"dashboards": [
        {"id": "01Zfj0000022ug5EAA", "title": "Sales Overview", "developer_name": "Sales_Overview", "folder_name": "Public Dashboards", "description": None,
         "type": "LoggedInUser", "last_modified_date": "2026-09-01T10:00:00.000+0000"}], "has_more": False}}],
)
async def analytics_dashboards_list(ctx: Context, args: DashboardsListIn) -> DashboardsListOut:
    where = f"Title LIKE {soql_like(args.name_contains)}" if args.name_contains else ""
    rows, has_more = await _list(ctx, "Dashboard", "Id,Title,DeveloperName,FolderName,Description,Type,LastModifiedDate", where, args.limit, args.offset)
    items = [DashboardItem(id=r["Id"], title=r.get("Title"), developer_name=r.get("DeveloperName"), folder_name=r.get("FolderName"),
                           description=r.get("Description"), type=r.get("Type"), last_modified_date=r.get("LastModifiedDate")) for r in rows]
    return DashboardsListOut(dashboards=items, has_more=has_more, next_offset=_next(args.offset, args.limit, has_more))


# --- salesforce.analytics.dashboard_get ----------------------------------------------------------

class DashboardComponent(BaseModel):
    id: str = Field(description="Salesforce id of the dashboard component, usable in salesforce.analytics.dashboard_component, usually starting with 01a")
    header: Optional[str] = Field(default=None, description="Header text of the component")
    title: Optional[str] = Field(default=None, description="Title of the component")
    footer: Optional[str] = Field(default=None, description="Footer text of the component")
    type: Optional[str] = Field(default=None, description="Kind of component, for example 'Report', 'Table', 'Metric' or 'Gauge'")
    report_id: Optional[str] = Field(default=None, description="Salesforce id of the report that feeds the component, if any")
    last_modified_date: Optional[str] = Field(default=None, description="Date and time of the last change to the component, in ISO 8601 format")


class DashboardGetIn(BaseModel):
    dashboard_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the dashboard, 15 or 18 letters and digits, usually starting with 01Z")


class DashboardOut(BaseModel):
    id: str = Field(description="Salesforce id of the dashboard")
    name: Optional[str] = Field(default=None, description="Name of the dashboard as shown in Salesforce")
    description: Optional[str] = Field(default=None, description="Description of the dashboard, if one was written")
    developer_name: Optional[str] = Field(default=None, description="API name of the dashboard, stable across languages")
    folder_name: Optional[str] = Field(default=None, description="Name of the folder that holds the dashboard")
    dashboard_type: Optional[str] = Field(default=None, description="Who the dashboard runs as: 'LoggedInUser', 'SpecifiedUser' or 'MyTeamUser'")
    running_user: Optional[str] = Field(default=None, description="Name of the user whose data the dashboard shows")
    component_count: int = Field(description="Number of components of the dashboard")
    components: list[DashboardComponent] = Field(description="The components (charts, tables, metrics) of the dashboard with their ids and the report behind each one")


@function(
    id="salesforce.analytics.dashboard_get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the definition of one Salesforce dashboard given its id: name, description, folder, the kind of running user and every component (chart, "
        "table, metric) with its id, header, title, type and the report that feeds it. Use it when the user asks what a dashboard shows or which reports it "
        "is built from. It describes the dashboard but does not return the numbers. Read-only: it does not refresh or change the dashboard. It fails with "
        "not_found when the id does not exist. To find dashboards use salesforce.analytics.dashboards_list, and for the data of a component use "
        "salesforce.analytics.dashboard_component."
    ),
    examples=[{"name": "default", "input": {"dashboard_id": "01Zfj0000022ug5EAA"}, "output": {
        "id": "01Zfj0000022ug5EAA", "name": "Sales Overview", "description": None, "developer_name": "Sales_Overview", "folder_name": "Public Dashboards",
        "dashboard_type": "LoggedInUser", "running_user": "Ana Perez", "component_count": 1, "components": [
            {"id": "01afj000002tJs5AAE", "header": "Pipeline by Stage", "title": None, "footer": None, "type": "Report", "report_id": "00Ofj000005WXccEAG",
             "last_modified_date": "2026-09-01T10:00:00Z"}]}}],
)
async def analytics_dashboard_get(ctx: Context, args: DashboardGetIn) -> DashboardOut:
    body = await get_json(ctx, f"/analytics/dashboards/{args.dashboard_id}/describe")
    comps = [DashboardComponent(id=c["id"], header=c.get("header"), title=c.get("title"), footer=c.get("footer"), type=c.get("type"),
                                report_id=c.get("reportId"), last_modified_date=c.get("lastModifiedDate")) for c in body.get("components", []) if c.get("id")]
    return DashboardOut(id=body.get("id") or args.dashboard_id, name=body.get("name"), description=body.get("description"), developer_name=body.get("developerName"),
                        folder_name=body.get("folderName"), dashboard_type=body.get("dashboardType"), running_user=(body.get("runningUser") or {}).get("displayName"),
                        component_count=len(comps), components=comps)


# --- salesforce.analytics.dashboard_component ----------------------------------------------------

class DashboardComponentIn(BaseModel):
    dashboard_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the dashboard that holds the component, usually starting with 01Z")
    component_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the component inside the dashboard, usually starting with 01a; get it from salesforce.analytics.dashboard_get")


class DashboardComponentOut(BaseModel):
    component_id: str = Field(description="Salesforce id of the dashboard component")
    data_status: Optional[str] = Field(default=None, description="State of the component data, for example 'DATA' when it has values or 'NO_DATA' when it could not be loaded")
    refresh_status: Optional[str] = Field(default=None, description="Refresh state of the component, for example 'IDLE' or 'REFRESHING'")
    refresh_date: Optional[str] = Field(default=None, description="Date and time of the last refresh of the component, in ISO 8601 format")
    error_message: Optional[str] = Field(default=None, description="Why the component has no data, for example when the source report type is not accessible to the running user")
    report_result: Optional[dict[str, Any]] = Field(default=None, description="Report result behind the component (factMap, groupings and report metadata); empty when the component has no data")


@function(
    id="salesforce.analytics.dashboard_component", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the data of one component (chart, table or metric) of a Salesforce dashboard: its data status, the last refresh, the reason when it has "
        "no data and the report result behind it (totals and groupings). Give the dashboard id and the component id. Use it when the user asks for the "
        "numbers shown by a specific dashboard chart. The data is what Salesforce last stored for the dashboard; it is not refreshed by this call. "
        "Read-only. It fails with not_found when the dashboard or the component id does not exist. Component ids come from "
        "salesforce.analytics.dashboard_get."
    ),
    examples=[{"name": "default", "input": {"dashboard_id": "01Zfj0000022ug5EAA", "component_id": "01afj000002tJs5AAE"}, "output": {
        "component_id": "01afj000002tJs5AAE", "data_status": "DATA", "refresh_status": "IDLE", "refresh_date": "2026-10-09T12:00:00Z", "error_message": None,
        "report_result": {"factMap": {"T!T": {"aggregates": [{"label": "12", "value": 12}]}}}}}],
)
async def analytics_dashboard_component(ctx: Context, args: DashboardComponentIn) -> DashboardComponentOut:
    body = await get_json(ctx, f"/analytics/dashboards/{args.dashboard_id}")
    item = next((c for c in body.get("componentData", []) if c.get("componentId") == args.component_id), None)
    if item is None:
        raise FunctionError(ErrorCode.not_found, f"The dashboard has no component with id {args.component_id}.")
    status = item.get("status") or {}
    return DashboardComponentOut(component_id=args.component_id, data_status=status.get("componentDataStatus"), refresh_status=status.get("refreshStatus"),
                                 refresh_date=status.get("refreshDate"), error_message=status.get("errorMessage"), report_result=item.get("reportResult"))
