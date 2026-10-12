"""Lecturas de Bulk API 2.0 (trabajos de consulta) y de Acciones Invocables de Salesforce.

Verificado con la API real (2026-10-09), v62.0:
- GET /jobs/query/{id} -> {id, operation, object, state (UploadComplete, InProgress, JobComplete, Failed, Aborted), createdDate, systemModstamp,
  numberRecordsProcessed, totalProcessingTime, contentType, columnDelimiter, lineEnding, errorMessage?}; 404 NOT_FOUND si no existe.
- GET /jobs/query/{id}/results devuelve CSV (text/csv), NO JSON: `maxRecords` limita las filas y la pagina siguiente se pide con `locator`.
  Las cabeceras `Sforce-NumberOfRecords` y `Sforce-Locator` ("null" cuando no hay mas) dicen cuantas filas llegaron y cual es la siguiente pagina.
  Si el trabajo no termino responde 400 JOB_NOT_COMPLETE (con el estado actual). Un `locator` malo da 400 INVALID_QUERY_VALUE.
  El catalogo decia que devuelve {csv_data}; aqui el CSV se convierte en filas ({columna: texto}) para que el agente no tenga que parsearlo.
- GET /actions/standard -> {actions[{label, name, type, url}]} (acciones estandar de la org, p. ej. chatterPost y emailSimple).
- GET /actions/custom -> {categoria: url} (flow, apex, quickAction, emailAlert, externalService, ...); GET /actions/custom/{categoria} -> {actions[...]}
  para flow, apex y similares, o {objeto: url} para quickAction.
Solo se LEEN trabajos y acciones: no se crean trabajos Bulk ni se invoca ninguna accion. Todas piden el permiso `api`.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito.
"""
import csv
import io
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.functions.apps.salesforce._common import ID_PATTERN, UPSTREAM_API, api_base, get_json
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

JOB_ID_KW = dict(pattern=ID_PATTERN, description="Salesforce id of the Bulk API 2.0 query job, 15 or 18 letters and digits, usually starting with 750")


# --- salesforce.bulk_query.get -------------------------------------------------------------------

class QueryJobIn(BaseModel):
    job_id: str = Field(**JOB_ID_KW)


class QueryJobOut(BaseModel):
    id: str = Field(description="Salesforce id of the bulk query job")
    state: Optional[str] = Field(default=None, description="State of the job: 'UploadComplete', 'InProgress', 'JobComplete' (results ready), 'Failed' or 'Aborted'")
    operation: Optional[str] = Field(default=None, description="Kind of job: 'query' (without deleted records) or 'queryAll' (with deleted records)")
    object: Optional[str] = Field(default=None, description="API name of the object the query reads, for example 'Account'")
    created_date: Optional[str] = Field(default=None, description="Date and time when the job was created, in ISO 8601 format")
    system_modstamp: Optional[str] = Field(default=None, description="Date and time of the last change to the job, in ISO 8601 format")
    number_records_processed: Optional[int] = Field(default=None, description="How many records the job has read so far")
    total_processing_time: Optional[int] = Field(default=None, description="Total time spent processing the job, in milliseconds")
    content_type: Optional[str] = Field(default=None, description="Format of the results, always 'CSV' for query jobs")
    error_message: Optional[str] = Field(default=None, description="Why the job failed, when it did")


@function(
    id="salesforce.bulk_query.get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the status of one Bulk API 2.0 query job (a large SOQL query that Salesforce runs in the background) given its id: its state (in progress, "
        "complete, failed, aborted), the object it reads, how many records it has processed, the dates, the processing time and, when it failed, the error "
        "message. Use it when the user asks whether a bulk query has finished or why it failed, and before reading its results. Read-only: it does not "
        "start, stop or change jobs. It fails with not_found when the id does not exist. When the state is JobComplete, read the rows with "
        "salesforce.bulk_query.results."
    ),
    examples=[{"name": "default", "input": {"job_id": "750fj00000AbCdEAAV"}, "output": {
        "id": "750fj00000AbCdEAAV", "state": "JobComplete", "operation": "query", "object": "Account", "created_date": "2026-10-09T15:54:50.000+0000",
        "system_modstamp": "2026-10-09T15:54:55.000+0000", "number_records_processed": 13, "total_processing_time": 172, "content_type": "CSV"}}],
)
async def bulk_query_get(ctx: Context, args: QueryJobIn) -> QueryJobOut:
    body = await get_json(ctx, f"/jobs/query/{args.job_id}")
    return QueryJobOut(id=body.get("id") or args.job_id, state=body.get("state"), operation=body.get("operation"), object=body.get("object"),
                       created_date=body.get("createdDate"), system_modstamp=body.get("systemModstamp"), number_records_processed=body.get("numberRecordsProcessed"),
                       total_processing_time=body.get("totalProcessingTime"), content_type=body.get("contentType"), error_message=body.get("errorMessage"))


# --- salesforce.bulk_query.results ---------------------------------------------------------------

class QueryResultsIn(BaseModel):
    job_id: str = Field(**JOB_ID_KW)
    max_records: int = Field(default=200, ge=1, le=2000, description="Maximum number of rows to return in this page, from 1 to 2000 (default 200)")
    locator: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_=-]{1,200}$", description="Locator returned as next_locator by a previous call, to continue with the next page of rows")


class QueryResultsOut(BaseModel):
    columns: list[str] = Field(description="Names of the columns of the result, in the order of the query")
    records: list[dict[str, str]] = Field(description="The rows of this page; each row maps a column name to its value as text, empty text when the field has no value")
    number_of_records: int = Field(description="How many rows this page holds")
    next_locator: Optional[str] = Field(default=None, description="Locator to pass as locator to get the next page of rows; empty when this is the last page")


@function(
    id="salesforce.bulk_query.results", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Reads the result rows of a completed Bulk API 2.0 query job. Salesforce delivers them as CSV, and this function converts them into rows keyed by "
        "column name, with every value as text. It returns up to 2000 rows per page (200 by default) and continues with next_locator until it comes back "
        "empty. Use it when the user wants the data of a large background query. The job must be in state JobComplete: otherwise it fails with "
        "invalid_input and Salesforce's message with the current state. Read-only: it does not change the job or any record. It fails with not_found when "
        "the job does not exist. Check the state first with salesforce.bulk_query.get."
    ),
    examples=[{"name": "default", "input": {"job_id": "750fj00000AbCdEAAV", "max_records": 2}, "output": {
        "columns": ["Id", "Name"], "records": [{"Id": "001fj00000WTST8AAP", "Name": "Edge Communications"}, {"Id": "001fj00000WTST9AAP", "Name": "Burlington Textiles"}],
        "number_of_records": 2, "next_locator": "MjowR2FmajAwMDAwTlk4NXhDQUQ6MA"}}],
)
async def bulk_query_results(ctx: Context, args: QueryResultsIn) -> QueryResultsOut:
    params: dict[str, Any] = {"maxRecords": args.max_records}
    if args.locator:
        params["locator"] = args.locator
    base = await api_base(ctx)
    resp = await ctx.conn.request("GET", f"{base}/jobs/query/{args.job_id}/results", params=params, headers={"Accept": "text/csv"})
    reader = csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"), newline=""))
    rows = [{k: (v or "") for k, v in row.items()} for row in reader]
    locator = resp.headers.get("Sforce-Locator")
    return QueryResultsOut(columns=list(reader.fieldnames or []), records=rows, number_of_records=len(rows),
                           next_locator=None if not locator or locator.lower() == "null" else locator)


# --- salesforce.actions.standard_list ------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class ActionInfo(BaseModel):
    name: str = Field(description="API name of the action, for example 'chatterPost' or 'emailSimple'")
    label: Optional[str] = Field(default=None, description="Label of the action as shown in Salesforce, in the language of the org")
    type: Optional[str] = Field(default=None, description="Kind of action as Salesforce names it, for example 'CHATTERPOST', 'EMAILSIMPLE' or 'FLOW'")
    url: Optional[str] = Field(default=None, description="Path of the action in the Salesforce API, relative to the org URL")


class ActionsOut(BaseModel):
    actions: list[ActionInfo] = Field(description="The invocable actions found, in the order Salesforce lists them")


def _action(raw: dict[str, Any]) -> ActionInfo:
    return ActionInfo(name=raw["name"], label=raw.get("label"), type=raw.get("type"), url=raw.get("url"))


@function(
    id="salesforce.actions.standard_list", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the standard invocable actions available in the connected Salesforce org, such as posting to Chatter, sending an email, submitting a record "
        "for approval or sending a custom notification, each with its API name, label, kind and path. Use it when the user asks what built-in actions "
        "Salesforce can run through the API or needs the exact name of one. Read-only and without parameters: it only lists the actions and never runs "
        "them, so nothing is sent or changed. For the actions the org built itself (flows, Apex, quick actions) use salesforce.actions.custom_list."
    ),
    examples=[{"name": "default", "input": {}, "output": {"actions": [
        {"name": "chatterPost", "label": "Post to Chatter", "type": "CHATTERPOST", "url": "/services/data/v62.0/actions/standard/chatterPost"}]}}],
)
async def actions_standard_list(ctx: Context, args: NoArgs) -> ActionsOut:
    body = await get_json(ctx, "/actions/standard")
    return ActionsOut(actions=[_action(a) for a in body.get("actions", []) if a.get("name")])


# --- salesforce.actions.custom_list --------------------------------------------------------------

class CustomActionsIn(BaseModel):
    action_type: Optional[str] = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9]{0,40}$", description="Category to open, as returned in categories, for example 'flow' or 'apex'; leave empty to list the categories")


class CustomActionsOut(BaseModel):
    categories: dict[str, str] = Field(description="Categories (or, for quickAction, objects) mapped to their path in the Salesforce API; empty when the actions of a category are listed in actions")
    actions: list[ActionInfo] = Field(description="The actions of the requested category, for example every flow that can be invoked; empty when only categories are listed")


@function(
    id="salesforce.actions.custom_list", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the custom invocable actions of the connected Salesforce org, the ones built by the company: flows, Apex actions, quick actions, email alerts "
        "and external services. Without parameters it returns the categories available; with action_type (for example 'flow' or 'apex') it returns the "
        "actions of that category with their API name, label, kind and path. Use it when the user asks which automations or flows can be run through the "
        "API. Read-only: it only lists the actions and never runs them, so nothing is sent or changed. A category that does not exist fails with not_found. "
        "For the built-in actions use salesforce.actions.standard_list."
    ),
    examples=[{"name": "default", "input": {"action_type": "flow"}, "output": {"categories": {}, "actions": [
        {"name": "Cancel_Order", "label": "Cancel Order", "type": "FLOW", "url": "/services/data/v62.0/actions/custom/flow/Cancel_Order"}]}}],
)
async def actions_custom_list(ctx: Context, args: CustomActionsIn) -> CustomActionsOut:
    body = await get_json(ctx, f"/actions/custom/{args.action_type}" if args.action_type else "/actions/custom")
    if isinstance(body, dict) and isinstance(body.get("actions"), list):
        return CustomActionsOut(categories={}, actions=[_action(a) for a in body["actions"] if a.get("name")])
    return CustomActionsOut(categories={k: str(v) for k, v in body.items()}, actions=[])
