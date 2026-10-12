"""Funciones de Instagram. Por ahora solo whoami: GET graph.instagram.com/v26.0/me (permiso instagram_business_basic), verificado el 2026-10-07.

La documentacion muestra /me a veces plano y a veces envuelto en {"data": [...]}: se aceptan los dos.
Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.instagram.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

GRAPH_URL = "https://graph.instagram.com/v26.0"


class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="Instagram professional account id (user_id), the same value stored when the account was connected")
    display_name: str = Field(description="Instagram username of the connected account, or its name if there is no username")
    username: Optional[str] = Field(default=None, description="Instagram username without the @")
    name: Optional[str] = Field(default=None, description="Profile name of the Instagram account")
    account_type: Optional[str] = Field(default=None, description="Business or Media_Creator")


@function(
    id="instagram.user.get", version=1, verb=Verb.read, upstream_api="v26.0", scopes=["instagram_business_basic"],
    description=(
        "Returns the Instagram professional account that is connected: its account id, username, profile name and account type (business or "
        "creator). Use it to confirm which Instagram account is being used, to answer questions such as 'which Instagram do I have connected?', "
        "or to check that the connection still works before reading posts, comments or insights. Read-only: it takes no parameters and does not "
        "change anything on Instagram. Personal (non professional) accounts cannot be connected. If several Instagram accounts are connected, one "
        "of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "17841400123456789", "display_name": "empresademo", "username": "empresademo", "name": "Empresa Demo", "account_type": "Business"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    body = (await ctx.conn.request("GET", f"{GRAPH_URL}/me", params={"fields": "user_id,username,name,account_type"})).json()
    data = body["data"][0] if isinstance(body.get("data"), list) and body["data"] else body
    account_id = str(data.get("user_id") or data["id"])
    return Me(account_id=account_id, display_name=data.get("username") or data.get("name") or account_id, username=data.get("username"),
              name=data.get("name"), account_type=data.get("account_type"))
