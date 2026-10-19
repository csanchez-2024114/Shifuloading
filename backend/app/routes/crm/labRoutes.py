"""POST /api/v1/crm/lab/chat — adaptador para que los bancos del laboratorio midan el motor Python (solo con CRM_LAB_ADAPTER=1).

No está montado en la app principal hasta que E1 cablee el router; los tests montan este módulo en una app de prueba.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.crm import adaptador_lab as adp

router = APIRouter()

# Inyectable en tests (motor falso); en producción lo proveerá E2.
_responder: Callable[..., dict] | None = None


def configurar_responder(fn: Callable[..., dict] | None) -> None:
    global _responder
    _responder = fn


def adaptador_activo() -> bool:
    return os.getenv("CRM_LAB_ADAPTER", "0").strip() == "1"


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
    if _responder is None:
        raise HTTPException(status_code=503, detail="Motor del chat de laboratorio no configurado todavía.")
    return adp.procesar_chat_lab(cuerpo.model_dump(), _responder)
