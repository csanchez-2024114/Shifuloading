"""Funciones de Kick. Whoami: GET api.kick.com/public/v1/users sin ids = el usuario autenticado (scope user:read), verificado el 2026-10-07.
Las demas lecturas estan en reads.py.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.kick.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.registry import function
from app.functions.spec import ErrorCode, Verb

API_URL = "https://api.kick.com/public/v1"


class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="Kick user id of the connected account, the same value stored when the account was connected")
    display_name: str = Field(description="Kick username of the connected account")
    email: Optional[str] = Field(default=None, description="Email address of the Kick account, if Kick shares it")
    profile_picture: Optional[str] = Field(default=None, description="Link to the profile picture of the Kick account")


@function(
    id="kick.user.get", version=1, verb=Verb.read, upstream_api="public/v1", scopes=["user:read"],
    description=(
        "Returns the Kick account that is connected: its Kick user id, username, email address (when Kick shares it) and profile picture link. Use "
        "it to confirm which Kick account is being used, to answer questions such as 'which Kick channel do I have connected?', or to check that the "
        "connection still works before reading channel or livestream data. Read-only: it takes no parameters and does not change anything on Kick. "
        "If several Kick accounts are connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "123456", "display_name": "empresademo", "email": "ana@empresa.test", "profile_picture": "https://files.kick.com/images/user/123456/profile.webp"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    users = (await ctx.conn.request("GET", f"{API_URL}/users")).json().get("data") or []
    if not users:
        raise FunctionError(ErrorCode.upstream_changed, "Kick no devolvio el usuario autenticado.")
    user = users[0]
    account_id = str(user["user_id"])
    return Me(account_id=account_id, display_name=user.get("name") or account_id, email=user.get("email"), profile_picture=user.get("profile_picture"))


from app.functions.apps.kick import reads  # noqa: E402,F401  (load_all solo importa functions.py)
