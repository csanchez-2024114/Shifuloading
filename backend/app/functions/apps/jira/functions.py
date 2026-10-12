"""Funciones de Jira. Por ahora solo whoami: GET https://api.atlassian.com/me (scope read:me), verificado el 2026-10-07.

Las descripciones y los Field(description=...) estan en INGLES y completos a proposito (ver doc/funciones/CONTRATO.md).
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps.jira.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb


class NoArgs(BaseModel):
    pass


class Me(BaseModel):
    account_id: str = Field(description="Atlassian account id of the connected user, the same value stored when the account was connected")
    display_name: str = Field(description="Full name of the connected Atlassian user")
    email: Optional[str] = Field(default=None, description="Email address of the connected Atlassian user")
    nickname: Optional[str] = Field(default=None, description="Public nickname of the Atlassian user")
    account_status: Optional[str] = Field(default=None, description="active, inactive or closed")
    zoneinfo: Optional[str] = Field(default=None, description="Time zone of the user, for example 'America/Guatemala'")


@function(
    id="jira.user.get", version=1, verb=Verb.read, upstream_api="me", scopes=["read:me"],
    description=(
        "Returns the Atlassian user who connected Jira: the Atlassian account id, full name, email address, nickname, account status and time zone. "
        "Use it to confirm which Atlassian account is being used, to answer questions such as 'which Jira account do I have connected?', or to check "
        "that the connection still works before reading projects or issues. Read-only: it takes no parameters and does not change anything in Jira. "
        "It does not list the Jira sites the user can access. If the user has several Jira accounts connected, one of them must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {
        "account_id": "112233aa-bb11-cc22-33dd-445566abcabc", "display_name": "Ana Perez", "email": "ana@empresa.test",
        "nickname": "aperez", "account_status": "active", "zoneinfo": "America/Guatemala"}}],
)
async def user_get(ctx: Context, args: NoArgs) -> Me:
    body = (await ctx.conn.request("GET", "https://api.atlassian.com/me", headers={"Accept": "application/json"})).json()
    return Me(account_id=body["account_id"], display_name=body.get("name") or body.get("nickname") or body["account_id"],
              email=body.get("email"), nickname=body.get("nickname"), account_status=body.get("account_status"), zoneinfo=body.get("zoneinfo"))
