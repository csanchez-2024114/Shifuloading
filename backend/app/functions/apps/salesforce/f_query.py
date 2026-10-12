"""Consultas de Salesforce: SOQL (query, query_more, query_all) y busquedas de texto SOSL (search, search_parameterized).

Verificado con la API real (2026-10-09), v62.0:
- GET /query?q=SELECT...        -> {totalSize, done, records[{attributes, ...}], nextRecordsUrl}; `nextRecordsUrl` es /services/data/v62.0/query/{localizador}.
  `Sforce-Query-Options: batchSize=N` (200 a 2000) cambia cuantos registros llegan por pagina. Los agregados (COUNT(), GROUP BY) devuelven
  `records` con tipo AggregateResult y `COUNT()` solo trae `totalSize`.
- GET /queryAll?q=...           -> igual que query pero incluye registros eliminados y archivados (IsDeleted = true).
- GET /search?q=FIND {...} ...  -> {searchRecords[{attributes, Id, ...}]}.
- GET /parameterizedSearch?q=texto&sobject=Account&Account.fields=Id,Name&Account.limit=5&Account.where=...&in=NAME -> {searchRecords[...]}.
  El catalogo decia que recibe `searchType`/`fields`/`where` sueltos: la API los pide con el prefijo del objeto (`Account.fields`).
Salesforce no deja escribir con estos endpoints (SOQL y SOSL son de solo lectura). Todas piden el permiso `api`.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito.
"""
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.salesforce._common import FIELD_PATTERN, SOBJECT_PATTERN, UPSTREAM_API, clean_record, get_json, locator_of
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

LOCATOR_PATTERN = r"^[A-Za-z0-9]{15,18}-\d{1,9}$"


class QueryOut(BaseModel):
    records: list[dict[str, Any]] = Field(description="The records of this page; each has the fields named in the query by their Salesforce API name (empty for COUNT() queries)")
    total_size: int = Field(description="Total number of records the query matches across all pages; for COUNT() queries, the count itself")
    done: bool = Field(description="True when this page is the last one; false when more records remain and query_locator can be used to fetch them")
    query_locator: Optional[str] = Field(default=None, description="Locator to pass to salesforce.soql.query_more to get the next page; empty when done is true")


def _query_out(body: dict[str, Any]) -> QueryOut:
    return QueryOut(records=[clean_record(r) for r in body.get("records", [])], total_size=int(body.get("totalSize", 0)),
                    done=bool(body.get("done", True)), query_locator=locator_of(body.get("nextRecordsUrl")))


SOQL_KW = dict(min_length=7, max_length=20000, description="The SOQL statement to run, a SELECT query such as \"SELECT Id, Name FROM Account WHERE Industry = 'Energy' LIMIT 10\"")
BATCH_KW = dict(default=200, ge=200, le=2000, description="How many records Salesforce sends per page, from 200 to 2000 (default 200); more pages are fetched with query_more")


class SoqlIn(BaseModel):
    soql_query: str = Field(**SOQL_KW)
    batch_size: int = Field(**BATCH_KW)


def _batch(args: SoqlIn) -> dict[str, str]:
    return {"Sforce-Query-Options": f"batchSize={args.batch_size}"}


# --- salesforce.soql.query -----------------------------------------------------------------------

@function(
    id="salesforce.soql.query", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Runs a SOQL query (Salesforce Object Query Language, a SELECT statement) against the connected Salesforce org and returns the matching records with "
        "the fields named in the query, the total number of matches, and a locator to fetch the next page when the result is large. Use it for any question "
        "the dedicated functions cannot answer: custom filters, joins to related objects (SELECT Account.Name FROM Contact), counts (SELECT COUNT() FROM "
        "Lead) or groupings. It returns up to batch_size records per page (200 by default). Read-only: SOQL cannot create, change or delete data, and "
        "records in the recycle bin are not included. A malformed query fails with invalid_input and Salesforce's message. For the next page use "
        "salesforce.soql.query_more, and to include deleted records use salesforce.soql.query_all."
    ),
    examples=[{"name": "default", "input": {"soql_query": "SELECT Id, Name FROM Account LIMIT 2"}, "output": {
        "records": [{"Id": "001fj00000WTSTKAA5", "Name": "Acme Corp"}, {"Id": "001fj00000WTSTJAA5", "Name": "sForce"}], "total_size": 2, "done": True}}],
)
async def soql_query(ctx: Context, args: SoqlIn) -> QueryOut:
    return _query_out(await get_json(ctx, "/query", params={"q": args.soql_query}, headers=_batch(args)))


# --- salesforce.soql.query_more ------------------------------------------------------------------

class QueryMoreIn(BaseModel):
    query_locator: str = Field(pattern=LOCATOR_PATTERN, description="Locator returned as query_locator by a previous salesforce.soql.query, query_more or query_all call, for example '01gfj00000AbCdEAAZ-2000'")


@function(
    id="salesforce.soql.query_more", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Fetches the next page of a SOQL query that returned more records than fit in one page. Give the query_locator that salesforce.soql.query (or "
        "query_all) returned when done was false; the result has the same shape (a page can hold up to 2000 records) and carries a new query_locator until the last page, where done is true. "
        "Use it when the user wants to continue reading a large result. The locator belongs to the user who ran the query and expires after some time "
        "(about 15 minutes of inactivity), after which Salesforce answers with invalid_input or not_found and the query must be run again. Read-only. To "
        "start a query use salesforce.soql.query."
    ),
    examples=[{"name": "default", "input": {"query_locator": "01gfj00000AbCdEAAZ-200"}, "output": {
        "records": [{"Id": "001fj00000WTSTKAA5", "Name": "Acme Corp"}], "total_size": 201, "done": True}}],
)
async def soql_query_more(ctx: Context, args: QueryMoreIn) -> QueryOut:
    return _query_out(await get_json(ctx, f"/query/{args.query_locator}"))


# --- salesforce.soql.query_all -------------------------------------------------------------------

@function(
    id="salesforce.soql.query_all", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Runs a SOQL query like salesforce.soql.query but also includes records that were deleted (in the recycle bin) and archived activities, so a "
        "WHERE IsDeleted = true filter can find them. Use it when the user asks about deleted or archived records, for example 'which accounts did we "
        "delete last week?'. It returns the matching records with the fields named in the query, the total number of matches and a locator for the next "
        "page, up to batch_size records per page (200 by default). Read-only: it does not restore or remove anything. For ordinary queries prefer "
        "salesforce.soql.query, and for the next page use salesforce.soql.query_more."
    ),
    examples=[{"name": "default", "input": {"soql_query": "SELECT Id, Name FROM Account WHERE IsDeleted = true"}, "output": {
        "records": [{"Id": "001fj00000WTSTKAA5", "Name": "Old Corp"}], "total_size": 1, "done": True}}],
)
async def soql_query_all(ctx: Context, args: SoqlIn) -> QueryOut:
    return _query_out(await get_json(ctx, "/queryAll", params={"q": args.soql_query}, headers=_batch(args)))


# --- salesforce.sosl.search ----------------------------------------------------------------------

class SearchRecordsOut(BaseModel):
    records: list[dict[str, Any]] = Field(description="The matching records; each has 'sobject_type' (the object it belongs to) and the fields requested for that object (at least 'Id')")


def _search_out(body: dict[str, Any]) -> SearchRecordsOut:
    out = []
    for r in body.get("searchRecords", []):
        out.append({"sobject_type": (r.get("attributes") or {}).get("type"), **clean_record(r)})
    return SearchRecordsOut(records=out)


class SoslIn(BaseModel):
    sosl_query: str = Field(min_length=7, max_length=20000, description="The SOSL statement to run, such as \"FIND {acme} IN ALL FIELDS RETURNING Account(Id, Name), Contact(Id, LastName)\"")

    @model_validator(mode="after")
    def _starts_with_find(self):
        if not re.match(r"^\s*FIND\b", self.sosl_query, re.IGNORECASE):
            raise ValueError("A SOSL query must start with FIND, for example: FIND {acme} RETURNING Account(Id, Name)")
        return self


@function(
    id="salesforce.sosl.search", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Runs a SOSL text search (Salesforce Object Search Language, a FIND statement) across several objects at once and returns the matching records, each "
        "tagged with its object type and the fields listed in RETURNING (only the id when none are listed). Use it when the user looks for a word, name, "
        "email or phone number without knowing which object holds it, for example 'find acme everywhere'. The statement must start with FIND, such as "
        "FIND {acme} IN ALL FIELDS RETURNING Account(Id, Name), Contact(Id, LastName); Salesforce returns at most 2000 records. Read-only. A malformed "
        "statement fails with invalid_input. To search one object with simple parameters use salesforce.sosl.search_parameterized."
    ),
    examples=[{"name": "default", "input": {"sosl_query": "FIND {sforce} IN ALL FIELDS RETURNING Account(Id, Name)"}, "output": {
        "records": [{"sobject_type": "Account", "Id": "001fj00000WTSTJAA5", "Name": "sForce"}]}}],
)
async def sosl_search(ctx: Context, args: SoslIn) -> SearchRecordsOut:
    return _search_out(await get_json(ctx, "/search", params={"q": args.sosl_query}))


# --- salesforce.sosl.search_parameterized --------------------------------------------------------

class ParameterizedIn(BaseModel):
    search_term: str = Field(min_length=1, max_length=500, description="Text to look for, for example 'acme'; Salesforce matches whole words and word beginnings")
    sobject_type: str = Field(pattern=SOBJECT_PATTERN, description="API name of the single object to search, for example 'Account', 'Contact' or 'Lead'")
    fields: list[str] = Field(default_factory=lambda: ["Id"], min_length=1, max_length=50, description="API names of the fields to return for each record (default only 'Id'), for example ['Id', 'Name']")
    where: Optional[str] = Field(default=None, max_length=1000, description="Optional SOQL condition to narrow the results, without the word WHERE, for example \"Industry = 'Energy'\"")
    search_in: Optional[Literal["ALL", "NAME", "EMAIL", "PHONE", "SIDEBAR"]] = Field(default=None, description="Which kind of fields to search: ALL, NAME, EMAIL, PHONE or SIDEBAR; leave empty to let Salesforce decide")
    limit: int = Field(default=25, ge=1, le=200, description="Maximum number of records to return, from 1 to 200 (default 25)")

    @model_validator(mode="after")
    def _fields_ok(self):
        for f in self.fields:
            if not re.match(FIELD_PATTERN, f):
                raise ValueError(f"'{f}' is not a valid field API name")
        return self


@function(
    id="salesforce.sosl.search_parameterized", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Searches the text of one Salesforce object with plain parameters, without writing a SOSL statement: the search term, the object, the fields to "
        "return, an optional condition and which kind of fields to look in (names, emails, phones). Use it for simple requests such as 'find leads called "
        "Bertha' or 'search accounts that mention energy'. It returns up to 200 records, each tagged with its object type and the requested fields. "
        "Read-only. The where condition is a SOQL filter such as Industry = 'Energy'. A wrong field or condition fails with invalid_input. To search "
        "several objects at once use salesforce.sosl.search."
    ),
    examples=[{"name": "default", "input": {"search_term": "sforce", "sobject_type": "Account", "fields": ["Id", "Name"]}, "output": {
        "records": [{"sobject_type": "Account", "Id": "001fj00000WTSTJAA5", "Name": "sForce"}]}}],
)
async def sosl_search_parameterized(ctx: Context, args: ParameterizedIn) -> SearchRecordsOut:
    obj = args.sobject_type
    params = {"q": args.search_term, "sobject": obj, f"{obj}.fields": ",".join(args.fields), f"{obj}.limit": str(args.limit)}
    if args.where:
        params[f"{obj}.where"] = args.where
    if args.search_in:
        params["in"] = args.search_in
    return _search_out(await get_json(ctx, "/parameterizedSearch", params=params))
