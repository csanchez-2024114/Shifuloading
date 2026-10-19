"""POST /api/v1/crm/lab/chat — adaptador para que los bancos del laboratorio midan el motor Python (solo con CRM_LAB_ADAPTER=1).

Montado en la app principal solo si CRM_LAB_ADAPTER=1; requiere CRM_DISENO=1 para el agente de diseño.
"""
from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.crm import adaptador_lab as adp
from app.crm.responder_lab import responder_real

router = APIRouter()

# Inyectable en tests; por defecto el motor real del CRM.
_responder: Callable[..., dict | Awaitable[dict]] | None = None


def configurar_responder(fn: Callable[..., dict | Awaitable[dict]] | None) -> None:
    global _responder
    _responder = fn


def adaptador_activo() -> bool:
    return os.getenv("CRM_LAB_ADAPTER", "0").strip() == "1"


def diseno_activo() -> bool:
    return os.getenv("CRM_DISENO", "0").strip() == "1"


def _motor() -> Callable[..., dict | Awaitable[dict]]:
    return _responder if _responder is not None else responder_real


class CuerpoLabChat(BaseModel):
    model_config = ConfigDict(extra="allow")

    plantilla: str = Field(default="membresias", max_length=40)
    estado: dict | None = None
    texto: str = ""
    historial: list[dict] | None = None
    muestra: dict | None = None
    seleccion: list[dict] | None = None
    imagen: str | None = None


@router.post("/lab/chat")
async def lab_chat(cuerpo: CuerpoLabChat) -> dict[str, Any]:
    if not adaptador_activo():
        raise HTTPException(status_code=404, detail="Adaptador de laboratorio desactivado (CRM_LAB_ADAPTER≠1).")
    # Solo el motor real necesita el agente de diseño; un responder inyectado (bancos/tests) no.
    if _responder is None and not diseno_activo():
        raise HTTPException(
            status_code=503,
            detail="El adaptador de laboratorio requiere CRM_DISENO=1 (agente con herramientas de diseño).",
        )
    return await adp.procesar_chat_lab(cuerpo.model_dump(), _motor())
