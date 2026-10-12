"""Disparar un workflow desde fuera: POST /webhooks/{token} (se monta bajo /api/v1).

El token (lo genera set_webhook_trigger) es la unica autenticacion: largo, aleatorio y secreto.
Si no existe se responde 404 generico, igual que un workflow ajeno: no se revela que tokens existen.
El cuerpo JSON queda en el run como `trigger_payload` y los pasos lo leen con {{trigger.campo}}.
"""
import json
import logging
import os
import re
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.limiter import get_real_ip, limiter
from app.database import get_db
from app.services.workflow_launcher import start_workflow_run
from app.services.workflow_run_service import ConcurrentRunLimitExceededError

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_BODY_BYTES = 64 * 1024
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")  # evita consultar Mongo con basura


def _by_token_and_ip(request: Request) -> str:
    # Por IP+token: un emisor desbocado no le quita el cupo al resto. Los tokens al azar no sirven para
    # esquivar el limite porque el tope por IP (abajo) los cuenta todos.
    return f"{get_real_ip(request)}:{request.path_params.get('token', '')}"


@router.post("/webhooks/{token}", status_code=202)
@limiter.limit("30/minute", key_func=_by_token_and_ip)
@limiter.limit("120/minute", key_func=get_real_ip)
async def trigger_webhook(request: Request, token: str, db: Any = Depends(get_db)):
    not_found = HTTPException(status_code=404, detail="No encontrado.")
    if not _TOKEN_RE.match(token):
        raise not_found
    wf = await db["workflows"].find_one({"webhook_token": token})
    if not wf or not secrets.compare_digest(str(wf.get("webhook_token", "")), token):
        raise not_found
    if wf.get("status") != "active":
        raise HTTPException(status_code=409, detail="El workflow no esta activo.")
    if not wf.get("steps"):
        raise HTTPException(status_code=409, detail="El workflow no tiene pasos.")

    # Se corta por tamano antes de leer todo: ni el encabezado ni el flujo real pueden pasar de 64 KB.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Cuerpo demasiado grande (maximo 64 KB).")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Cuerpo demasiado grande (maximo 64 KB).")
    payload = None
    if body.strip():
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(status_code=400, detail="El cuerpo debe ser JSON.") from None

    try:
        run_id = await start_workflow_run(
            db, wf, trigger="webhook", payload=payload,
            simulate=os.getenv("SHIFU_FUNCTIONS_SIMULATE", "") == "1",
        )
    except ConcurrentRunLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"run_id": run_id}
