"""Lectura y escritura del CRM en MongoDB (colección `crm_workspaces`, un documento por persona).

Los cambios se hacen leyendo el documento, aplicando una función pura (`operaciones`) y reemplazándolo solo si nadie lo
cambió mientras tanto (campo `version`). Si hubo un cambio en medio, se reintenta: dos pestañas abiertas no se pisan.
"""
from __future__ import annotations

from typing import Callable

from app.core.constants import Collections
from app.crm.estructura import normalizar
from app.crm.operaciones import ErrorCrm, ahora_utc

INTENTOS = 4


def _col(db):
    return db[Collections.CRM]


async def obtener(db, user_id: str) -> dict | None:
    doc = await _col(db).find_one({"user_id": user_id}, {"_id": 0})
    return normalizar(doc) if doc else None


async def reemplazar(db, user_id: str, doc: dict) -> dict:
    """Crea el CRM o lo reemplaza por completo (al repetir el cuestionario)."""
    await _col(db).replace_one({"user_id": user_id}, doc, upsert=True)
    return doc


async def borrar(db, user_id: str) -> None:
    await _col(db).delete_one({"user_id": user_id})


async def guardar_version(db, user_id: str, nuevo: dict, version_base: int) -> dict | None:
    """Guarda `nuevo` solo si el CRM sigue en `version_base`. Devuelve lo guardado, o None si alguien lo cambió en medio."""
    nuevo = {**nuevo, "version": version_base + 1, "updated_at": ahora_utc()}
    res = await _col(db).replace_one({"user_id": user_id, "version": version_base}, nuevo)
    return nuevo if res.matched_count == 1 else None


async def actualizar(db, user_id: str, cambiar: Callable[[dict], dict]) -> dict:
    """Aplica `cambiar(doc) -> doc_nuevo`. Si devuelve el mismo objeto no se escribe nada."""
    for _ in range(INTENTOS):
        doc = await obtener(db, user_id)
        if doc is None:
            raise ErrorCrm(404, "Todavía no tienes un CRM. Responde el cuestionario para crearlo.")
        nuevo = cambiar(doc)
        if nuevo is doc:
            return doc
        nuevo["version"] = doc["version"] + 1
        nuevo["updated_at"] = ahora_utc()
        res = await _col(db).replace_one({"user_id": user_id, "version": doc["version"]}, nuevo)
        if res.matched_count == 1:
            return nuevo
    raise ErrorCrm(409, "Tu CRM cambió mientras guardábamos. Inténtalo de nuevo.")
