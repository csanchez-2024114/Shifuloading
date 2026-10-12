"""Funciones de lectura de Brevo (API v3). Endpoints y campos verificados en developers.brevo.com el 2026-10-06.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito: el agente los usa para buscar la funcion
y para llenar sus argumentos (ver doc/funciones/CONTRATO.md, "Descripciones").
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.functions.apps.brevo.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

BASE_URL = "https://api.brevo.com/v3"


# --- brevo.account.get (whoami) ------------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class Account(BaseModel):
    account_id: str = Field(description="Identifier of the Brevo account; it is the account email, the same value stored when the account was connected")
    email: str = Field(description="Email address of the Brevo account owner")
    company_name: Optional[str] = Field(default=None, description="Company name registered in the Brevo account, if any")
    first_name: Optional[str] = Field(default=None, description="First name of the account owner, if set")
    last_name: Optional[str] = Field(default=None, description="Last name of the account owner, if set")


@function(
    id="brevo.account.get", version=1, verb=Verb.read, upstream_api="v3",
    description=(
        "Returns the Brevo account that is connected for the user: the account email (which also serves as the account identifier), the company name and "
        "the first and last name of the owner. Use it to confirm which Brevo account is being used before reading or changing anything, to answer questions "
        "such as 'which Brevo account do I have connected?', or to check that the connection and API key still work. Read-only: it takes no parameters and "
        "does not modify anything in Brevo. If the user has several Brevo accounts connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "ana@empresa.test", "email": "ana@empresa.test", "company_name": "Empresa", "first_name": "Ana", "last_name": "Perez"}}],
)
async def account_get(ctx: Context, args: NoArgs) -> Account:
    body = (await ctx.conn.request("GET", f"{BASE_URL}/account")).json()
    email = body["email"]
    return Account(account_id=email, email=email, company_name=body.get("companyName"),
                   first_name=body.get("firstName"), last_name=body.get("lastName"))


# --- brevo.contacts.list -------------------------------------------------------------------------

class ListContactsIn(BaseModel):
    limit: int = Field(default=50, ge=1, le=1000, description="How many contacts to return in this page, from 1 to 1000 (default 50)")
    offset: int = Field(default=0, ge=0, description="Zero-based index of the first contact of the page; use it to read further pages (default 0)")
    sort: Literal["asc", "desc"] = Field(default="desc", description="Order by creation date: 'desc' returns the newest contacts first (default), 'asc' the oldest first")


class Contact(BaseModel):
    id: int = Field(description="Brevo contact id")
    email: Optional[str] = Field(default=None, description="Email address of the contact, if it has one")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the contact was created")
    modified_at: Optional[str] = Field(default=None, description="UTC date and time of the last change to the contact")
    email_blacklisted: bool = Field(default=False, description="True if the contact's email is blocked from receiving campaigns")
    list_ids: list[int] = Field(default_factory=list, description="Ids of the Brevo lists the contact belongs to")
    attributes: dict[str, Any] = Field(default_factory=dict, description="Custom contact attributes, for example FIRSTNAME or SMS")


class ListContactsOut(BaseModel):
    count: int = Field(description="Total number of contacts in the whole account, not only in this page")
    contacts: list[Contact] = Field(description="The contacts of this page")


@function(
    id="brevo.contacts.list", version=1, verb=Verb.read, upstream_api="v3",
    description=(
        "Lists the contacts stored in the connected Brevo account, newest first by default, with pagination. Each contact includes its id, email address, creation and "
        "modification dates, whether its email is blacklisted, the ids of the lists it belongs to and its custom attributes (for example first name or phone). "
        "Use it when the user wants to see, browse, count or export their Brevo contacts, or needs a contact id for a later step. The reply also gives the total "
        "number of contacts in the account, not just in the page. Read-only. A page holds at most 1000 contacts; use offset to read the next pages. "
        "It cannot search by email or filter by list yet, and it does not create, change or delete contacts."
    ),
    examples=[{"name": "default", "input": {"limit": 2}, "output": {"count": 1, "contacts": [
        {"id": 1, "email": "cliente@ejemplo.test", "created_at": "2026-01-01T10:00:00.000Z", "modified_at": "2026-01-02T10:00:00.000Z",
         "email_blacklisted": False, "list_ids": [3], "attributes": {"FIRSTNAME": "Cli"}}]}}],
)
async def contacts_list(ctx: Context, args: ListContactsIn) -> ListContactsOut:
    body = (await ctx.conn.request("GET", f"{BASE_URL}/contacts",
                                   params={"limit": args.limit, "offset": args.offset, "sort": args.sort})).json()
    contacts = [
        Contact(id=c["id"], email=c.get("email"), created_at=c.get("createdAt"), modified_at=c.get("modifiedAt"),
                email_blacklisted=bool(c.get("emailBlacklisted", False)), list_ids=c.get("listIds") or [],
                attributes=c.get("attributes") or {})
        for c in body.get("contacts", [])
    ]
    return ListContactsOut(count=body.get("count", len(contacts)), contacts=contacts)


# --- brevo.templates.list ------------------------------------------------------------------------

class ListTemplatesIn(BaseModel):
    limit: int = Field(default=50, ge=1, le=1000, description="How many templates to return in this page, from 1 to 1000 (default 50)")
    offset: int = Field(default=0, ge=0, description="Zero-based index of the first template of the page; use it to read further pages (default 0)")
    only_active: Optional[bool] = Field(default=None, description="True returns only active templates, False only inactive ones; leave empty to return all templates")


class Template(BaseModel):
    id: int = Field(description="Brevo template id")
    name: str = Field(description="Name of the template")
    subject: Optional[str] = Field(default=None, description="Subject line of the email template")
    is_active: bool = Field(default=False, description="True if the template is active and can be used to send emails")
    tag: Optional[str] = Field(default=None, description="Tag assigned to the template, if any")
    created_at: Optional[str] = Field(default=None, description="UTC date and time when the template was created")
    modified_at: Optional[str] = Field(default=None, description="UTC date and time of the last change to the template")


class ListTemplatesOut(BaseModel):
    count: int = Field(description="Total number of templates that match the filter in the whole account")
    templates: list[Template] = Field(description="The templates of this page, without their HTML body")  # sin htmlContent: puede pesar mucho


@function(
    id="brevo.templates.list", version=1, verb=Verb.read, upstream_api="v3",
    description=(
        "Lists the email templates saved in the connected Brevo account, with pagination. Each template includes its id, name, subject line, active or inactive "
        "status, tag and creation and modification dates. The HTML body of a template is intentionally not returned because it can be very large. "
        "Use it when the user asks which email templates exist, wants to choose a template to send or edit, or needs a template id for a later step. "
        "It can be limited to active or inactive templates. Read-only: it does not create, edit or send templates or emails. A page holds at most 1000 templates."
    ),
    examples=[{"name": "default", "input": {"only_active": True}, "output": {"count": 1, "templates": [
        {"id": 7, "name": "Bienvenida", "subject": "Hola", "is_active": True, "tag": "onboarding",
         "created_at": "2026-01-01T10:00:00.000Z", "modified_at": "2026-01-02T10:00:00.000Z"}]}}],
)
async def templates_list(ctx: Context, args: ListTemplatesIn) -> ListTemplatesOut:
    params: dict[str, Any] = {"limit": args.limit, "offset": args.offset}
    if args.only_active is not None:
        params["templateStatus"] = "true" if args.only_active else "false"
    body = (await ctx.conn.request("GET", f"{BASE_URL}/smtp/templates", params=params)).json()
    templates = [
        Template(id=t["id"], name=t["name"], subject=t.get("subject"), is_active=bool(t.get("isActive", False)),
                 tag=t.get("tag"), created_at=t.get("createdAt"), modified_at=t.get("modifiedAt"))
        for t in body.get("templates", [])
    ]
    return ListTemplatesOut(count=body.get("count", len(templates)), templates=templates)
