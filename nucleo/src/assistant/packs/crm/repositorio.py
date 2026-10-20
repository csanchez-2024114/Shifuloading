"""Lectura y escritura del CRM en MongoDB (colección `crm_workspaces`, un documento por persona).

Los cambios se hacen leyendo el documento, aplicando una función pura (`operaciones`) y reemplazándolo solo si nadie lo
cambió mientras tanto (campo `version`). Si hubo un cambio en medio, se reintenta: dos pestañas abiertas no se pisan.
"""
from __future__ import annotations

from typing import Callable

import bson

from assistant.packs.crm.colecciones import Collections
from assistant.packs.crm import automatizaciones
from assistant.packs.crm.estructura import normalizar
from assistant.packs.crm.operaciones import ErrorCrm, ahora_utc
from assistant.packs.crm.puntos import MAX_PUNTOS

INTENTOS = 4
MAX_BYTES = 12 * 1024 * 1024  # Mongo no guarda documentos de más de 16 MB: se corta antes, con un mensaje claro


def _cabe(doc: dict) -> None:
    """Lanza ErrorCrm 413 si el CRM ya no cabe en un documento de Mongo."""
    try:
        tamano = len(bson.encode(doc))
    except Exception:  # algo que bson no sabe guardar: lo dirá Mongo al escribir; aquí solo se mide el tamaño
        return
    if tamano > MAX_BYTES:
        raise ErrorCrm(413, "Tu CRM ya es demasiado grande para guardar este cambio. Quita registros que no uses (o importaciones viejas) e inténtalo de nuevo.")


def _col(db):
    return db[Collections.CRM]


async def obtener(db, user_id: str, ahora=None) -> dict | None:
    """El CRM de la persona, al día: se normaliza y se corre lo que las automatizaciones tengan pendiente (se guarda solo si hubo algo)."""
    doc = await _col(db).find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return None
    doc = automatizaciones.normalizar(normalizar(doc))
    nuevo, cambio = automatizaciones.ejecutar_pendientes(doc, ahora)
    if not cambio:
        return doc
    guardado = await guardar_version(db, user_id, nuevo, doc["version"])
    return guardado or doc  # si alguien lo cambió en medio, se devuelve lo que había: la próxima lectura lo reintenta


async def reemplazar(db, user_id: str, doc: dict) -> dict:
    """Crea el CRM o lo reemplaza por completo (al repetir el cuestionario)."""
    await _col(db).replace_one({"user_id": user_id}, doc, upsert=True)
    return doc


async def borrar(db, user_id: str) -> None:
    await _col(db).delete_one({"user_id": user_id})


async def guardar_version(db, user_id: str, nuevo: dict, version_base: int) -> dict | None:
    """Guarda `nuevo` solo si el CRM sigue en `version_base`. Devuelve lo guardado, o None si alguien lo cambió en medio."""
    nuevo = {**nuevo, "version": version_base + 1, "updated_at": ahora_utc()}
    _cabe(nuevo)
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
        _cabe(nuevo)
        res = await _col(db).replace_one({"user_id": user_id, "version": doc["version"]}, nuevo)
        if res.matched_count == 1:
            return nuevo
    raise ErrorCrm(409, "Tu CRM cambió mientras guardábamos. Inténtalo de nuevo.")


# ───────── Puntos de deshacer (colección `crm_puntos`) ─────────

def _puntos(db):
    return db[Collections.CRM_PUNTOS]


async def puntos_agregar(db, user_id: str, punto: dict) -> None:
    """Guarda un punto y deja solo los últimos MAX_PUNTOS de la persona."""
    await _puntos(db).insert_one({**punto, "user_id": user_id})
    viejos = await _puntos(db).find({"user_id": user_id}, {"_id": 0, "n": 1}).sort("n", -1).skip(MAX_PUNTOS).to_list(length=None)
    if viejos:
        await _puntos(db).delete_many({"user_id": user_id, "n": {"$lte": max(x["n"] for x in viejos)}})


async def puntos_listar(db, user_id: str, con_foto: bool = False) -> list[dict]:
    """Los puntos de la persona, del más viejo al más nuevo. Sin foto, salvo que se pida (para deshacer)."""
    proyeccion = {"_id": 0, "user_id": 0} if con_foto else {"_id": 0, "user_id": 0, "foto": 0}
    return await _puntos(db).find({"user_id": user_id}, proyeccion).sort("n", 1).to_list(length=None)


async def puntos_obtener(db, user_id: str, n: int) -> dict | None:
    return await _puntos(db).find_one({"user_id": user_id, "n": n}, {"_id": 0, "user_id": 0})


async def puntos_borrar_desde(db, user_id: str, n: int) -> None:
    """Borra los puntos `n` y posteriores (con n=0, todos: al rehacer o borrar el CRM)."""
    await _puntos(db).delete_many({"user_id": user_id, "n": {"$gte": n}})


async def puntos_reponer(db, user_id: str, desde_n: int, quedan: list[dict]) -> None:
    """Tras deshacer: borra del punto `desde_n` en adelante y vuelve a poner los posteriores que se quedan (con su foto ajustada)."""
    await puntos_borrar_desde(db, user_id, desde_n)
    for x in sorted((x for x in quedan if x["n"] > desde_n), key=lambda x: x["n"]):
        await _puntos(db).insert_one({**x, "user_id": user_id})


# ───────── Logo del negocio (colección `crm_logos`) ─────────
# El CRM solo guarda `marca.logo_id`; la imagen vive aquí, una por id (el id sale del contenido: la misma imagen, el mismo id).

def _logos(db):
    return db[Collections.CRM_LOGOS]


async def logo_guardar(db, user_id: str, logo: dict) -> None:
    await _logos(db).replace_one({"user_id": user_id, "id": logo["id"]},
                                 {"user_id": user_id, "id": logo["id"], "imagen": logo["imagen"]}, upsert=True)


async def logo_obtener(db, user_id: str, logo_id: str) -> dict | None:
    """{id, imagen} del logo de la persona, o None."""
    return await _logos(db).find_one({"user_id": user_id, "id": logo_id}, {"_id": 0, "user_id": 0})


async def logos_borrar(db, user_id: str) -> None:
    await _logos(db).delete_many({"user_id": user_id})
