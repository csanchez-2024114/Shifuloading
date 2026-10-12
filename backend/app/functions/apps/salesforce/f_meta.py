"""Lecturas de objetos genericos (sObjects) de Salesforce: descripcion, registros por tipo, por clave externa y cambios recientes.

Verificado con la API real (2026-10-09), v62.0:
- GET /sobjects                       -> {encoding, maxBatchSize, sobjects[{name, label, labelPlural, keyPrefix, custom, queryable, ...}]}
- GET /sobjects/{Tipo}                -> {objectDescribe{...}, recentItems[{Id, Name, attributes}]}
- GET /sobjects/{Tipo}/describe       -> {name, label, fields[...], childRelationships[...], recordTypeInfos[...], ...}
- GET /sobjects/{Tipo}/{id}           -> el registro (todos sus campos, o solo `fields=A,B`); 404 NOT_FOUND si no existe
- GET /sobjects/{Tipo}/{campo}/{valor}-> un registro por un campo de clave externa o `Id`; 404 si el campo no es de clave externa, 300 si varios coinciden
- GET /sobjects/{Tipo}/deleted|updated?start=&end= -> {deletedRecords[{id, deletedDate}], earliestDateAvailable, latestDateCovered} / {ids[], latestDateCovered};
  `start` no puede ser de hace mas de 30 dias (400 INVALID_REPLICATION_DATE).
El catalogo decia que `list_by_type` usa `?limit=` en /sobjects/{Tipo}: no existe; se lista con SOQL (SELECT campos FROM Tipo LIMIT n OFFSET m).
Todas piden el permiso `api`. Las descripciones y los Field(description=...) estan en INGLES y completos a proposito.
"""
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.salesforce._common import (
    FIELD_PATTERN, ID_PATTERN, SOBJECT_PATTERN, UPSTREAM_API, clean_record, get_json,
)
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

MAX_OFFSET = 2000  # tope de OFFSET en SOQL

SOBJECT_TYPE_KW = dict(pattern=SOBJECT_PATTERN, description="API name of the Salesforce object, for example 'Account', 'Contact' or a custom object such as 'Invoice__c'")
FIELDS_KW = dict(default=None, max_length=100, description="API names of the fields to return, for example ['Id', 'Name', 'Industry']; related fields such as 'Owner.Name' are allowed")


def _check_fields(fields: Optional[list[str]]) -> Optional[list[str]]:
    for f in fields or []:
        if not re.match(FIELD_PATTERN, f):
            raise ValueError(f"'{f}' is not a valid field API name")
    return fields


# --- salesforce.sobject.describe_global ----------------------------------------------------------

class ObjectSummary(BaseModel):
    name: str = Field(description="API name of the object, used in every other function, for example 'Account' or 'Invoice__c'")
    label: Optional[str] = Field(default=None, description="Label of the object as shown in the Salesforce interface, in the language of the org")
    label_plural: Optional[str] = Field(default=None, description="Plural label of the object as shown in the Salesforce interface")
    key_prefix: Optional[str] = Field(default=None, description="First three characters of the record ids of this object, for example '001' for accounts")
    custom: Optional[bool] = Field(default=None, description="True for custom objects created in this org (their names end in __c)")
    queryable: Optional[bool] = Field(default=None, description="True when records of the object can be read with SOQL queries")
    searchable: Optional[bool] = Field(default=None, description="True when records of the object are included in text searches (SOSL)")
    createable: Optional[bool] = Field(default=None, description="True when the connected user can create records of this object")
    updateable: Optional[bool] = Field(default=None, description="True when the connected user can update records of this object")
    deletable: Optional[bool] = Field(default=None, description="True when the connected user can delete records of this object")


def _summary(raw: dict[str, Any]) -> ObjectSummary:
    return ObjectSummary(name=raw["name"], label=raw.get("label"), label_plural=raw.get("labelPlural"), key_prefix=raw.get("keyPrefix"),
                         custom=raw.get("custom"), queryable=raw.get("queryable"), searchable=raw.get("searchable"),
                         createable=raw.get("createable"), updateable=raw.get("updateable"), deletable=raw.get("deletable"))


class DescribeGlobalIn(BaseModel):
    name_contains: Optional[str] = Field(default=None, min_length=1, max_length=80, description="Only objects whose API name or label contains this text, ignoring upper and lower case, for example 'invoice'")
    custom_only: bool = Field(default=False, description="When true, only custom objects (created in this org) are returned; default false returns all objects")
    queryable_only: bool = Field(default=False, description="When true, only objects whose records can be read with SOQL are returned; default false returns all objects")
    limit: int = Field(default=200, ge=1, le=500, description="How many objects to return, from 1 to 500 (default 200)")
    offset: int = Field(default=0, ge=0, description="How many matching objects to skip; use the next_offset value of a previous result to continue")


class DescribeGlobalOut(BaseModel):
    sobjects: list[ObjectSummary] = Field(description="The objects returned in this page, in the order Salesforce lists them")
    total: int = Field(description="How many objects match the filters in total, across all pages")
    has_more: bool = Field(description="True when more objects match than were returned and a next page can be requested")
    next_offset: Optional[int] = Field(default=None, description="Offset to pass as input to get the next page of objects; empty when there is no next page")


@function(
    id="salesforce.sobject.describe_global", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the objects (sObjects) available in the connected Salesforce org, both standard ones such as Account or Opportunity and custom ones, with "
        "their API name, label, id prefix and what the connected user can do with them (query, search, create, update, delete). Use it when the user asks "
        "which kinds of data their Salesforce holds, or to discover the exact API name of an object before describing it or querying it. It can filter by "
        "text in the name or label, only custom objects, or only queryable ones, and returns up to 500 objects per call. Read-only. For the fields of "
        "one object use salesforce.sobject.describe."
    ),
    examples=[{"name": "default", "input": {"name_contains": "account", "limit": 2}, "output": {"sobjects": [
        {"name": "Account", "label": "Account", "label_plural": "Accounts", "key_prefix": "001", "custom": False, "queryable": True, "searchable": True,
         "createable": True, "updateable": True, "deletable": True}], "total": 1, "has_more": False}}],
)
async def sobject_describe_global(ctx: Context, args: DescribeGlobalIn) -> DescribeGlobalOut:
    body = await get_json(ctx, "/sobjects")
    needle = args.name_contains.lower() if args.name_contains else None
    rows = [r for r in body.get("sobjects", [])
            if (not args.custom_only or r.get("custom")) and (not args.queryable_only or r.get("queryable"))
            and (not needle or needle in str(r.get("name", "")).lower() or needle in str(r.get("label", "")).lower())]
    page = rows[args.offset:args.offset + args.limit]
    end = args.offset + len(page)
    return DescribeGlobalOut(sobjects=[_summary(r) for r in page], total=len(rows), has_more=end < len(rows), next_offset=end if end < len(rows) else None)


# --- salesforce.sobject.describe -----------------------------------------------------------------

class FieldInfo(BaseModel):
    name: str = Field(description="API name of the field, used in SOQL queries and filters, for example 'Industry' or 'Region__c'")
    label: Optional[str] = Field(default=None, description="Label of the field as shown in the Salesforce interface, in the language of the org")
    type: Optional[str] = Field(default=None, description="Data type of the field, for example 'string', 'picklist', 'reference', 'currency', 'date' or 'boolean'")
    length: Optional[int] = Field(default=None, description="Maximum length of the text for text fields; 0 for other types")
    nillable: Optional[bool] = Field(default=None, description="True when the field can be empty")
    custom: Optional[bool] = Field(default=None, description="True for custom fields created in this org (their names end in __c)")
    createable: Optional[bool] = Field(default=None, description="True when a value can be given when creating a record")
    updateable: Optional[bool] = Field(default=None, description="True when the value can be changed after the record is created")
    filterable: Optional[bool] = Field(default=None, description="True when the field can be used in a WHERE clause of a query")
    external_id: Optional[bool] = Field(default=None, description="True when the field is marked as an external id and can be used in salesforce.sobject.get_by_external_id")
    reference_to: list[str] = Field(default_factory=list, description="For lookup fields, the API names of the objects the field points to")
    relationship_name: Optional[str] = Field(default=None, description="For lookup fields, the name used to reach the related record in queries, for example 'Owner'")


class ChildRelationship(BaseModel):
    child_sobject: str = Field(description="API name of the child object that points to this object, for example 'Contact'")
    field: str = Field(description="API name of the field of the child object that holds the id of this object, for example 'AccountId'")
    relationship_name: Optional[str] = Field(default=None, description="Plural name used in queries to reach the child records, for example 'Contacts'")


class RecordTypeInfo(BaseModel):
    record_type_id: str = Field(description="Salesforce id of the record type")
    name: Optional[str] = Field(default=None, description="Name of the record type as shown in the Salesforce interface")
    developer_name: Optional[str] = Field(default=None, description="API name of the record type")
    available: Optional[bool] = Field(default=None, description="True when the connected user can use this record type")
    default: Optional[bool] = Field(default=None, description="True when this is the default record type of the connected user")
    master: Optional[bool] = Field(default=None, description="True for the master record type that every object has")


class DescribeIn(BaseModel):
    sobject_type: str = Field(**SOBJECT_TYPE_KW)
    include_child_relationships: bool = Field(default=False, description="When true, also returns the child objects that point to this one (can be over a hundred entries); default false")


class DescribeOut(ObjectSummary):
    field_count: int = Field(description="Number of fields of the object")
    fields: list[FieldInfo] = Field(description="All the fields of the object with their API name, type and capabilities")
    record_types: list[RecordTypeInfo] = Field(description="The record types of the object that the connected user can see")
    child_relationships: list[ChildRelationship] = Field(default_factory=list, description="Child objects that point to this one; empty unless include_child_relationships is true")


@function(
    id="salesforce.sobject.describe", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Describes one Salesforce object (sObject) in full: its API name, label and capabilities, every field with its API name, label, data type, length, "
        "whether it can be empty, created, updated or filtered, whether it is an external id and which objects a lookup field points to, plus the record "
        "types and, on request, the child objects that point to it. Use it when the user asks what fields an object has, or before writing a query to find "
        "the exact API names. The object name must be the API name, for example 'Account' or 'Invoice__c'. Read-only. It fails with not_found when the "
        "object does not exist. To list the available objects use salesforce.sobject.describe_global."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account"}, "output": {
        "name": "Account", "label": "Account", "label_plural": "Accounts", "key_prefix": "001", "custom": False, "queryable": True, "searchable": True,
        "createable": True, "updateable": True, "deletable": True, "field_count": 1,
        "fields": [{"name": "Name", "label": "Account Name", "type": "string", "length": 255, "nillable": False, "custom": False, "createable": True,
                    "updateable": True, "filterable": True, "external_id": False, "reference_to": [], "relationship_name": None}],
        "record_types": [{"record_type_id": "012000000000000AAA", "name": "Master", "developer_name": "Master", "available": True, "default": True, "master": True}],
        "child_relationships": []}}],
)
async def sobject_describe(ctx: Context, args: DescribeIn) -> DescribeOut:
    raw = await get_json(ctx, f"/sobjects/{args.sobject_type}/describe")
    fields = [FieldInfo(name=f["name"], label=f.get("label"), type=f.get("type"), length=f.get("length"), nillable=f.get("nillable"), custom=f.get("custom"),
                        createable=f.get("createable"), updateable=f.get("updateable"), filterable=f.get("filterable"), external_id=f.get("externalId"),
                        reference_to=list(f.get("referenceTo") or []), relationship_name=f.get("relationshipName")) for f in raw.get("fields", [])]
    record_types = [RecordTypeInfo(record_type_id=r["recordTypeId"], name=r.get("name"), developer_name=r.get("developerName"), available=r.get("available"),
                                   default=r.get("defaultRecordTypeMapping"), master=r.get("master")) for r in raw.get("recordTypeInfos", [])]
    children = [ChildRelationship(child_sobject=c["childSObject"], field=c["field"], relationship_name=c.get("relationshipName"))
                for c in raw.get("childRelationships", [])] if args.include_child_relationships else []
    return DescribeOut(**_summary(raw).model_dump(), field_count=len(fields), fields=fields, record_types=record_types, child_relationships=children)


# --- salesforce.sobject.get_metadata -------------------------------------------------------------

class SObjectTypeIn(BaseModel):
    sobject_type: str = Field(**SOBJECT_TYPE_KW)


class RecentItem(BaseModel):
    id: str = Field(description="Salesforce id of the record the user viewed or changed recently")
    name: Optional[str] = Field(default=None, description="Name of that record, when the object has a name field")


class MetadataOut(BaseModel):
    object_info: ObjectSummary = Field(description="Basic information about the object: API name, labels, id prefix and capabilities")
    recent_items: list[RecentItem] = Field(description="Records of this object that the connected user viewed or changed recently, most recent first")


@function(
    id="salesforce.sobject.get_metadata", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the basic information of one Salesforce object (sObject): API name, label, id prefix and what the connected user can do with it, together "
        "with the records of that object the user viewed or changed most recently (id and name). Use it when the user asks for a quick overview of an "
        "object or wants to see what they worked on lately in Accounts, Contacts or any other object. It is lighter than a full description and returns "
        "no fields. Read-only. It fails with not_found when the object does not exist. For the fields use salesforce.sobject.describe."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account"}, "output": {
        "object_info": {"name": "Account", "label": "Account", "label_plural": "Accounts", "key_prefix": "001", "custom": False, "queryable": True,
                        "searchable": True, "createable": True, "updateable": True, "deletable": True},
        "recent_items": [{"id": "001fj00000WTSTKAA5", "name": "Acme Corp"}]}}],
)
async def sobject_get_metadata(ctx: Context, args: SObjectTypeIn) -> MetadataOut:
    raw = await get_json(ctx, f"/sobjects/{args.sobject_type}")
    return MetadataOut(object_info=_summary(raw["objectDescribe"]),
                       recent_items=[RecentItem(id=r["Id"], name=r.get("Name")) for r in raw.get("recentItems", []) if r.get("Id")])


# --- salesforce.sobject.list_by_type -------------------------------------------------------------

class ListByTypeIn(BaseModel):
    sobject_type: str = Field(**SOBJECT_TYPE_KW)
    fields: Optional[list[str]] = Field(**FIELDS_KW)
    limit: int = Field(default=50, ge=1, le=200, description="How many records to return, from 1 to 200 (default 50)")
    offset: int = Field(default=0, ge=0, le=MAX_OFFSET, description="How many records to skip, from 0 to 2000; use the next_offset value of a previous result to continue")

    @model_validator(mode="after")
    def _fields_ok(self):
        _check_fields(self.fields)
        return self


class RecordsPageOut(BaseModel):
    records: list[dict[str, Any]] = Field(description="The records returned in this page, newest first, each with the requested fields by their Salesforce API name")
    has_more: bool = Field(description="True when there are more records than were returned and a next page can be requested")
    next_offset: Optional[int] = Field(default=None, description="Offset to pass as input to get the next page; empty when there is no next page or Salesforce cannot skip that far")


@function(
    id="salesforce.sobject.list_by_type", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the records of any Salesforce object by its API name, standard or custom (for example 'Product2', 'Invoice__c'), newest first, returning the "
        "requested fields by their Salesforce API name. Use it when the user wants to browse an object that has no dedicated function. If no fields are "
        "given it returns the id and the name field of the object. It returns up to 200 records per call; when has_more is true call it again with "
        "next_offset (Salesforce can skip at most 2000 records). Read-only. For Account, Contact, Lead, Opportunity, Case and Task prefer their own "
        "functions, and for custom filters use salesforce.soql.query."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Product2", "fields": ["Id", "Name"], "limit": 1}, "output": {
        "records": [{"Id": "01tfj00000AbCdEAAZ", "Name": "Generator 5kW"}], "has_more": False}}],
)
async def sobject_list_by_type(ctx: Context, args: ListByTypeIn) -> RecordsPageOut:
    fields = args.fields
    if not fields:  # sin campos: Id y el campo que Salesforce marca como nombre del objeto (no todos tienen Name)
        info = await get_json(ctx, f"/sobjects/{args.sobject_type}/describe")
        name_field = next((f["name"] for f in info.get("fields", []) if f.get("nameField")), None)
        fields = ["Id"] + ([name_field] if name_field and name_field != "Id" else [])
    soql = f"SELECT {','.join(fields)} FROM {args.sobject_type} ORDER BY CreatedDate DESC LIMIT {args.limit + 1} OFFSET {args.offset}"
    rows = (await get_json(ctx, "/query", params={"q": soql})).get("records", [])
    nxt = args.offset + args.limit
    has_more = len(rows) > args.limit
    return RecordsPageOut(records=[clean_record(r) for r in rows[:args.limit]], has_more=has_more, next_offset=nxt if has_more and nxt <= MAX_OFFSET else None)


# --- salesforce.sobject.get_by_type --------------------------------------------------------------

class RecordOut(BaseModel):
    id: str = Field(description="Salesforce id of the record")
    record: dict[str, Any] = Field(description="The record with its fields by their Salesforce API name (all fields unless a list was requested)")


class GetByTypeIn(BaseModel):
    sobject_type: str = Field(**SOBJECT_TYPE_KW)
    record_id: str = Field(pattern=ID_PATTERN, description="Salesforce id of the record, 15 or 18 letters and digits, for example '001fj00000WTSTKAA5'")
    fields: Optional[list[str]] = Field(**FIELDS_KW)

    @model_validator(mode="after")
    def _fields_ok(self):
        _check_fields(self.fields)
        return self


def _record_out(raw: Any) -> RecordOut:
    if isinstance(raw, list):  # 300 Multiple Choices: varios registros coinciden con la clave externa
        raise FunctionError(ErrorCode.invalid_input, "More than one record has that external id value; use a more specific value or query with SOQL.")
    rec = clean_record(raw)
    return RecordOut(id=str(rec.get("Id", "")), record=rec)


@function(
    id="salesforce.sobject.get_by_type", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns one record of any Salesforce object given the object API name and the record id, with all its fields or only the fields requested (by "
        "their Salesforce API name). Use it when the user asks for the details of a record of an object that has no dedicated function, such as a "
        "product, a contract or a custom object, or when they need fields that the dedicated get functions do not return. Read-only: it does not change "
        "the record. It fails with not_found when the id does not exist or is not visible to the connected user. To find ids use "
        "salesforce.sobject.list_by_type or salesforce.soql.query."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account", "record_id": "001fj00000WTSTKAA5", "fields": ["Id", "Name"]}, "output": {
        "id": "001fj00000WTSTKAA5", "record": {"Id": "001fj00000WTSTKAA5", "Name": "Acme Corp"}}}],
)
async def sobject_get_by_type(ctx: Context, args: GetByTypeIn) -> RecordOut:
    raw = await get_json(ctx, f"/sobjects/{args.sobject_type}/{args.record_id}", params={"fields": ",".join(args.fields)} if args.fields else None)
    return _record_out(raw)


# --- salesforce.sobject.get_by_external_id -------------------------------------------------------

class GetByExternalIdIn(BaseModel):
    sobject_type: str = Field(**SOBJECT_TYPE_KW)
    external_id_field: str = Field(pattern=SOBJECT_PATTERN, description="API name of the field that holds the external id, for example 'Legacy_Id__c'; 'Id' is also accepted")
    external_id_value: str = Field(min_length=1, max_length=255, description="Value of the external id to look for, exactly as stored in Salesforce, for example 'CUST-0042'")
    fields: Optional[list[str]] = Field(**FIELDS_KW)

    @model_validator(mode="after")
    def _fields_ok(self):
        _check_fields(self.fields)
        return self


@function(
    id="salesforce.sobject.get_by_external_id", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns one record of any Salesforce object by the value of an external id field, which is a field that stores the id the record has in another "
        "system, for example a customer number. Give the object API name, the API name of the external id field and the value. Use it when the user has "
        "an id from another system and wants the matching Salesforce record. Read-only. It fails with not_found when no record has that value or when the "
        "field is not an external id, and with invalid_input when several records share the value. To see which fields are external ids use "
        "salesforce.sobject.describe."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account", "external_id_field": "Legacy_Id__c", "external_id_value": "CUST-0042", "fields": ["Id", "Name"]}, "output": {
        "id": "001fj00000WTSTKAA5", "record": {"Id": "001fj00000WTSTKAA5", "Name": "Acme Corp"}}}],
)
async def sobject_get_by_external_id(ctx: Context, args: GetByExternalIdIn) -> RecordOut:
    path = f"/sobjects/{args.sobject_type}/{args.external_id_field}/{quote(args.external_id_value, safe='')}"
    raw = await get_json(ctx, path, params={"fields": ",".join(args.fields)} if args.fields else None)
    return _record_out(raw)


# --- salesforce.sobject.get_deleted / get_updated ------------------------------------------------

def _utc(value: datetime) -> str:
    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class ChangesIn(BaseModel):
    sobject_type: str = Field(**SOBJECT_TYPE_KW)
    start: datetime = Field(description="Start of the period, in ISO 8601 UTC, for example '2026-10-01T00:00:00Z'; Salesforce only accepts dates from the last 30 days")
    end: Optional[datetime] = Field(default=None, description="End of the period, in ISO 8601 UTC; defaults to now when omitted")

    @model_validator(mode="after")
    def _ordered(self):
        if self.end is not None and _utc(self.end) <= _utc(self.start):
            raise ValueError("end must be later than start")
        return self


def _period(args: ChangesIn) -> dict[str, str]:
    return {"start": _utc(args.start), "end": _utc(args.end or datetime.now(timezone.utc))}


class DeletedRecord(BaseModel):
    id: str = Field(description="Salesforce id of the record that was deleted")
    deleted_date: Optional[str] = Field(default=None, description="Date and time when the record was deleted, in ISO 8601 format")


class DeletedOut(BaseModel):
    deleted_records: list[DeletedRecord] = Field(description="Records of the object deleted during the period")
    earliest_date_available: Optional[str] = Field(default=None, description="Oldest date for which Salesforce still keeps deletion information, in ISO 8601 format")
    latest_date_covered: Optional[str] = Field(default=None, description="Latest date Salesforce could cover with this answer, in ISO 8601 format; use it as the next start")


@function(
    id="salesforce.sobject.get_deleted", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the ids of the records of one Salesforce object that were deleted during a period, with the date each was deleted. Give the object API name "
        "and the start of the period; the end defaults to now. Use it when the user asks what was deleted recently in Accounts, Contacts or another object, "
        "or to keep another system in sync. Salesforce only looks back 30 days, so an older start fails with invalid_input. Read-only: it does not restore "
        "or delete anything. Records are returned as ids only; the deleted data is not available. For changed records use salesforce.sobject.get_updated."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account", "start": "2026-10-01T00:00:00Z"}, "output": {
        "deleted_records": [{"id": "001fj00000WTSTKAA5", "deleted_date": "2026-10-03T10:15:00.000+0000"}],
        "earliest_date_available": "2025-12-16T15:01:00.000+0000", "latest_date_covered": "2026-10-09T00:48:00.000+0000"}}],
)
async def sobject_get_deleted(ctx: Context, args: ChangesIn) -> DeletedOut:
    raw = await get_json(ctx, f"/sobjects/{args.sobject_type}/deleted", params=_period(args))
    return DeletedOut(deleted_records=[DeletedRecord(id=r["id"], deleted_date=r.get("deletedDate")) for r in raw.get("deletedRecords", [])],
                      earliest_date_available=raw.get("earliestDateAvailable"), latest_date_covered=raw.get("latestDateCovered"))


class UpdatedOut(BaseModel):
    ids: list[str] = Field(description="Ids of the records of the object created or changed during the period")
    latest_date_covered: Optional[str] = Field(default=None, description="Latest date Salesforce could cover with this answer, in ISO 8601 format; use it as the next start")


@function(
    id="salesforce.sobject.get_updated", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the ids of the records of one Salesforce object that were created or changed during a period. Give the object API name and the start of the "
        "period; the end defaults to now. Use it when the user asks what changed recently in Accounts, Contacts or another object, or to keep another "
        "system in sync, then read the records with salesforce.sobject.get_by_type. Salesforce only looks back 30 days, so an older start fails with "
        "invalid_input. Read-only: it returns ids only and does not change anything. For deleted records use salesforce.sobject.get_deleted."
    ),
    examples=[{"name": "default", "input": {"sobject_type": "Account", "start": "2026-10-01T00:00:00Z"}, "output": {
        "ids": ["001fj00000WTSTKAA5"], "latest_date_covered": "2026-10-09T00:48:00.000+0000"}}],
)
async def sobject_get_updated(ctx: Context, args: ChangesIn) -> UpdatedOut:
    raw = await get_json(ctx, f"/sobjects/{args.sobject_type}/updated", params=_period(args))
    return UpdatedOut(ids=list(raw.get("ids", [])), latest_date_covered=raw.get("latestDateCovered"))
