"""Funciones de Facebook. Por ahora solo whoami: GET /v26.0/me?fields=id,name (permiso public_profile), verificado el 2026-10-07.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from pydantic import BaseModel, Field

from app.functions.apps.facebook.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

GRAPH_URL = "https://graph.facebook.com/v26.0"


class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="App-scoped Facebook user id of the person who connected, the same value stored when the account was connected")
    display_name: str = Field(description="Full name of the connected Facebook user")


@function(
    id="facebook.user.get", version=1, verb=Verb.read, upstream_api="v26.0", scopes=["public_profile"],
    description=(
        "Returns the Facebook user who connected the account: the app-scoped user id and the full name from the public profile. Use it to confirm "
        "which Facebook profile is being used, to answer questions such as 'which Facebook do I have connected?', or to check that the connection "
        "still works before reading pages or posts. Read-only: it takes no parameters and does not change anything on Facebook. It does not list "
        "the Facebook pages the user manages. If the user has several Facebook accounts connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {"account_id": "10224567890123456", "display_name": "Ana Perez"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    body = (await ctx.conn.request("GET", f"{GRAPH_URL}/me", params={"fields": "id,name"})).json()
    return Me(account_id=str(body["id"]), display_name=body.get("name") or str(body["id"]))
