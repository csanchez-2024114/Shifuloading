"""Funciones de Discord. Whoami: GET discord.com/api/v10/users/@me (scope identify), verificado el 2026-10-07. Las demas lecturas en reads.py.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.discord.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

API_URL = "https://discord.com/api/v10"


class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="Discord user id of the connected account, the same value stored when the account was connected")
    display_name: str = Field(description="Display name of the Discord user, or the username if no display name is set")
    username: str = Field(description="Unique Discord username")
    avatar: Optional[str] = Field(default=None, description="Avatar hash of the user, used to build the avatar image link")


@function(
    id="discord.user.get", version=1, verb=Verb.read, upstream_api="v10", scopes=["identify"],
    description=(
        "Returns the Discord user who connected the account: the Discord user id, the display name, the unique username and the avatar hash. Use it "
        "to confirm which Discord account is being used, to answer questions such as 'which Discord do I have connected?', or to check that the "
        "connection still works. Read-only: it takes no parameters and does not change anything on Discord. It does not list servers, channels or "
        "messages. If several Discord accounts are connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "80351110224678912", "display_name": "Ana Perez", "username": "anaperez", "avatar": "8342729096ea3675442027381ff50dfe"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    body = (await ctx.conn.request("GET", f"{API_URL}/users/@me")).json()
    return Me(account_id=str(body["id"]), display_name=body.get("global_name") or body["username"], username=body["username"], avatar=body.get("avatar"))


from app.functions.apps.discord import reads  # noqa: E402,F401  (load_all solo importa functions.py)
