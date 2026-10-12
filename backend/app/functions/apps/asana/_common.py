"""Helpers compartidos por los modulos de funciones de Asana (functions.py, f_advanced.py, f_legacy.py)."""
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field, create_model

from app.functions.context import Context

BASE_URL = "https://app.asana.com/api/1.0"

LIMIT_KW = dict(default=100, ge=1, le=100, description="Maximum number of items to return in this page, from 1 to 100 (default 100)")
OFFSET_DESC = "Offset token returned by a previous page to continue listing from there"


async def get_body(ctx: Context, path: str, *, params: Optional[dict] = None, ok_statuses: tuple[int, ...] = ()) -> dict:
    """GET a Asana y devuelve el JSON completo del body (envuelto siempre en {"data": ...})."""
    resp = await ctx.conn.request("GET", f"{BASE_URL}{path}", params=params or None, ok_statuses=ok_statuses)
    return resp.json()


async def send_body(ctx: Context, method: str, path: str, payload: dict[str, Any], *, params: Optional[dict] = None) -> dict:
    """POST/PUT con el cuerpo que Asana espera ({"data": {...}}); devuelve el JSON completo de la respuesta."""
    resp = await ctx.conn.request(method, f"{BASE_URL}{path}", json={"data": payload}, params=params or None)
    return resp.json()


def nested_gid(raw: dict, key: str) -> Optional[str]:
    """Gid de un objeto compacto {gid, name} anidado (assignee, owner, project, workspace...)."""
    value = raw.get(key)
    return value.get("gid") if isinstance(value, dict) else None


def next_offset(body: dict) -> Optional[str]:
    """Cursor "offset" de la pagina siguiente; Asana lo devuelve en next_page.offset cuando hay mas resultados."""
    return (body.get("next_page") or {}).get("offset")


def page_params(limit: int, offset: Optional[str], opt_fields: str, **extra: Any) -> dict:
    """Query comun de las listas paginadas; omite los filtros vacios (None, "" o False)."""
    params: dict[str, Any] = {"limit": limit, "opt_fields": opt_fields}
    if offset:
        params["offset"] = offset
    params.update({k: v for k, v in extra.items() if v not in (None, "", False)})
    return params


class PageIn(BaseModel):
    """Entrada comun de las listas paginadas de Asana (limit 1-100 y token offset)."""
    limit: int = Field(**LIMIT_KW)
    offset: Optional[str] = Field(default=None, description=OFFSET_DESC)


def page_model(item_cls: type[BaseModel], noun: str) -> type[BaseModel]:
    """Modelo de salida {items, has_more, next_offset} de una lista paginada de `item_cls`."""
    return create_model(
        f"{item_cls.__name__}Page",
        items=(list[item_cls], Field(description=f"{noun} returned in this page")),
        has_more=(bool, Field(description=f"True when there are more {noun} than were returned and a next page can be requested")),
        next_offset=(Optional[str], Field(default=None, description=f"Offset token to pass as input to request the next page of {noun}")),
    )


def build_page(model: type[BaseModel], body: dict, build: Callable[[dict], BaseModel]) -> BaseModel:
    """Convierte el body de una lista de Asana en la pagina de salida (Asana pone next_page.offset si hay mas)."""
    return model(items=[build(i) for i in body.get("data") or []], has_more=bool(body.get("next_page")), next_offset=next_offset(body))
