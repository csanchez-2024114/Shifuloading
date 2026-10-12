"""Funciones de Salesforce. Por ahora solo la whoami (Tarea 1: conexion de la cuenta).

Verificado en developer.salesforce.com (2026-10-09): GET https://login.salesforce.com/services/oauth2/userinfo con el access token
devuelve user_id, organization_id, name, email, preferred_username y zoneinfo (requiere el scope `openid`). Se usa este endpoint y no
el de Chatter (/services/data/v62.0/chatter/users/me del catalogo) porque ese vive en el instance_url de la org, que el sistema aun no
guarda (ver app_spec.py). La Tarea 2 puede cambiarla cuando exista ese soporte.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.salesforce.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

USERINFO_URL = "https://login.salesforce.com/services/oauth2/userinfo"


class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="Salesforce user id (18 characters) of the connected user, the same value stored when the account was connected")
    display_name: str = Field(description="Full name of the connected Salesforce user, or the email address when the name is not available")
    email: Optional[str] = Field(default=None, description="Email address of the connected Salesforce user")
    username: Optional[str] = Field(default=None, description="Salesforce username (login name) of the connected user")
    organization_id: Optional[str] = Field(default=None, description="Id of the Salesforce organization (org) the connected user belongs to")
    zoneinfo: Optional[str] = Field(default=None, description="Time zone of the user, for example 'America/Guatemala'")


@function(
    id="salesforce.user.get", version=1, verb=Verb.read, upstream_api="v62.0", scopes=["openid"],
    description=(
        "Returns the Salesforce user who connected the account: the Salesforce user id, full name, email address, username, the id of the "
        "organization (org) the user belongs to and the user's time zone. Use it to confirm which Salesforce account is being used, to answer "
        "questions such as 'which Salesforce account do I have connected?', or to check that the connection still works before reading CRM "
        "records. Read-only: it takes no parameters and does not change anything in Salesforce. It does not return accounts, contacts or any "
        "other CRM record. If the user has several Salesforce accounts connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "005xx000001SvogAAC", "display_name": "Ana Perez", "email": "ana@empresa.test", "username": "ana@empresa.test",
        "organization_id": "00Dxx0000001gPLEAY", "zoneinfo": "America/Guatemala"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    body = (await ctx.conn.request("GET", USERINFO_URL, headers={"Accept": "application/json"})).json()
    user_id = str(body["user_id"])
    return Me(account_id=user_id, display_name=body.get("name") or body.get("email") or user_id, email=body.get("email"),
              username=body.get("preferred_username"), organization_id=body.get("organization_id"), zoneinfo=body.get("zoneinfo"))


# Las demas lecturas viven en modulos propios (se registran al importarlos, como en Asana).
from app.functions.apps.salesforce import f_analytics, f_bulk, f_chatter, f_crm, f_meta, f_org, f_query, f_users  # noqa: E402,F401
