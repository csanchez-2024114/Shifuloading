"""Funciones de Threads. Por ahora solo whoami: GET graph.threads.net/v1.0/me?fields=id,username,name (permiso threads_basic), verificado el 2026-10-07.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.threads.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

GRAPH_URL = "https://graph.threads.net/v1.0"


class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="Threads user id of the connected profile, the same value stored when the account was connected")
    display_name: str = Field(description="Threads username of the connected profile, or its name if there is no username")
    username: Optional[str] = Field(default=None, description="Threads username without the @")
    name: Optional[str] = Field(default=None, description="Profile name shown on Threads")


@function(
    id="threads.user.get", version=1, verb=Verb.read, upstream_api="v1.0", scopes=["threads_basic"],
    description=(
        "Returns the Threads profile that is connected: its Threads user id, username and profile name. Use it to confirm which Threads profile is "
        "being used, to answer questions such as 'which Threads account do I have connected?', or to check that the connection still works before "
        "reading or publishing posts. Read-only: it takes no parameters and does not change anything on Threads. It does not list posts or replies. "
        "If several Threads profiles are connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "1234567890123456", "display_name": "empresademo", "username": "empresademo", "name": "Empresa Demo"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    body = (await ctx.conn.request("GET", f"{GRAPH_URL}/me", params={"fields": "id,username,name"})).json()
    account_id = str(body["id"])
    return Me(account_id=account_id, display_name=body.get("username") or body.get("name") or account_id,
              username=body.get("username"), name=body.get("name"))
