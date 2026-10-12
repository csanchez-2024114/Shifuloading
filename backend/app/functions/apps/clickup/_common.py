"""Ayudantes y modelos compartidos de las funciones de ClickUp (API v2 y v3).

Las rutas, parametros y formas de respuesta salen de las especificaciones OpenAPI oficiales
(developer.clickup.com/openapi/clickup-api-v2-reference.json y ClickUp_PUBLIC_API_V3.yaml, 2026-10-08).
Las salidas dejan pasar los campos que ClickUp agrega (extra="allow") y solo tipan los importantes, todos opcionales:
asi un campo nuevo o ausente en un plan no rompe la funcion con `upstream_changed`.
"""
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.functions.context import Context
from app.functions.errors import FunctionError
from app.functions.spec import ErrorCode

V2 = "https://api.clickup.com/api/v2"
V3 = "https://api.clickup.com/api/v3"

# Los ids de ClickUp son numericos o alfanumericos ("86abc12", "3c-106", "8cnn-1234"): nunca llevan "/" ni "..". Se valida para que
# un argumento no pueda cambiar la ruta de la peticion.
PathId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]+$", min_length=1, max_length=64)]


def _to_str(value: Any) -> Any:
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


# ClickUp manda ids como texto o como entero segun el endpoint (user.id es entero, team.id texto): se normalizan a texto.
Ident = Annotated[Optional[str], BeforeValidator(_to_str)]


class Out(BaseModel):
    """Base de las salidas: tipa lo importante y deja pasar el resto de lo que mande ClickUp."""
    model_config = ConfigDict(extra="allow")


class NoArgs(BaseModel):
    pass


class WorkspaceIn(BaseModel):
    workspace_id: PathId = Field(description="ClickUp Workspace id (named team_id in the API). Get it from clickup.workspaces.list")


class SpaceIn(BaseModel):
    space_id: PathId = Field(description="ClickUp Space id. Get it from clickup.spaces.list")


class FolderIn(BaseModel):
    folder_id: PathId = Field(description="ClickUp Folder id. Get it from clickup.folders.list")


class ListIn(BaseModel):
    list_id: PathId = Field(description="ClickUp List id. Get it from clickup.lists.list or clickup.lists.list_folderless")


class TaskIn(BaseModel):
    task_id: PathId = Field(description="ClickUp task id, for example '86abc12'. Get it from clickup.tasks.list or clickup.tasks.list_workspace")


class ViewIn(BaseModel):
    view_id: PathId = Field(description="ClickUp view id, for example '3c-106'. Get it from one of the clickup.views.list_* functions")


class Cursor(BaseModel):
    """Paginacion por cursor de la API v3 (chat, adjuntos, documentos)."""
    cursor: Optional[str] = Field(default=None, description="Pagination cursor: pass the next_cursor value of the previous response to get the next page; leave empty for the first page")
    limit: int = Field(default=50, ge=1, le=100, description="Maximum number of results per page, from 1 to 100 (default 50)")


def query(**values: Any) -> dict[str, Any]:
    """Parametros de la query sin los vacios; los booleanos van como true/false y las listas como parametro repetido (la clave lleva '[]')."""
    out: dict[str, Any] = {}
    for key, value in values.items():
        if value is None or value == []:
            continue
        out[key] = ("true" if value else "false") if isinstance(value, bool) else value
    return out


async def get(ctx: Context, url: str, params: Optional[dict[str, Any]] = None) -> Any:
    """GET con la credencial de la cuenta; devuelve el JSON. Una respuesta que no es JSON es un cambio de la app, no un error de quien llama."""
    resp = await ctx.conn.request("GET", url, params=params or None)
    try:
        return resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "ClickUp respondio algo que no es JSON.") from None


def obj(body: Any) -> dict[str, Any]:
    return body if isinstance(body, dict) else {}


def items(body: Any, key: str) -> list[Any]:
    """La lista `key` de una respuesta, o [] si no esta."""
    value = obj(body).get(key)
    return value if isinstance(value, list) else []


def unwrap(body: Any, key: str = "data") -> Any:
    """Algunas respuestas (tiempos, v3) vienen envueltas en {"data": ...}."""
    data = obj(body).get(key)
    return data if data is not None else body


def page_cursor(body: Any) -> Optional[str]:
    cursor = obj(body).get("next_cursor")
    return str(cursor) if cursor else None


async def send(ctx: Context, method: str, url: str, payload: dict[str, Any], params: Optional[dict[str, Any]] = None) -> Any:
    """POST/PUT con cuerpo JSON (las funciones de escritura); devuelve el JSON de la respuesta."""
    resp = await ctx.conn.request(method, url, json=payload, params=params or None)
    try:
        return resp.json()
    except ValueError:
        raise FunctionError(ErrorCode.upstream_changed, "ClickUp respondio algo que no es JSON.") from None
