"""Funciones de lectura de HubSpot (API con version por fecha 2026-09).

Verificado en developers.hubspot.com (2026-10-07):
- GET /account-info/2026-09/details: solo pide el scope `oauth`; devuelve portalId (Hub ID), accountType, timeZone, companyCurrency,
  uiDomain, dataHostingLocation y, opcional, portalName. (El catalogo decia `crm.objects.read`, que no existe.)
- POST /crm/objects/2026-09/{objeto}/search: filterGroups (max 5 grupos, 6 filtros por grupo, 18 en total), query, sorts (uno),
  properties, limit (max 200) y after; responde {total, results, paging.next.after}; no pasa de 10,000 resultados por consulta.
- POST /crm/objects/2026-09/{objeto}/batch/read: inputs (max 100), properties (obligatorio) e idProperty (solo si no son record ids);
  responde 200, o 207 con `errors` (OBJECT_NOT_FOUND con los ids en context.ids) si alguno no existe.
POR COMPROBAR en una prueba real: el 207 con ids inexistentes y que portalName llegue en cuentas normales.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente los usa para buscar la funcion
y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.functions.apps.hubspot.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

BASE_URL = "https://api.hubapi.com"
CRM_URL = f"{BASE_URL}/crm/objects/2026-09"
API = "2026-09"

# batch/read exige `properties`; si el usuario no pide ninguna se mandan estas (las mismas que la busqueda devuelve por defecto, y algo mas).
DEFAULT_PROPERTIES = {
    "contacts": ["firstname", "lastname", "email", "phone", "company", "lifecyclestage", "createdate", "lastmodifieddate"],
    "companies": ["name", "domain", "industry", "phone", "city", "country", "createdate", "hs_lastmodifieddate"],
}


# --- hubspot.account.get (whoami) ----------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class Account(BaseModel):
    account_id: str = Field(description="HubSpot account id (portal id or Hub ID), the same value stored when the account was connected")
    display_name: str = Field(description="Account name if HubSpot provides it, otherwise 'HubSpot <portal id>'")
    account_type: Optional[str] = Field(default=None, description="STANDARD, DEVELOPER_TEST, SANDBOX or APP_DEVELOPER")
    time_zone: Optional[str] = Field(default=None, description="Time zone configured in the account, for example 'US/Eastern'")
    currency: Optional[str] = Field(default=None, description="Main currency code of the account, for example 'USD'")
    ui_domain: Optional[str] = Field(default=None, description="Domain used to open the HubSpot user interface, for example 'app.hubspot.com'")
    data_hosting_location: Optional[str] = Field(default=None, description="Data center that hosts the account, for example 'na1' or 'eu1'")


@function(
    id="hubspot.account.get", version=1, verb=Verb.read, upstream_api=API, scopes=["oauth"],
    description=(
        "Returns the HubSpot account that is connected for the user: the account id (portal id, also called Hub ID), the account name when available, the "
        "account type (standard, sandbox, developer test), the configured time zone and currency, the user interface domain and the data hosting location. "
        "Use it to confirm which HubSpot account is being used, to answer questions such as 'which HubSpot do I have connected?', or to check that the "
        "connection still works before reading CRM records. Read-only: it takes no parameters and does not change anything in HubSpot. If the user has "
        "several HubSpot accounts connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "123456", "display_name": "Empresa Demo", "account_type": "STANDARD", "time_zone": "US/Eastern", "currency": "USD",
        "ui_domain": "app.hubspot.com", "data_hosting_location": "na1"}}],
)
async def account_get(ctx: Context, args: NoArgs) -> Account:
    body = (await ctx.conn.request("GET", f"{BASE_URL}/account-info/{API}/details")).json()
    portal_id = str(body["portalId"])
    return Account(account_id=portal_id, display_name=body.get("portalName") or f"HubSpot {portal_id}", account_type=body.get("accountType"),
                   time_zone=body.get("timeZone"), currency=body.get("companyCurrency"), ui_domain=body.get("uiDomain"),
                   data_hosting_location=body.get("dataHostingLocation"))


# --- registros del CRM (compartido) --------------------------------------------------------------

class Record(BaseModel):
    id: str = Field(description="HubSpot record id, usable to read the record again or in later steps")
    properties: dict[str, Optional[str]] = Field(description="Property values of the record by internal property name; HubSpot sends every value as text")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the record was created")
    updated_at: Optional[str] = Field(default=None, description="UTC date and time of the last change to the record")
    archived: bool = Field(default=False, description="True if the record is archived (deleted) in HubSpot")


def _record(raw: dict[str, Any]) -> Record:
    return Record(id=str(raw["id"]), properties=raw.get("properties") or {}, created_at=raw.get("createdAt"),
                  updated_at=raw.get("updatedAt"), archived=bool(raw.get("archived")))


# --- busqueda (compartido) -----------------------------------------------------------------------

Operator = Literal["EQ", "NEQ", "LT", "LTE", "GT", "GTE", "BETWEEN", "IN", "NOT_IN",
                   "HAS_PROPERTY", "NOT_HAS_PROPERTY", "CONTAINS_TOKEN", "NOT_CONTAINS_TOKEN"]
_NO_VALUE = {"HAS_PROPERTY", "NOT_HAS_PROPERTY"}
_LIST_VALUE = {"IN", "NOT_IN"}
MAX_FILTERS = 18


class Filter(BaseModel):
    property_name: str = Field(min_length=1, description="Internal name of the property to compare, for example 'email', 'lifecyclestage' or 'createdate'")
    operator: Operator = Field(description=(
        "Comparison: EQ, NEQ, LT, LTE, GT, GTE, BETWEEN (needs value and high_value), IN and NOT_IN (need values), HAS_PROPERTY and "
        "NOT_HAS_PROPERTY (no value), CONTAINS_TOKEN and NOT_CONTAINS_TOKEN (word match, '*' works as a wildcard)"))
    value: Optional[str] = Field(default=None, description="Value to compare with; dates go as Unix milliseconds or ISO 8601. Required except for IN, NOT_IN, HAS_PROPERTY and NOT_HAS_PROPERTY")
    high_value: Optional[str] = Field(default=None, description="Upper limit, only for BETWEEN; value is then the lower limit")
    values: list[str] = Field(default_factory=list, description="Values to match exactly, only for IN and NOT_IN; text values in lowercase")

    @model_validator(mode="after")
    def _values_fit_operator(self) -> "Filter":
        if self.operator in _LIST_VALUE and not self.values:
            raise ValueError(f"{self.operator} needs values")
        if self.operator == "BETWEEN" and (self.value is None or self.high_value is None):
            raise ValueError("BETWEEN needs value and high_value")
        if self.operator not in _NO_VALUE | _LIST_VALUE and self.value is None:
            raise ValueError(f"{self.operator} needs value")
        return self


class FilterGroup(BaseModel):
    filters: list[Filter] = Field(min_length=1, max_length=6, description="Conditions that must all be true (AND) for a record to match this group, up to 6")


class SearchIn(BaseModel):
    query: Optional[str] = Field(default=None, max_length=3000, description="Free text looked up in the default searchable properties of the object; leave empty to rely only on filters")
    filter_groups: list[FilterGroup] = Field(default_factory=list, max_length=5, description=(
        "Groups of filters combined with OR: a record matches if it satisfies any group. Up to 5 groups and 18 filters in total; leave empty to not filter"))
    properties: list[str] = Field(default_factory=list, max_length=200, description="Internal names of the properties to return for each record; leave empty for the default ones")
    sort_by: Optional[str] = Field(default=None, description="Internal name of one property to sort by, for example 'createdate'; leave empty for creation order (oldest first)")
    sort_direction: Literal["ASCENDING", "DESCENDING"] = Field(default="DESCENDING", description="Sort order used with sort_by: DESCENDING (default) or ASCENDING")
    limit: int = Field(default=10, ge=1, le=200, description="How many records to return in this page, from 1 to 200 (default 10)")
    after: Optional[str] = Field(default=None, description="Paging cursor returned as next_after by a previous call; leave empty for the first page")

    @model_validator(mode="after")
    def _filters_within_limit(self) -> "SearchIn":
        if sum(len(g.filters) for g in self.filter_groups) > MAX_FILTERS:
            raise ValueError(f"at most {MAX_FILTERS} filters in total")
        return self


class SearchOut(BaseModel):
    total: int = Field(description="Total number of records that match, not only the ones in this page")
    results: list[Record] = Field(description="Records of this page")
    next_after: Optional[str] = Field(default=None, description="Cursor for the next page; empty when there are no more results")


def _filter(f: Filter) -> dict[str, Any]:
    out: dict[str, Any] = {"propertyName": f.property_name, "operator": f.operator}
    if f.value is not None:
        out["value"] = f.value
    if f.high_value is not None:
        out["highValue"] = f.high_value
    if f.values:
        out["values"] = f.values
    return out


async def _search(ctx: Context, object_type: str, args: SearchIn) -> SearchOut:
    body: dict[str, Any] = {"limit": args.limit}
    if args.query:
        body["query"] = args.query
    if args.filter_groups:
        body["filterGroups"] = [{"filters": [_filter(f) for f in g.filters]} for g in args.filter_groups]
    if args.properties:
        body["properties"] = args.properties
    if args.sort_by:
        body["sorts"] = [{"propertyName": args.sort_by, "direction": args.sort_direction}]
    if args.after:
        body["after"] = args.after
    data = (await ctx.conn.request("POST", f"{CRM_URL}/{object_type}/search", json=body)).json()
    return SearchOut(total=int(data.get("total", 0)), results=[_record(r) for r in data.get("results", [])],
                     next_after=((data.get("paging") or {}).get("next") or {}).get("after"))


# --- lectura por lotes (compartido) --------------------------------------------------------------

class BatchReadIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100, description="Ids of the records to read, from 1 to 100; record ids unless id_property is set")
    properties: list[str] = Field(default_factory=list, max_length=200, description="Internal names of the properties to return for each record; leave empty for a useful default set")
    id_property: Optional[str] = Field(default=None, description="Leave empty when ids are HubSpot record ids; otherwise the unique property the ids refer to, such as 'email' for contacts")


class BatchReadOut(BaseModel):
    results: list[Record] = Field(description="Records that were found, in no guaranteed order")
    not_found: list[str] = Field(default_factory=list, description="Requested ids that HubSpot could not find")


async def _batch_read(ctx: Context, object_type: str, args: BatchReadIn) -> BatchReadOut:
    body: dict[str, Any] = {"inputs": [{"id": i} for i in args.ids], "properties": args.properties or DEFAULT_PROPERTIES[object_type]}
    if args.id_property:
        body["idProperty"] = args.id_property
    data = (await ctx.conn.request("POST", f"{CRM_URL}/{object_type}/batch/read", json=body)).json()  # 207 = algunos no existen
    missing = [str(i) for e in data.get("errors", []) for i in ((e.get("context") or {}).get("ids") or [])]
    return BatchReadOut(results=[_record(r) for r in data.get("results", [])], not_found=missing)


_CONTACT = {"id": "151", "properties": {"email": "ana@empresa.test", "firstname": "Ana", "lastname": "Perez"},
            "created_at": "2026-01-02T10:00:00Z", "updated_at": "2026-03-01T09:00:00Z", "archived": False}
_COMPANY = {"id": "901", "properties": {"name": "Empresa Demo", "domain": "empresa.test", "industry": "COMPUTER_SOFTWARE"},
            "created_at": "2026-01-02T10:00:00Z", "updated_at": "2026-03-01T09:00:00Z", "archived": False}
_DEAL = {"id": "3301", "properties": {"dealname": "Licencia anual", "amount": "1200", "dealstage": "contractsent", "pipeline": "default"},
         "created_at": "2026-02-01T10:00:00Z", "updated_at": "2026-03-01T09:00:00Z", "archived": False}


# --- hubspot.contacts.search ---------------------------------------------------------------------

@function(
    id="hubspot.contacts.search", version=1, verb=Verb.read, upstream_api=API, scopes=["crm.objects.contacts.read"],
    description=(
        "Searches the contacts of the connected HubSpot CRM by free text and/or by property filters, with sorting and cursor pagination. The free text "
        "looks in first name, last name, email, phone, mobile phone and company; filters compare any contact property (for example email equals a value, "
        "lifecyclestage is customer, createdate after a date). Each result has the contact id, the requested properties (by default first name, last "
        "name and email), and its creation and update dates; the reply also gives the total number of matches. Use it when the user asks to find a "
        "contact by name, email or phone, or to list contacts that meet some conditions. Up to 200 records per page and 10,000 per query; pass next_after "
        "to read the next page. Read-only. To read contacts whose ids are already known use hubspot.contacts.batch_read."
    ),
    examples=[{"name": "default", "input": {"query": "ana@empresa.test", "limit": 5},
               "output": {"total": 1, "results": [_CONTACT], "next_after": None}}],
)
async def contacts_search(ctx: Context, args: SearchIn) -> SearchOut:
    return await _search(ctx, "contacts", args)


# --- hubspot.contacts.batch_read -----------------------------------------------------------------

@function(
    id="hubspot.contacts.batch_read", version=1, verb=Verb.read, upstream_api=API, scopes=["crm.objects.contacts.read"],
    description=(
        "Reads up to 100 HubSpot contacts in one call from their record ids, or from their email addresses when id_property is set to 'email'. Each "
        "result has the contact id, the requested properties (by default name, email, phone, company, lifecycle stage and dates) and its creation and "
        "update dates; ids that do not exist are listed in not_found instead of failing the whole call. Use it when contact ids are already known, for "
        "example from a search, an association or a previous step, and their details are needed. Read-only. It does not search by text or filters (use "
        "hubspot.contacts.search) and it does not return associations."
    ),
    examples=[{"name": "default", "input": {"ids": ["151", "999"], "properties": ["email", "firstname", "lastname"]},
               "output": {"results": [_CONTACT], "not_found": ["999"]}}],
)
async def contacts_batch_read(ctx: Context, args: BatchReadIn) -> BatchReadOut:
    return await _batch_read(ctx, "contacts", args)


# --- hubspot.companies.search --------------------------------------------------------------------

@function(
    id="hubspot.companies.search", version=1, verb=Verb.read, upstream_api=API, scopes=["crm.objects.companies.read"],
    description=(
        "Searches the companies of the connected HubSpot CRM by free text and/or by property filters, with sorting and cursor pagination. The free text "
        "looks in the company name, domain, website and phone; filters compare any company property (for example industry, city, annualrevenue greater "
        "than a value, createdate after a date). Each result has the company id, the requested properties (by default name and domain) and its creation "
        "and update dates; the reply also gives the total number of matches. Use it when the user asks to find a company or organization by name or "
        "domain, or to list companies that meet some conditions. Up to 200 records per page and 10,000 per query; pass next_after to read the next page. "
        "Read-only. To read companies whose ids are already known use hubspot.companies.batch_read."
    ),
    examples=[{"name": "default", "input": {"query": "empresa.test"}, "output": {"total": 1, "results": [_COMPANY], "next_after": None}}],
)
async def companies_search(ctx: Context, args: SearchIn) -> SearchOut:
    return await _search(ctx, "companies", args)


# --- hubspot.companies.batch_read ----------------------------------------------------------------

@function(
    id="hubspot.companies.batch_read", version=1, verb=Verb.read, upstream_api=API, scopes=["crm.objects.companies.read"],
    description=(
        "Reads up to 100 HubSpot companies in one call from their record ids, or from a custom unique property when id_property is set. Each result has "
        "the company id, the requested properties (by default name, domain, industry, phone, city, country and dates) and its creation and update dates; "
        "ids that do not exist are listed in not_found instead of failing the whole call. Use it when company ids are already known, for example from a "
        "search, an association or a previous step, and their details are needed. Read-only. It does not search by text or filters (use "
        "hubspot.companies.search) and it does not return associations."
    ),
    examples=[{"name": "default", "input": {"ids": ["901"]}, "output": {"results": [_COMPANY], "not_found": []}}],
)
async def companies_batch_read(ctx: Context, args: BatchReadIn) -> BatchReadOut:
    return await _batch_read(ctx, "companies", args)


# --- hubspot.deals.search ------------------------------------------------------------------------

@function(
    id="hubspot.deals.search", version=1, verb=Verb.read, upstream_api=API, scopes=["crm.objects.deals.read"],
    description=(
        "Searches the deals (sales opportunities) of the connected HubSpot CRM by free text and/or by property filters, with sorting and cursor "
        "pagination. The free text looks in the deal name, pipeline, deal stage, description and deal type; filters compare any deal property (for "
        "example dealstage, amount greater than a value, closedate between two dates, hubspot_owner_id). Each result has the deal id, the requested "
        "properties (by default name, amount, close date, pipeline and stage) and its creation and update dates; the reply also gives the total number "
        "of matches. Use it when the user asks about open or won deals, deals in a stage, deals closing this month or the biggest deals. Up to 200 records "
        "per page and 10,000 per query; pass next_after to read the next page. Read-only: it does not create or change deals."
    ),
    examples=[{"name": "default", "input": {
        "filter_groups": [{"filters": [{"property_name": "dealstage", "operator": "EQ", "value": "contractsent"}]}],
        "sort_by": "amount", "limit": 5}, "output": {"total": 1, "results": [_DEAL], "next_after": None}}],
)
async def deals_search(ctx: Context, args: SearchIn) -> SearchOut:
    return await _search(ctx, "deals", args)
