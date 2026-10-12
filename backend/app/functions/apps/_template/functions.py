"""PLANTILLA: una funcion = una entrada, una salida y un handler.

Reglas (detalle en doc/funciones/GUIA_JUNIOR.md y CONTRATO.md):
- id = app.recurso.verbo, en ingles y minusculas; una vez publicado NO se renombra.
- Entrada y salida son modelos Pydantic: de ahi salen input_schema y output_schema.
- La description de la funcion y la de CADA campo de entrada van en INGLES y COMPLETAS: el agente las usa para BUSCAR la funcion
  y para llenar sus argumentos. Una descripcion corta o vaga hace que no la encuentre o la use mal. Guia: que hace, cuando usarla
  (frases tipicas del usuario), que devuelve, parametros importantes con sus valores por defecto, limites y lo que NO hace.
  No uses ordenes ("ALWAYS use this", "MUST"): describe, no mandes; el modelo decide.
- El handler solo habla con la app mediante ctx.conn.request(...). Nunca toca el vault ni el token.
- No captures excepciones para devolver texto: lanza FunctionError(codigo) o deja que el runner lo maneje.
- Si cambias algo que ROMPE (campo que se quita o cambia de tipo), sube `version`; no edites la version publicada.
  Mejorar el TEXTO (descriptions, ejemplos) no rompe nada y no pide version nueva.
"""
from typing import Optional

from pydantic import BaseModel, Field

from app.functions.apps._template.app_spec import APP  # noqa: F401  (registra la app antes que las funciones)
from app.functions.context import Context
from app.functions.registry import function
from app.functions.spec import Verb

BASE_URL = "https://api.example.test/v1"


# --- example.account.get (whoami) ---------------------------------------------------------------

class NoArgs(BaseModel):
    pass


class Account(BaseModel):
    account_id: str = Field(description="Identifier of the connected account; the same value stored when the account was connected (this lets the test detect crossed accounts)")
    email: Optional[str] = Field(default=None, description="Email address of the connected account, if the app provides it")


@function(
    id="example.account.get", version=1, verb=Verb.read, upstream_api="v1",
    description=(
        "Returns the account of the Example app that is connected for the user: its account identifier and email address. Use it to confirm which account is being "
        "used, to answer questions such as 'which Example account do I have connected?', or to check that the connection still works before doing anything else. "
        "Read-only: it takes no parameters and does not change anything in the Example app. If the user has several accounts connected, one must be chosen first."
    ),
    examples=[{"name": "default", "input": {}, "output": {"account_id": "acc_1", "email": "ana@example.test"}}],
)
async def account_get(ctx: Context, args: NoArgs) -> Account:
    resp = await ctx.conn.request("GET", f"{BASE_URL}/me")
    body = resp.json()
    return Account(account_id=str(body["id"]), email=body.get("email"))


# --- example.items.list --------------------------------------------------------------------------

class ListItemsIn(BaseModel):
    limit: int = Field(default=10, ge=1, le=100, description="How many items to return, from 1 to 100 (default 10)")
    query: Optional[str] = Field(default=None, description="Optional text to filter the items by name; leave empty to return all items")


class Item(BaseModel):
    id: str = Field(description="Id of the item in the Example app")
    name: str = Field(description="Name of the item")


class ListItemsOut(BaseModel):
    items: list[Item] = Field(description="The items found, at most the requested limit")


@function(
    id="example.items.list", version=1, verb=Verb.read, upstream_api="v1", scopes=["items.read"],
    description=(
        "Lists the items stored in the connected Example app, up to a maximum number, optionally filtered by a text query on the name. Each item includes its id and "
        "its name. Use it when the user wants to see, browse or find their items, or needs an item id for a later step. It returns at most 100 items per call. "
        "Read-only: it does not create, change or delete items."
    ),
    examples=[{"name": "default", "input": {"limit": 2}, "output": {"items": [{"id": "1", "name": "Uno"}]}}],
)
async def items_list(ctx: Context, args: ListItemsIn) -> ListItemsOut:
    params = {"limit": args.limit}
    if args.query:
        params["q"] = args.query
    resp = await ctx.conn.request("GET", f"{BASE_URL}/items", params=params)
    return ListItemsOut(items=[Item(id=str(i["id"]), name=i["name"]) for i in resp.json()["items"]])


# Cuando la app responde con un error "de negocio" en un status que no es un 4xx/5xx claro (p. ej. Dropbox 409),
# pide ok_statuses=(409,) en request() y traducelo tu: raise FunctionError(ErrorCode.not_found, "...")
# (from app.functions.errors import FunctionError; from app.functions.spec import ErrorCode)
