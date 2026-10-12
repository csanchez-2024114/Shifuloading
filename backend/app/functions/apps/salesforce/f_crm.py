"""Lecturas de los objetos de CRM de Salesforce: Account, Contact, Lead, Opportunity, Case, Task, Event, Campaign y Note (list, get y search segun el objeto).

Verificado con la API real (2026-10-09). El catalogo se equivocaba en tres cosas y aqui se corrigieron:
- `GET /sobjects/Account` NO lista registros (devuelve la descripcion del objeto y los vistos recientemente). Listar y buscar se hace con SOQL:
  `GET /services/data/v62.0/query?q=SELECT ... FROM Account ORDER BY CreatedDate DESC LIMIT n OFFSET m` (OFFSET maximo 2000).
- `GET /sobjects/Account?Name=...` tampoco existe: la busqueda arma un WHERE con los filtros (texto escapado, ver `_common.soql_str`).
- `GET /sobjects/Account/{id}?fields=...` si devuelve el registro (404 NOT_FOUND si no existe).
Para saber si hay otra pagina se pide `limit + 1` registros. Todas piden el permiso `api`. Task, Event y Campaign no tienen `search` y Note solo tiene `get` (es lo que pide cada sprint); `search`/`list` se apagan con `search: False` / `list: False`.

Cada objeto se declara una vez en OBJECTS y `_register` crea sus modelos Pydantic y registra las funciones, igual que el patron de Asana.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model, model_validator

from app.functions.apps.salesforce._common import ID_PATTERN, UPSTREAM_API, get_json, soql_like, soql_str
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

MAX_LIMIT = 200
MAX_OFFSET = 2000  # tope de OFFSET en SOQL

CREATED = ("CreatedDate", "created_date", str, "Date and time when the record was created, in ISO 8601 format")
MODIFIED = ("LastModifiedDate", "last_modified_date", str, "Date and time of the last change to the record, in ISO 8601 format")
OWNER = ("OwnerId", "owner_id", str, "Salesforce user id of the owner of the record; use salesforce.user.get_by_id to see who it is")

# (campo de Salesforce, nombre de salida, tipo, descripcion en ingles)
OBJECTS: list[dict[str, Any]] = [
    dict(
        key="account", sobject="Account", noun="account", plural="accounts",
        summary="its name, type, industry, phone, website, annual revenue, number of employees, billing and shipping city, state and country, and owner",
        example_search={"name": "acme"},
        fields=[
            ("Id", "id", str, "Salesforce id of the account, usable in get and as account_id filter in other searches"),
            ("Name", "name", str, "Name of the account (the company or organization)"),
            ("Type", "type", str, "Type of account, for example 'Customer - Direct' or 'Prospect'"),
            ("Industry", "industry", str, "Industry the account belongs to, for example 'Technology'"),
            ("Phone", "phone", str, "Main phone number of the account"),
            ("Website", "website", str, "Website address of the account"),
            ("AnnualRevenue", "annual_revenue", float, "Estimated annual revenue of the account, in the currency of the org"),
            ("NumberOfEmployees", "number_of_employees", int, "Number of employees of the account"),
            ("BillingCity", "billing_city", str, "City of the billing address"),
            ("BillingState", "billing_state", str, "State or province of the billing address"),
            ("BillingCountry", "billing_country", str, "Country of the billing address"),
            ("ShippingCity", "shipping_city", str, "City of the shipping address"),
            ("ShippingCountry", "shipping_country", str, "Country of the shipping address"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[
            ("name", "Name", "like", "Text contained in the account name, for example 'acme'; the match ignores upper and lower case"),
            ("phone", "Phone", "like", "Text contained in the account phone number, for example '555'"),
            ("industry", "Industry", "eq", "Exact industry of the account, for example 'Technology'"),
        ],
        example={"id": "001fj00000WTSTKAA5", "name": "Acme Corp", "type": "Customer - Direct", "industry": "Technology", "phone": "(555) 123-4567",
                 "website": "https://acme.test", "annual_revenue": 1500000.0, "number_of_employees": 120, "billing_city": "Guatemala",
                 "billing_state": None, "billing_country": "GT", "shipping_city": None, "shipping_country": None, "owner_id": "005fj000009FPCEAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="contact", sobject="Contact", noun="contact", plural="contacts",
        summary="its first and last name, email, phone, job title, department, account id and owner",
        example_search={"last_name": "perez"},
        fields=[
            ("Id", "id", str, "Salesforce id of the contact"),
            ("FirstName", "first_name", str, "First name of the contact"),
            ("LastName", "last_name", str, "Last name of the contact"),
            ("Email", "email", str, "Email address of the contact"),
            ("Phone", "phone", str, "Phone number of the contact"),
            ("Title", "title", str, "Job title of the contact"),
            ("Department", "department", str, "Department where the contact works"),
            ("AccountId", "account_id", str, "Salesforce id of the account the contact belongs to; use salesforce.account.get to read it"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[
            ("last_name", "LastName", "like", "Text contained in the contact last name, for example 'perez'; the match ignores upper and lower case"),
            ("email", "Email", "eq", "Exact email address of the contact, for example 'ana@empresa.test'"),
            ("account_id", "AccountId", "id", "Salesforce id of the account whose contacts you want, 15 or 18 letters and digits"),
        ],
        example={"id": "003fj00000TZjw1AAD", "first_name": "Ana", "last_name": "Perez", "email": "ana@empresa.test", "phone": "(512) 757-6000",
                 "title": "Procurement Director", "department": "Procurement", "account_id": "001fj00000WTST8AAP", "owner_id": "005fj000009FOJNAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="lead", sobject="Lead", noun="lead", plural="leads",
        summary="its first and last name, email, phone, company, job title, status, rating, source, whether it was converted, and owner",
        example_search={"email": "bertha@fcof.net"},
        fields=[
            ("Id", "id", str, "Salesforce id of the lead"),
            ("FirstName", "first_name", str, "First name of the lead"),
            ("LastName", "last_name", str, "Last name of the lead"),
            ("Email", "email", str, "Email address of the lead"),
            ("Phone", "phone", str, "Phone number of the lead"),
            ("Company", "company", str, "Company the lead works for"),
            ("Title", "title", str, "Job title of the lead"),
            ("Status", "status", str, "Status of the lead in the sales process, for example 'Open - Not Contacted' or 'Working - Contacted'"),
            ("Rating", "rating", str, "Rating of the lead: 'Hot', 'Warm' or 'Cold'"),
            ("LeadSource", "lead_source", str, "Where the lead came from, for example 'Web' or 'Purchased List'"),
            ("IsConverted", "is_converted", bool, "True when the lead was already converted into an account, contact and opportunity"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[
            ("email", "Email", "eq", "Exact email address of the lead, for example 'bertha@fcof.net'"),
            ("company", "Company", "like", "Text contained in the company name of the lead, for example 'farmers'; the match ignores upper and lower case"),
            ("status", "Status", "eq", "Exact lead status, for example 'Working - Contacted'"),
        ],
        example={"id": "00Qfj000007RfxVEAS", "first_name": "Bertha", "last_name": "Boxer", "email": "bertha@fcof.net", "phone": "(850) 644-4200",
                 "company": "Farmers Coop. of Florida", "title": "Director of Vendor Relations", "status": "Working - Contacted", "rating": "Hot",
                 "lead_source": "Web", "is_converted": False, "owner_id": "005fj000009FOJNAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="opportunity", sobject="Opportunity", noun="opportunity", plural="opportunities",
        summary="its name, sales stage, amount, close date, probability, type, source, whether it is closed or won, account id and owner",
        example_search={"stage_name": "Qualification", "min_amount": 10000},
        fields=[
            ("Id", "id", str, "Salesforce id of the opportunity"),
            ("Name", "name", str, "Name of the opportunity"),
            ("StageName", "stage_name", str, "Current sales stage, for example 'Prospecting', 'Qualification' or 'Closed Won'"),
            ("Amount", "amount", float, "Expected amount of the opportunity, in the currency of the org"),
            ("CloseDate", "close_date", str, "Expected or actual close date, in YYYY-MM-DD format"),
            ("Probability", "probability", float, "Probability of winning the opportunity, as a percentage from 0 to 100"),
            ("Type", "type", str, "Type of opportunity, for example 'New Customer' or 'Existing Customer - Upgrade'"),
            ("LeadSource", "lead_source", str, "Where the opportunity came from, for example 'Web' or 'Partner Referral'"),
            ("IsClosed", "is_closed", bool, "True when the opportunity is in a closed stage, either won or lost"),
            ("IsWon", "is_won", bool, "True when the opportunity was closed as won"),
            ("AccountId", "account_id", str, "Salesforce id of the account the opportunity belongs to; use salesforce.account.get to read it"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[
            ("stage_name", "StageName", "eq", "Exact sales stage, for example 'Qualification' or 'Closed Won'"),
            ("min_amount", "Amount", "gte", "Minimum amount: only opportunities with an amount equal to or greater than this number are returned"),
            ("account_id", "AccountId", "id", "Salesforce id of the account whose opportunities you want, 15 or 18 letters and digits"),
        ],
        example={"id": "006fj0000070GqLAAU", "name": "Acme Mobile Generators", "stage_name": "Qualification", "amount": 15000.0, "close_date": "2026-10-24",
                 "probability": 10.0, "type": "New Customer", "lead_source": "Purchased List", "is_closed": False, "is_won": False,
                 "account_id": "001fj00000WTSTBAA5", "owner_id": "005fj000009FOJNAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="case", sobject="Case", noun="case", plural="cases",
        summary="its case number, subject, description, status, priority, origin, contact id, account id, whether it is closed, and owner",
        example_search={"status": "Closed", "priority": "High"},
        fields=[
            ("Id", "id", str, "Salesforce id of the case"),
            ("CaseNumber", "case_number", str, "Case number shown to users, for example '00001001'"),
            ("Subject", "subject", str, "Short subject line of the case"),
            ("Description", "description", str, "Long description of the problem or request"),
            ("Status", "status", str, "Status of the case, for example 'New', 'Working' or 'Closed'"),
            ("Priority", "priority", str, "Priority of the case, for example 'High', 'Medium' or 'Low'"),
            ("Origin", "origin", str, "Channel where the case was opened, for example 'Phone', 'Email' or 'Web'"),
            ("ContactId", "contact_id", str, "Salesforce id of the contact who reported the case; use salesforce.contact.get to read it"),
            ("AccountId", "account_id", str, "Salesforce id of the account the case belongs to; use salesforce.account.get to read it"),
            ("IsClosed", "is_closed", bool, "True when the case is in a closed status"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[
            ("status", "Status", "eq", "Exact case status, for example 'New', 'Working' or 'Closed'"),
            ("priority", "Priority", "eq", "Exact case priority, for example 'High', 'Medium' or 'Low'"),
            ("contact_id", "ContactId", "id", "Salesforce id of the contact whose cases you want, 15 or 18 letters and digits"),
        ],
        example={"id": "500fj00000lnVGdAAM", "case_number": "00001001", "subject": "Performance inadequate for second consecutive week",
                 "description": None, "status": "Closed", "priority": "High", "origin": "Phone", "contact_id": "003fj00000TZjwIAAT",
                 "account_id": "001fj00000WTSTDAA5", "is_closed": True, "owner_id": "005fj000009FOJNAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="task", sobject="Task", noun="task", plural="tasks", search=False,
        summary="its subject, status, priority, due date, description, the related contact or lead (who id) and record (what id), whether it is closed, and owner",
        fields=[
            ("Id", "id", str, "Salesforce id of the task"),
            ("Subject", "subject", str, "Subject of the task, for example 'Call Ana about the proposal'"),
            ("Status", "status", str, "Status of the task, for example 'Not Started', 'In Progress' or 'Completed'"),
            ("Priority", "priority", str, "Priority of the task, for example 'High', 'Normal' or 'Low'"),
            ("ActivityDate", "due_date", str, "Due date of the task, in YYYY-MM-DD format"),
            ("Description", "description", str, "Free text with the details of the task"),
            ("WhoId", "who_id", str, "Salesforce id of the contact or lead the task is about"),
            ("WhatId", "what_id", str, "Salesforce id of the account, opportunity or other record the task is related to"),
            ("IsClosed", "is_closed", bool, "True when the task is in a completed status"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[],
        example={"id": "00Tfj00000AbCdEEAV", "subject": "Call Ana about the proposal", "status": "Not Started", "priority": "Normal", "due_date": "2026-10-20",
                 "description": None, "who_id": "003fj00000TZjw1AAD", "what_id": "001fj00000WTST8AAP", "is_closed": False,
                 "owner_id": "005fj000009FOJNAA4", "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="event", sobject="Event", noun="event", plural="events", search=False,
        summary="its subject, start and end date and time, whether it lasts all day, location, description, the related contact or lead (who id) and record (what id), and owner",
        fields=[
            ("Id", "id", str, "Salesforce id of the calendar event"),
            ("Subject", "subject", str, "Subject of the event, for example 'Demo with Acme'"),
            ("StartDateTime", "start_date_time", str, "Date and time when the event starts, in ISO 8601 format"),
            ("EndDateTime", "end_date_time", str, "Date and time when the event ends, in ISO 8601 format"),
            ("IsAllDayEvent", "is_all_day_event", bool, "True when the event lasts the whole day and has no specific start time"),
            ("Location", "location", str, "Place where the event happens, as free text"),
            ("Description", "description", str, "Free text with the details of the event"),
            ("WhoId", "who_id", str, "Salesforce id of the contact or lead the event is about"),
            ("WhatId", "what_id", str, "Salesforce id of the account, opportunity or other record the event is related to"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[],
        example={"id": "00Ufj00000AbCdEEAV", "subject": "Demo with Acme", "start_date_time": "2026-10-20T15:00:00.000+0000",
                 "end_date_time": "2026-10-20T16:00:00.000+0000", "is_all_day_event": False, "location": "Video call", "description": None,
                 "who_id": "003fj00000TZjw1AAD", "what_id": "001fj00000WTST8AAP", "owner_id": "005fj000009FOJNAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="campaign", sobject="Campaign", noun="campaign", plural="campaigns", search=False,
        summary="its name, type, status, start and end date, whether it is active, budgeted and actual cost, expected revenue, number of leads, contacts and opportunities, and owner",
        fields=[
            ("Id", "id", str, "Salesforce id of the campaign"),
            ("Name", "name", str, "Name of the marketing campaign"),
            ("Type", "type", str, "Type of campaign, for example 'Webinar', 'Email' or 'Conference'"),
            ("Status", "status", str, "Status of the campaign, for example 'Planned', 'In Progress' or 'Completed'"),
            ("StartDate", "start_date", str, "Date when the campaign starts, in YYYY-MM-DD format"),
            ("EndDate", "end_date", str, "Date when the campaign ends, in YYYY-MM-DD format"),
            ("IsActive", "is_active", bool, "True when the campaign is active"),
            ("BudgetedCost", "budgeted_cost", float, "Planned cost of the campaign, in the currency of the org"),
            ("ActualCost", "actual_cost", float, "Real cost spent on the campaign so far, in the currency of the org"),
            ("ExpectedRevenue", "expected_revenue", float, "Revenue the campaign is expected to bring, in the currency of the org"),
            ("NumberOfLeads", "number_of_leads", int, "Number of leads that are members of the campaign"),
            ("NumberOfContacts", "number_of_contacts", int, "Number of contacts that are members of the campaign"),
            ("NumberOfOpportunities", "number_of_opportunities", int, "Number of opportunities linked to the campaign"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[],
        example={"id": "701fj00000WTl8UAAT", "name": "Product Webinar", "type": "Webinar", "status": "Completed", "start_date": "2026-05-28",
                 "end_date": "2026-05-28", "is_active": True, "budgeted_cost": 10000.0, "actual_cost": 11400.0, "expected_revenue": 3000000.0,
                 "number_of_leads": 0, "number_of_contacts": 0, "number_of_opportunities": 0, "owner_id": "005fj000009FOJNAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
    dict(
        key="note", sobject="Note", noun="note", plural="notes", search=False, list=False,
        find_hint="salesforce.soql.query with a SELECT Id, Title FROM Note statement",
        summary="its title, body text, the id of the record it is attached to (parent id), whether it is private, owner, and creation and modification dates",
        fields=[
            ("Id", "id", str, "Salesforce id of the note"),
            ("Title", "title", str, "Title of the note"),
            ("Body", "body", str, "Text of the note"),
            ("ParentId", "parent_id", str, "Salesforce id of the record the note is attached to, for example an account or opportunity"),
            ("IsPrivate", "is_private", bool, "True when only the owner of the note can see it"),
            OWNER, CREATED, MODIFIED,
        ],
        filters=[],
        example={"id": "002fj00000AbCdEAAV", "title": "Call summary", "body": "Ana asked for a new quote.", "parent_id": "001fj00000WTST8AAP",
                 "is_private": False, "owner_id": "005fj000009FOJNAA4",
                 "created_date": "2026-01-10T15:00:23.000+0000", "last_modified_date": "2026-02-01T10:00:00.000+0000"},
    ),
]


def _record_model(cfg: dict[str, Any]) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for sf, name, typ, desc in cfg["fields"]:
        fields[name] = (typ, Field(description=desc)) if name == "id" else (Optional[typ], Field(default=None, description=desc))
    return create_model(f"Salesforce{cfg['sobject']}", **fields)


def _to_record(model: type[BaseModel], cfg: dict[str, Any], raw: dict[str, Any]) -> BaseModel:
    return model(**{name: raw.get(sf) for sf, name, _, _ in cfg["fields"]})


def _select(cfg: dict[str, Any]) -> str:
    return ",".join(sf for sf, _, _, _ in cfg["fields"])


def _where(cfg: dict[str, Any], args: BaseModel) -> str:
    clauses = []
    for arg, sf, kind, _ in cfg["filters"]:
        value = getattr(args, arg)
        if value is None:
            continue
        if kind == "like":
            clauses.append(f"{sf} LIKE {soql_like(value)}")
        elif kind == "gte":
            clauses.append(f"{sf} >= {float(value)!r}")
        else:  # eq e id
            clauses.append(f"{sf} = {soql_str(value)}")
    return " AND ".join(clauses)


async def _query(ctx: Context, cfg: dict[str, Any], model: type[BaseModel], where: str, limit: int, offset: int) -> tuple[list[BaseModel], bool]:
    """Corre el SOQL pidiendo un registro de mas para saber si hay otra pagina."""
    soql = (f"SELECT {_select(cfg)} FROM {cfg['sobject']}" + (f" WHERE {where}" if where else "")
            + f" ORDER BY CreatedDate DESC LIMIT {limit + 1} OFFSET {offset}")
    body = await get_json(ctx, "/query", params={"q": soql})
    rows = body.get("records", [])
    return [_to_record(model, cfg, r) for r in rows[:limit]], len(rows) > limit


def _register(cfg: dict[str, Any]) -> None:
    key, sobject, noun, plural, summary = cfg["key"], cfg["sobject"], cfg["noun"], cfg["plural"], cfg["summary"]
    Record = _record_model(cfg)
    example = cfg["example"]

    # --- list ---
    if cfg.get("list", True):
        ListIn = create_model(
            f"Salesforce{sobject}ListIn",
            limit=(int, Field(default=50, ge=1, le=MAX_LIMIT, description=f"How many {plural} to return, from 1 to {MAX_LIMIT} (default 50)")),
            offset=(int, Field(default=0, ge=0, le=MAX_OFFSET, description=f"How many {plural} to skip, from 0 to {MAX_OFFSET}; use the next_offset value of a previous result to continue")),
        )
        ListOut = create_model(
            f"Salesforce{sobject}ListOut",
            records=(list[Record], Field(description=f"The {plural} returned in this page, newest first")),
            has_more=(bool, Field(description=f"True when there are more {plural} than were returned and a next page can be requested")),
            next_offset=(Optional[int], Field(default=None, description=f"Offset to pass as input to get the next page of {plural}; empty when there is no next page or Salesforce cannot skip that far")),
        )

        async def list_handler(ctx: Context, args: ListIn) -> ListOut:
            records, has_more = await _query(ctx, cfg, Record, "", args.limit, args.offset)
            nxt = args.offset + args.limit
            return ListOut(records=records, has_more=has_more, next_offset=nxt if has_more and nxt <= MAX_OFFSET else None)

        search_hint = f"; to filter them use salesforce.{key}.search" if cfg.get("search", True) else ""
        function(
            id=f"salesforce.{key}.list", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
            description=(
                f"Lists the {plural} stored in the connected Salesforce org, newest first. Each record includes {summary}. Use it when the user asks to see, "
                f"browse or review their {plural}, or needs a {noun} id for a later step. It returns up to {MAX_LIMIT} records per call; when has_more is true, "
                f"call it again with next_offset (Salesforce can skip at most {MAX_OFFSET} records this way). Read-only: it does not create, change or delete "
                f"{plural}. For one {noun} use salesforce.{key}.get{search_hint}."
            ),
            examples=[{"name": "default", "input": {"limit": 1}, "output": {"records": [example], "has_more": False}}],
        )(list_handler)

    # --- get ---
    id_arg = f"{key}_id"
    GetIn = create_model(
        f"Salesforce{sobject}GetIn",
        **{id_arg: (str, Field(pattern=ID_PATTERN, description=f"Salesforce id of the {noun}, 15 or 18 letters and digits, for example '{example['id']}'"))},
    )

    async def get_handler(ctx: Context, args: GetIn) -> Record:
        raw = await get_json(ctx, f"/sobjects/{sobject}/{getattr(args, id_arg)}", params={"fields": _select(cfg)})
        return _to_record(Record, cfg, raw)

    find_hint = cfg.get("find_hint") or (f"salesforce.{key}.search or salesforce.{key}.list" if cfg.get("search", True) else f"salesforce.{key}.list")
    function(
        id=f"salesforce.{key}.get", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
        description=(
            f"Returns one Salesforce {noun} given its record id, with {summary}. Use it when the user asks for the details of a specific {noun}, or when "
            f"another record points to it by id. Read-only: it does not change the {noun}. It fails with not_found when the id does not exist or is not "
            f"visible to the connected user. To find the id first use {find_hint}."
        ),
        examples=[{"name": "default", "input": {id_arg: example["id"]}, "output": example}],
    )(get_handler)

    # --- search ---
    if not cfg.get("search", True):
        return
    filter_fields: dict[str, Any] = {}
    for arg, _, kind, desc in cfg["filters"]:
        if kind == "gte":
            filter_fields[arg] = (Optional[float], Field(default=None, ge=0, allow_inf_nan=False, description=desc))
        elif kind == "id":
            filter_fields[arg] = (Optional[str], Field(default=None, pattern=ID_PATTERN, description=desc))
        else:
            filter_fields[arg] = (Optional[str], Field(default=None, min_length=1, max_length=100, description=desc))
    names = [f[0] for f in cfg["filters"]]

    class SearchBase(BaseModel):
        @model_validator(mode="after")
        def _needs_a_filter(self):
            if all(getattr(self, n) is None for n in names):
                raise ValueError("Give at least one filter: " + ", ".join(names))
            return self

    SearchIn = create_model(
        f"Salesforce{sobject}SearchIn", __base__=SearchBase, **filter_fields,
        limit=(int, Field(default=50, ge=1, le=MAX_LIMIT, description=f"How many {plural} to return, from 1 to {MAX_LIMIT} (default 50)")),
    )
    SearchOut = create_model(
        f"Salesforce{sobject}SearchOut",
        records=(list[Record], Field(description=f"The {plural} that match all the filters, newest first")),
        has_more=(bool, Field(description=f"True when more {plural} match than were returned; add a filter or raise the limit")),
    )

    async def search_handler(ctx: Context, args: SearchIn) -> SearchOut:
        records, has_more = await _query(ctx, cfg, Record, _where(cfg, args), args.limit, 0)
        return SearchOut(records=records, has_more=has_more)

    kinds = {"like": "text contained in", "eq": "exact value of", "gte": "minimum value of", "id": "id of the related"}
    filters_text = "; ".join(f"{arg} ({kinds[k]} {sf})" for arg, sf, k, _ in cfg["filters"])
    function(
        id=f"salesforce.{key}.search", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
        description=(
            f"Searches the {plural} of the connected Salesforce org that match the given filters and returns them newest first, each with {summary}. "
            f"Filters available: {filters_text}. Use it when the user asks to find {plural} by one of these criteria. At least one filter is required "
            f"and, when several are given, all of them must match; text filters match anywhere in the value ignoring upper and lower case. It returns up "
            f"to {MAX_LIMIT} records and has_more tells whether more match. Read-only. To browse without filters use salesforce.{key}.list, and for one "
            f"{noun} by id use salesforce.{key}.get."
        ),
        examples=[{"name": "default", "input": cfg["example_search"], "output": {"records": [example], "has_more": False}}],
    )(search_handler)


for _cfg in OBJECTS:
    _register(_cfg)
