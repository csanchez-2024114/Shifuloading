"""Reloj del CRM: ejecuta las automatizaciones aunque nadie tenga el CRM abierto y le deja un aviso a la persona.

Lo llama el programador de la plataforma (`app/workers/scheduler_loop.py`, con SHIFU_SCHEDULER=1) en cada vuelta. Como esa vuelta es
cada 30 segundos y el CRM solo necesita revisarse cada tanto, aquí se limita a una pasada cada `CRM_RELOJ_SEGUNDOS` (300 por defecto).

Por cada CRM con alguna automatización encendida: se lee, se corre lo pendiente (`automatizaciones.ejecutar_con_avisos`), se guarda SOLO si
nadie lo cambió mientras tanto (versión) y, ya guardado, se crean los avisos. Así, con dos procesos corriendo a la vez, no sale ningún aviso
doble, y lo que no se pudo guardar se reintenta en la siguiente pasada.

Los avisos (`user_notifications`) los ve la persona en la campana del CRM y, si el envío de correo está configurado, también le llegan por correo
(`notice_mailer`).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

from assistant.packs.crm.colecciones import Collections
from assistant.packs.crm import automatizaciones, repositorio as repo
from assistant.packs.crm.estructura import normalizar

logger = logging.getLogger(__name__)

MAX_POR_PASADA = 200          # CRM revisados por pasada: tope de seguridad
SEGUNDOS_POR_DEFECTO = 300

_ultima_pasada = 0.0          # reloj monotónico de la última pasada completa


def _cada_cuanto() -> float:
    try:
        return max(5.0, float(os.getenv("CRM_RELOJ_SEGUNDOS", SEGUNDOS_POR_DEFECTO)))
    except ValueError:
        return float(SEGUNDOS_POR_DEFECTO)


async def _avisar(db: Any, user_id: str, avisos: list[dict]) -> None:
    from app.services.notification_service import create_notification  # import tardío: arrastra el gestor de eventos en vivo

    for a in avisos:
        await create_notification(db, user_id, a["tipo"], a["titulo"], a["mensaje"])


async def _pasar_uno(db: Any, user_id: str, ahora: datetime | None) -> int:
    doc = await repo._col(db).find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return 0
    doc = automatizaciones.normalizar(normalizar(doc))
    nuevo, cambio, avisos = automatizaciones.ejecutar_con_avisos(doc, ahora)
    if not cambio:
        return 0
    guardado = await repo.guardar_version(db, user_id, nuevo, doc["version"])
    if guardado is None:
        return 0  # alguien lo cambió en medio (o ya lo corrió otro proceso): la próxima pasada lo reintenta, sin avisos dobles
    await _avisar(db, user_id, avisos)
    return len(avisos) or 1


async def tick(db: Any, ahora: datetime | None = None, forzar: bool = False) -> int:
    """Una pasada por los CRM con automatizaciones encendidas. Devuelve cuántos CRM tuvieron cambios.
    Si todavía no toca (menos de `CRM_RELOJ_SEGUNDOS` desde la última pasada) no hace nada, salvo con `forzar`."""
    global _ultima_pasada
    if not forzar and time.monotonic() - _ultima_pasada < _cada_cuanto():
        return 0
    _ultima_pasada = time.monotonic()
    filas = await db[Collections.CRM].find({"automatizaciones": {"$elemMatch": {"on": True}}}, {"_id": 0, "user_id": 1}).limit(MAX_POR_PASADA).to_list(MAX_POR_PASADA)
    cambiados = 0
    for fila in filas:
        try:
            if await _pasar_uno(db, fila["user_id"], ahora):
                cambiados += 1
        except Exception:  # un CRM raro no frena a los demás
            logger.exception("[crm-reloj] fallo el CRM de %s", fila.get("user_id"))
    if cambiados:
        logger.info("[crm-reloj] %s CRM con cambios", cambiados)
    return cambiados
