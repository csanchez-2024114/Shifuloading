"""Lecturas de la org de Salesforce: limites, recientes, vistas de lista, tipos de registro, listas desplegables, recursos de la API y trabajos Bulk.

Verificado con la API real (2026-10-09), v62.0:
- GET /limits -> {NombreDelLimite: {Max, Remaining}} (71 limites). GET /recent?limit=N -> lista de {attributes{type}, Id, Name}.
- GET /sobjects/{Tipo}/listviews -> {done, listviews[{id, label, developerName, soqlCompatible, describeUrl, resultsUrl}]};
  GET .../listviews/{id}/results?limit=&offset= -> {columns[{fieldNameOrPath, label, type, hidden}], records[{columns[{fieldNameOrPath, value}]}], size, done, id, label, developerName}.
- `GET /sobjects/{Tipo}/describe/recordTypes` NO existe (404): los tipos de registro salen de `recordTypeInfos` de `describe`. Las listas desplegables
  salen de `fields[].picklistValues` de `describe` (value, label, active, defaultValue, validFor).
- GET /metadata solo expone {deployRequest} (la API Metadata completa es SOAP) y GET /tooling lista los recursos de la Tooling API (query, search, ...).
- GET /services/data (sin version ni autenticacion obligatoria) lista las versiones [{label, url, version}]; GET /services/data/v62.0 lista los recursos de esa version.
- GET /jobs/ingest/{id} -> estado de un trabajo Bulk API 2.0 de carga (404 si no existe); GET /jobs/ingest lista los trabajos.
La org de prueba no tiene trabajos Bulk: `bulk.job_get` solo se probo con un id inexistente. Todas piden el permiso `api`.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito.
"""
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.functions.apps.salesforce._common import (
    API_VERSION, ID_PATTERN, SOBJECT_PATTERN, UPSTREAM_API, get_json, get_root_json,
)
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.apps.salesforce.f_meta import RecordTypeInfo, SObjectTypeIn
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb


# --- salesforce.limits.get -----------------------------------------------------------------------

class LimitInfo(BaseModel):
    name: str = Field(description="Name of the limit as Salesforce reports it, for example 'DailyApiRequests' or 'DataStorageMB'")
    max: int = Field(description="Maximum allowed for this limit in the current period")
    remaining: int = Field(description="How much of the limit is still available")
    used: int = Field(description="How much of the limit has been consumed (max minus remaining)")


class LimitsIn(BaseModel):
    name_contains: Optional[str] = Field(default=None, min_length=1, max_length=80, description="Optional text contained in the limit name, ignoring upper and lower case, for example 'api' or 'storage'")


class LimitsOut(BaseModel):
    limits: list[LimitInfo] = Field(description="The limits of the org with their maximum, remaining and used amounts, in alphabetical order")


@function(
    id="salesforce.limits.get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the usage limits of the connected Salesforce org, such as daily API requests, data and file storage, email sends and concurrent report runs, "
        "each with its maximum, what remains and what has been used. Use it when the user asks how many API calls are left today, whether the org is close to "
        "a limit, or why requests are being rejected. It can filter by text in the limit name, for example 'api' or 'storage'. Read-only: it does not change "
        "limits or consume them beyond this one request. The names are the ones Salesforce uses and some limits are not available in every edition."
    ),
    examples=[{"name": "default", "input": {"name_contains": "DailyApi"}, "output": {"limits": [
        {"name": "DailyApiRequests", "max": 15000, "remaining": 14980, "used": 20}]}}],
)
async def limits_get(ctx: Context, args: LimitsIn) -> LimitsOut:
    body = await get_json(ctx, "/limits")
    needle = args.name_contains.lower() if args.name_contains else None
    items = [LimitInfo(name=k, max=int(v.get("Max", 0)), remaining=int(v.get("Remaining", 0)), used=int(v.get("Max", 0)) - int(v.get("Remaining", 0)))
             for k, v in sorted(body.items()) if isinstance(v, dict) and (not needle or needle in k.lower())]
    return LimitsOut(limits=items)


# --- salesforce.recent.get -----------------------------------------------------------------------

class RecentIn(BaseModel):
    limit: int = Field(default=25, ge=1, le=200, description="How many recent items to return, from 1 to 200 (default 25)")


class RecentItem(BaseModel):
    id: str = Field(description="Salesforce id of the record the user viewed or changed recently")
    name: Optional[str] = Field(default=None, description="Name of the record, when the object has a name field")
    sobject_type: Optional[str] = Field(default=None, description="API name of the object the record belongs to, for example 'Account' or 'Opportunity'")


class RecentOut(BaseModel):
    items: list[RecentItem] = Field(description="The records the connected user viewed or changed most recently, most recent first")


@function(
    id="salesforce.recent.get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the records the connected Salesforce user viewed or changed most recently, across all objects, each with its id, name and object type. Use it "
        "when the user asks what they were working on, wants to jump back to a record they opened lately, or needs the ids of their latest activity. It "
        "returns up to 200 items. Read-only: it does not open or change anything. It only covers the connected user, not the whole org. To see recent "
        "records of one object use salesforce.sobject.get_metadata, and to read a record use its object's get function."
    ),
    examples=[{"name": "default", "input": {"limit": 2}, "output": {"items": [
        {"id": "001fj00000WTSTKAA5", "name": "Acme Corp", "sobject_type": "Account"}, {"id": "500fj00000lnVGdAAM", "name": "00001001", "sobject_type": "Case"}]}}],
)
async def recent_get(ctx: Context, args: RecentIn) -> RecentOut:
    body = await get_json(ctx, "/recent", params={"limit": args.limit})
    rows = body if isinstance(body, list) else body.get("records", [])
    return RecentOut(items=[RecentItem(id=r["Id"], name=r.get("Name"), sobject_type=(r.get("attributes") or {}).get("type")) for r in rows if r.get("Id")])


# --- salesforce.list_views.describe --------------------------------------------------------------

class ListViewInfo(BaseModel):
    id: str = Field(description="Salesforce id of the list view, usable in salesforce.list_views.run, usually starting with 00B")
    label: Optional[str] = Field(default=None, description="Name of the list view as shown in Salesforce, in the language of the org")
    developer_name: Optional[str] = Field(default=None, description="API name of the list view, stable across languages, for example 'AllAccounts'")
    soql_compatible: Optional[bool] = Field(default=None, description="True when the list view can be expressed as a SOQL query")


class ListViewsOut(BaseModel):
    sobject_type: str = Field(description="API name of the object the list views belong to")
    list_views: list[ListViewInfo] = Field(description="The list views of the object that the connected user can see")
    done: bool = Field(description="True when these are all the list views; false when Salesforce has more than it returned")


@function(
    id="salesforce.list_views.describe", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the list views (saved filters such as 'All Accounts' or 'New This Week') that the connected Salesforce user can see for one object, each with "
        "its id, label and API name. Use it when the user asks which saved views exist for Accounts, Contacts, Opportunities or any other object, or needs "
        "a list view id to run it. Give the object API name. Read-only: it does not run the views or change them. It fails with not_found when the object "
        "does not exist or has no list views. To get the records of a view use salesforce.list_views.run."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account"}, "output": {"sobject_type": "Account", "list_views": [
        {"id": "00Bfj00000HjWmCEAV", "label": "New This Week", "developer_name": "NewThisWeek", "soql_compatible": True}], "done": True}}],
)
async def list_views_describe(ctx: Context, args: SObjectTypeIn) -> ListViewsOut:
    body = await get_json(ctx, f"/sobjects/{args.sobject_type}/listviews")
    views = [ListViewInfo(id=v["id"], label=v.get("label"), developer_name=v.get("developerName"), soql_compatible=v.get("soqlCompatible")) for v in body.get("listviews", [])]
    return ListViewsOut(sobject_type=args.sobject_type, list_views=views, done=bool(body.get("done", True)))


# --- salesforce.list_views.run -------------------------------------------------------------------

class ListViewRunIn(BaseModel):
    sobject_type: str = Field(pattern=SOBJECT_PATTERN, description="API name of the Salesforce object the list view belongs to, for example 'Account'")
    list_view_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the list view, 15 or 18 letters and digits, usually starting with 00B")
    limit: int = Field(default=50, ge=1, le=200, description="How many records to return, from 1 to 200 (default 50)")
    offset: int = Field(default=0, ge=0, le=2000, description="How many records to skip, from 0 to 2000; use the next_offset value of a previous result to continue")


class ListViewColumn(BaseModel):
    field_name: str = Field(description="API name or path of the field shown in this column, for example 'Name' or 'Owner.Alias'")
    label: Optional[str] = Field(default=None, description="Label of the column as shown in Salesforce, in the language of the org")
    type: Optional[str] = Field(default=None, description="Data type of the column, for example 'string', 'picklist', 'date' or 'phone'")


class ListViewRunOut(BaseModel):
    label: Optional[str] = Field(default=None, description="Name of the list view as shown in Salesforce")
    columns: list[ListViewColumn] = Field(description="The visible columns of the list view, in display order")
    records: list[dict[str, Any]] = Field(description="The rows of this page; each row maps a column field name to its value (including 'Id' when the view carries it)")
    has_more: bool = Field(description="True when the view has more rows than were returned and a next page can be requested")
    next_offset: Optional[int] = Field(default=None, description="Offset to pass as input to get the next page of rows; empty when there is no next page or Salesforce cannot skip that far")


@function(
    id="salesforce.list_views.run", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Runs one saved list view of a Salesforce object and returns its rows exactly as the view filters and sorts them, with the visible columns and a "
        "value for each column of each row. Use it when the user asks for the content of a view such as 'All Accounts' or 'My Open Opportunities'. Give the "
        "object API name and the list view id. It returns up to 200 rows per call and continues with next_offset (Salesforce can skip at most 2000). "
        "Read-only: it does not change the view or the records. It fails with not_found when the view does not exist. To find view ids use "
        "salesforce.list_views.describe."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account", "list_view_id": "00Bfj00000HjrRKEAZ", "limit": 1}, "output": {
        "label": "All Accounts", "columns": [{"field_name": "Name", "label": "Account Name", "type": "string"}],
        "records": [{"Name": "Acme Corp", "Id": "001fj00000WTSTKAA5"}], "has_more": False}}],
)
async def list_views_run(ctx: Context, args: ListViewRunIn) -> ListViewRunOut:
    body = await get_json(ctx, f"/sobjects/{args.sobject_type}/listviews/{args.list_view_id}/results", params={"limit": args.limit + 1, "offset": args.offset})
    rows = body.get("records", [])
    page = [{c.get("fieldNameOrPath"): c.get("value") for c in r.get("columns", [])} for r in rows[:args.limit]]
    has_more = len(rows) > args.limit
    nxt = args.offset + args.limit
    cols = [ListViewColumn(field_name=c["fieldNameOrPath"], label=c.get("label"), type=c.get("type")) for c in body.get("columns", []) if not c.get("hidden") and c.get("fieldNameOrPath")]
    return ListViewRunOut(label=body.get("label"), columns=cols, records=page, has_more=has_more, next_offset=nxt if has_more and nxt <= 2000 else None)


# --- salesforce.record_type.get ------------------------------------------------------------------

class RecordTypesOut(BaseModel):
    sobject_type: str = Field(description="API name of the object the record types belong to")
    record_types: list[RecordTypeInfo] = Field(description="The record types of the object that the connected user can see; objects without custom record types only have the master one")


@function(
    id="salesforce.record_type.get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the record types of one Salesforce object that the connected user can see, each with its id, name, API name, whether the user can use it, "
        "whether it is the user's default and whether it is the master record type. Record types let one object (for example Opportunity) have different "
        "processes, page layouts and picklist values. Use it when the user asks which record types an object has or needs a record type id. Give the object "
        "API name. Read-only. It fails with not_found when the object does not exist. For all the fields of the object use salesforce.sobject.describe."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Opportunity"}, "output": {"sobject_type": "Opportunity", "record_types": [
        {"record_type_id": "012000000000000AAA", "name": "Master", "developer_name": "Master", "available": True, "default": True, "master": True}]}}],
)
async def record_type_get(ctx: Context, args: SObjectTypeIn) -> RecordTypesOut:
    body = await get_json(ctx, f"/sobjects/{args.sobject_type}/describe")
    types = [RecordTypeInfo(record_type_id=r["recordTypeId"], name=r.get("name"), developer_name=r.get("developerName"), available=r.get("available"),
                            default=r.get("defaultRecordTypeMapping"), master=r.get("master")) for r in body.get("recordTypeInfos", [])]
    return RecordTypesOut(sobject_type=args.sobject_type, record_types=types)


# --- salesforce.picklist.get ---------------------------------------------------------------------

class PicklistIn(BaseModel):
    sobject_type: str = Field(pattern=SOBJECT_PATTERN, description="API name of the Salesforce object that holds the field, for example 'Lead'")
    field_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$", description="API name of the picklist field, for example 'Status' or 'Industry'")


class PicklistValue(BaseModel):
    value: str = Field(description="Value stored in Salesforce for this option, which is what filters and queries must use")
    label: Optional[str] = Field(default=None, description="Label of the option as shown in Salesforce, in the language of the org")
    active: Optional[bool] = Field(default=None, description="True when the option can currently be chosen")
    default: Optional[bool] = Field(default=None, description="True when the option is the default of the field")


class PicklistOut(BaseModel):
    sobject_type: str = Field(description="API name of the object that holds the field")
    field_name: str = Field(description="API name of the picklist field")
    label: Optional[str] = Field(default=None, description="Label of the field as shown in Salesforce, in the language of the org")
    type: Optional[str] = Field(default=None, description="Field type: 'picklist' or 'multipicklist'")
    restricted: Optional[bool] = Field(default=None, description="True when only the listed values are allowed; false when users may type other values")
    controlling_field: Optional[str] = Field(default=None, description="API name of the field that controls which values are available, for dependent picklists; empty otherwise")
    values: list[PicklistValue] = Field(description="The options of the picklist in the order Salesforce shows them")


@function(
    id="salesforce.picklist.get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the options of one picklist (dropdown) field of a Salesforce object, for example the statuses of a Lead or the industries of an Account, "
        "each with the stored value, its label, whether it is active and whether it is the default. Use it when the user asks which values a field accepts, "
        "or before filtering or writing records so the value is spelled exactly as Salesforce stores it. Give the object API name and the field API name. "
        "Read-only. It fails with not_found when the field does not exist and with invalid_input when the field is not a picklist. For all the fields of "
        "an object use salesforce.sobject.describe."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Lead", "field_name": "Status"}, "output": {
        "sobject_type": "Lead", "field_name": "Status", "label": "Status", "type": "picklist", "restricted": False, "controlling_field": None,
        "values": [{"value": "Open - Not Contacted", "label": "Open - Not Contacted", "active": True, "default": True}]}}],
)
async def picklist_get(ctx: Context, args: PicklistIn) -> PicklistOut:
    body = await get_json(ctx, f"/sobjects/{args.sobject_type}/describe")
    field = next((f for f in body.get("fields", []) if str(f.get("name", "")).lower() == args.field_name.lower()), None)
    if field is None:
        raise FunctionError(ErrorCode.not_found, f"{args.sobject_type} has no field named {args.field_name}.")
    if field.get("type") not in ("picklist", "multipicklist"):
        raise FunctionError(ErrorCode.invalid_input, f"{field['name']} is a {field.get('type')} field, not a picklist.")
    values = [PicklistValue(value=v["value"], label=v.get("label"), active=v.get("active"), default=v.get("defaultValue")) for v in field.get("picklistValues", [])]
    return PicklistOut(sobject_type=args.sobject_type, field_name=field["name"], label=field.get("label"), type=field.get("type"),
                       restricted=field.get("restrictedPicklist"), controlling_field=field.get("controllerName"), values=values)


# --- salesforce.metadata.describe / salesforce.tooling.describe ----------------------------------

class NoArgs(BaseModel):
    pass


class ResourcesOut(BaseModel):
    resources: dict[str, str] = Field(description="Names of the available API resources mapped to their path in the Salesforce API, relative to the org URL")


@function(
    id="salesforce.metadata.describe", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the resources the Salesforce REST Metadata API exposes for the connected org, each with its path. Today that is only the deployment request "
        "resource, because the full Metadata API (objects, layouts, flows) is available through SOAP and not through this REST entry point. Use it when "
        "the user asks what the metadata endpoint offers or to check that the org allows metadata access. Read-only and without parameters: it does not "
        "deploy or retrieve any metadata. To inspect objects and fields use salesforce.sobject.describe and salesforce.sobject.describe_global instead."
    ),
    examples=[{"name": "default", "input": {}, "output": {"resources": {"deployRequest": "/services/data/v62.0/metadata/deployRequest"}}}],
)
async def metadata_describe(ctx: Context, args: NoArgs) -> ResourcesOut:
    return ResourcesOut(resources={k: str(v) for k, v in (await get_json(ctx, "/metadata")).items()})


@function(
    id="salesforce.tooling.describe", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the resources of the Salesforce Tooling API for the connected org, each with its path: query, search, sobjects, apex test runs, code "
        "completions and others. The Tooling API is used by developer tools to work with Apex classes, triggers, flows and other configuration. Use it "
        "when the user asks what the Tooling API offers or to check that it is reachable. Read-only and without parameters: it does not run tests, query "
        "code or change anything. For ordinary records and objects use the other salesforce.sobject and salesforce.soql functions."
    ),
    examples=[{"name": "default", "input": {}, "output": {"resources": {"query": "/services/data/v62.0/tooling/query", "search": "/services/data/v62.0/tooling/search"}}}],
)
async def tooling_describe(ctx: Context, args: NoArgs) -> ResourcesOut:
    return ResourcesOut(resources={k: str(v) for k, v in (await get_json(ctx, "/tooling")).items()})


# --- salesforce.data.version / salesforce.data.version_resources ---------------------------------

class ApiVersion(BaseModel):
    version: str = Field(description="Version number of the REST API, for example '62.0'")
    label: Optional[str] = Field(default=None, description="Release name of that version, for example 'Winter 25'")
    url: Optional[str] = Field(default=None, description="Path of that version in the Salesforce API, relative to the org URL")


class VersionsOut(BaseModel):
    in_use: str = Field(description="REST API version this connector uses for all its calls, for example '62.0'")
    versions: list[ApiVersion] = Field(description="All the REST API versions the org supports, oldest first")


@function(
    id="salesforce.data.version", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the versions of the Salesforce REST API that the connected org supports, with the release name and path of each, and tells which version this "
        "connector uses (currently 62.0). Use it when the user asks which API versions are available, whether the org supports a given version, or how "
        "recent the org is. Read-only and without parameters: it does not change anything. To see what a version offers use salesforce.data.version_resources."
    ),
    examples=[{"name": "default", "input": {}, "output": {"in_use": "62.0", "versions": [{"version": "62.0", "label": "Winter '25", "url": "/services/data/v62.0"}]}}],
)
async def data_version(ctx: Context, args: NoArgs) -> VersionsOut:
    rows = await get_root_json(ctx)
    return VersionsOut(in_use=API_VERSION, versions=[ApiVersion(version=str(r["version"]), label=r.get("label"), url=r.get("url")) for r in rows if r.get("version")])


class VersionResourcesIn(BaseModel):
    version: str = Field(default=API_VERSION, pattern=r"^\d{2,3}\.0$", description="REST API version to inspect, in the form '62.0'; defaults to the version this connector uses")


class VersionResourcesOut(ResourcesOut):
    version: str = Field(description="The REST API version these resources belong to")


@function(
    id="salesforce.data.version_resources", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the resources available in one version of the Salesforce REST API for the connected org: sobjects, query, search, limits, recent, analytics, "
        "tooling, composite and others, each with its path. Use it when the user asks what the API can do in a version or whether a feature such as "
        "analytics or composite requests exists. The version defaults to 62.0, which this connector uses, and must look like '62.0'. Read-only: it does not "
        "call any of the resources. It fails with not_found when the org does not support that version. To list versions use salesforce.data.version."
    ),
    examples=[{"name": "default", "input": {"version": "62.0"}, "output": {"version": "62.0", "resources": {"sobjects": "/services/data/v62.0/sobjects", "query": "/services/data/v62.0/query"}}}],
)
async def data_version_resources(ctx: Context, args: VersionResourcesIn) -> VersionResourcesOut:
    body = await get_root_json(ctx, f"/v{args.version}")
    return VersionResourcesOut(version=args.version, resources={k: str(v) for k, v in body.items()})


# --- salesforce.bulk.job_get ---------------------------------------------------------------------

class BulkJobIn(BaseModel):
    job_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the Bulk API 2.0 ingest job, 15 or 18 letters and digits, usually starting with 750")


class BulkJobOut(BaseModel):
    id: str = Field(description="Salesforce id of the bulk job")
    state: Optional[str] = Field(default=None, description="State of the job: 'Open', 'UploadComplete', 'InProgress', 'JobComplete', 'Failed' or 'Aborted'")
    operation: Optional[str] = Field(default=None, description="What the job does with the records: 'insert', 'update', 'upsert', 'delete' or 'hardDelete'")
    object: Optional[str] = Field(default=None, description="API name of the object the job loads records into, for example 'Contact'")
    created_date: Optional[str] = Field(default=None, description="Date and time when the job was created, in ISO 8601 format")
    system_modstamp: Optional[str] = Field(default=None, description="Date and time of the last change to the job, in ISO 8601 format")
    number_records_processed: Optional[int] = Field(default=None, description="How many records the job has processed so far")
    number_records_failed: Optional[int] = Field(default=None, description="How many records the job could not process")
    total_processing_time: Optional[int] = Field(default=None, description="Total time spent processing the job, in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Why the job failed, when it did")


@function(
    id="salesforce.bulk.job_get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the status of one Bulk API 2.0 ingest job (a mass load of records into Salesforce) given its id: its state (open, in progress, complete, "
        "failed, aborted), the operation, the target object, how many records were processed and how many failed, the dates and, when it failed, the "
        "error message. Use it when the user asks whether a bulk load finished or why it failed. Read-only: it does not start, stop or change jobs. It "
        "fails with not_found when the id does not exist. It covers ingest (load) jobs only; for bulk query jobs there is no function in this connector."
    ),
    examples=[{"name": "default", "input": {"job_id": "750fj00000AbCdEAAV"}, "output": {
        "id": "750fj00000AbCdEAAV", "state": "JobComplete", "operation": "insert", "object": "Contact", "created_date": "2026-10-08T10:00:00.000+0000",
        "system_modstamp": "2026-10-08T10:01:00.000+0000", "number_records_processed": 100, "number_records_failed": 0, "total_processing_time": 1200}}],
)
async def bulk_job_get(ctx: Context, args: BulkJobIn) -> BulkJobOut:
    body = await get_json(ctx, f"/jobs/ingest/{args.job_id}")
    return BulkJobOut(id=body.get("id") or args.job_id, state=body.get("state"), operation=body.get("operation"), object=body.get("object"),
                      created_date=body.get("createdDate"), system_modstamp=body.get("systemModstamp"), number_records_processed=body.get("numberRecordsProcessed"),
                      number_records_failed=body.get("numberRecordsFailed"), total_processing_time=body.get("totalProcessingTime"), error_message=body.get("errorMessage"))
