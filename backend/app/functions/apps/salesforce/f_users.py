"""Lecturas de usuarios de Salesforce por la API de Chatter (user.describe, user.search, user.get_by_id).

Verificado con la API real (2026-10-09): GET /services/data/v62.0/chatter/users devuelve {users, currentPageUrl, nextPageUrl, nextPageToken};
acepta `pageSize` (1-250), `page` (numero de pagina desde 0) y `q` (busqueda por nombre, minimo 2 caracteres). GET .../chatter/users/{id} devuelve
el detalle (aboutMe, address, companyName, displayName, email, firstName, lastName, managerId, managerName, title, username, userType, isActive).
El catalogo decia que `user.describe` recibia `search`: no es asi; la busqueda es `user.search`. Todas piden el permiso `api`.
"""
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.functions.apps.salesforce._common import ID_PATTERN, UPSTREAM_API, get_json
from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb


class User(BaseModel):
    id: str = Field(description="Salesforce user id (18 characters), usable as owner id in other Salesforce records")
    name: Optional[str] = Field(default=None, description="Full name of the user as shown in Salesforce")
    first_name: Optional[str] = Field(default=None, description="First name of the user")
    last_name: Optional[str] = Field(default=None, description="Last name of the user")
    email: Optional[str] = Field(default=None, description="Email address of the user, if visible to the connected account")
    title: Optional[str] = Field(default=None, description="Job title of the user")
    company_name: Optional[str] = Field(default=None, description="Company name stored in the user profile")
    username: Optional[str] = Field(default=None, description="Salesforce username (login name) of the user")
    is_active: Optional[bool] = Field(default=None, description="True when the user account is active and can log in")
    user_type: Optional[str] = Field(default=None, description="Kind of user, for example 'Standard', 'Guest' or 'ChatterOnly'")


class UserDetail(User):
    about: Optional[str] = Field(default=None, description="The 'About me' text of the user profile, as stored in Salesforce")
    manager_id: Optional[str] = Field(default=None, description="Salesforce user id of the manager of this user, if any")
    manager_name: Optional[str] = Field(default=None, description="Full name of the manager of this user, if any")
    city: Optional[str] = Field(default=None, description="City of the user address, if filled in")
    country: Optional[str] = Field(default=None, description="Country of the user address, if filled in")


def _user(raw: dict[str, Any]) -> dict[str, Any]:
    return dict(id=raw["id"], name=raw.get("name") or raw.get("displayName"), first_name=raw.get("firstName"), last_name=raw.get("lastName"),
                email=raw.get("email"), title=raw.get("title"), company_name=raw.get("companyName"), username=raw.get("username"),
                is_active=raw.get("isActive"), user_type=raw.get("userType"))


def _next_page(body: dict[str, Any]) -> Optional[int]:
    token = body.get("nextPageToken")
    try:
        return int(token) if body.get("nextPageUrl") and token is not None else None
    except (TypeError, ValueError):
        return None


PAGE_SIZE_KW = dict(default=25, ge=1, le=250, description="How many users to return in this page, from 1 to 250 (default 25)")
PAGE_KW = dict(default=0, ge=0, description="Page number to return, starting at 0; use the next_page value of a previous result to continue")


class UserPageOut(BaseModel):
    users: list[User] = Field(description="The users returned in this page")
    has_more: bool = Field(description="True when there are more users than were returned and a next page can be requested")
    next_page: Optional[int] = Field(default=None, description="Page number to pass as input to get the next page of users; empty when there is no next page")


# --- salesforce.user.describe --------------------------------------------------------------------

class UserListIn(BaseModel):
    page_size: int = Field(**PAGE_SIZE_KW)
    page: int = Field(**PAGE_KW)


@function(
    id="salesforce.user.describe", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Lists the users of the connected Salesforce org with their profile summary: user id, full name, first and last name, email, job title, company, "
        "username, whether the account is active and the kind of user. Use it when the user asks who works in their Salesforce, wants to browse the team, or "
        "needs a user id to filter other records by owner. It returns up to 250 users per page, uses the Chatter API, and continues with the next_page "
        "value. Read-only: it does not create or change users. To look for someone by name use salesforce.user.search, and for one user in detail use "
        "salesforce.user.get_by_id."
    ),
    examples=[{"name": "default", "input": {"page_size": 2}, "output": {"users": [
        {"id": "005fj000009fDddAAE", "name": "Ana Perez", "first_name": "Ana", "last_name": "Perez", "email": "ana@empresa.test", "title": "Sales Manager",
         "company_name": "Empresa Demo", "username": "ana@empresa.test", "is_active": True, "user_type": "Standard"}], "has_more": True, "next_page": 1}}],
)
async def user_describe(ctx: Context, args: UserListIn) -> UserPageOut:
    body = await get_json(ctx, "/chatter/users", params={"pageSize": args.page_size, "page": args.page})
    nxt = _next_page(body)
    return UserPageOut(users=[User(**_user(u)) for u in body.get("users", [])], has_more=nxt is not None, next_page=nxt)


# --- salesforce.user.search ----------------------------------------------------------------------

class UserSearchIn(BaseModel):
    search_term: str = Field(min_length=2, max_length=100, description="Text to look for in the user names, at least 2 characters, for example 'perez'")
    page_size: int = Field(**PAGE_SIZE_KW)
    page: int = Field(**PAGE_KW)


@function(
    id="salesforce.user.search", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Searches the users of the connected Salesforce org by name and returns the matching profiles: user id, full name, email, job title, company, "
        "username, whether the account is active and the kind of user. Use it when the user asks to find a person in Salesforce, for example 'find Ana "
        "Perez', or needs the user id of someone to filter records by owner. The search text must have at least 2 characters and is matched by Salesforce "
        "against the names. It returns up to 250 users per page. Read-only. To list everybody use salesforce.user.describe, and for the full detail of one "
        "user use salesforce.user.get_by_id."
    ),
    examples=[{"name": "default", "input": {"search_term": "perez"}, "output": {"users": [
        {"id": "005fj000009fDddAAE", "name": "Ana Perez", "first_name": "Ana", "last_name": "Perez", "email": "ana@empresa.test", "title": "Sales Manager",
         "company_name": "Empresa Demo", "username": "ana@empresa.test", "is_active": True, "user_type": "Standard"}], "has_more": False}}],
)
async def user_search(ctx: Context, args: UserSearchIn) -> UserPageOut:
    body = await get_json(ctx, "/chatter/users", params={"q": args.search_term, "pageSize": args.page_size, "page": args.page})
    nxt = _next_page(body)
    return UserPageOut(users=[User(**_user(u)) for u in body.get("users", [])], has_more=nxt is not None, next_page=nxt)


# --- salesforce.user.get_by_id -------------------------------------------------------------------

class UserGetIn(BaseModel):
    user_id: str = Field(pattern=ID_PATTERN, description="Salesforce user id, 15 or 18 letters and digits, usually starting with 005, for example '005fj000009fDddAAE'")


@function(
    id="salesforce.user.get_by_id", version=1, verb=Verb.read, upstream_api=UPSTREAM_API, scopes=["api"],
    description=(
        "Returns the detail of one Salesforce user given the user id: full name, email, job title, company, username, whether the account is active, the kind "
        "of user, the 'About me' text, the manager (id and name) and the city and country of the address. Use it when the user asks about a specific person "
        "in Salesforce or when a record shows an owner id and the user wants to know who that is. Read-only. It fails with not_found when the id does not "
        "exist. To find the id from a name use salesforce.user.search."
    ),
    examples=[{"name": "default", "input": {"user_id": "005fj000009fDddAAE"}, "output": {
        "id": "005fj000009fDddAAE", "name": "Ana Perez", "first_name": "Ana", "last_name": "Perez", "email": "ana@empresa.test", "title": "Sales Manager",
        "company_name": "Empresa Demo", "username": "ana@empresa.test", "is_active": True, "user_type": "Standard", "about": None,
        "manager_id": "005fj000009FOJNAA4", "manager_name": "Luis Gomez", "city": "Guatemala", "country": "GT"}}],
)
async def user_get_by_id(ctx: Context, args: UserGetIn) -> UserDetail:
    raw = await get_json(ctx, f"/chatter/users/{args.user_id}")
    address = raw.get("address") or {}
    return UserDetail(**_user(raw), about=raw.get("aboutMe"), manager_id=raw.get("managerId"), manager_name=raw.get("managerName"),
                      city=address.get("city"), country=address.get("country"))
