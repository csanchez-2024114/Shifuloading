"""Operaciones sobre el CRM (agregar, cambiar, quitar).

Son funciones puras: reciben el documento del CRM y devuelven uno nuevo, sin tocar el original. Si algo no se puede
hacer lanzan `ErrorCrm`, que las rutas convierten en una respuesta HTTP.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

from app.crm.secciones import ETAPAS, IDS_COLUMNA, IDS_SECCION, titulo_seccion

MAX_EVENTOS = 30
MAX_CONTACTOS = 5000  # tope por CRM mientras los contactos vivan dentro del mismo documento


class ErrorCrm(Exception):
    """Algo que el usuario pidió y no se puede hacer. `estado` es el código HTTP que le corresponde."""

    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado
        self.mensaje = mensaje


def nuevo_id() -> str:
    return uuid.uuid4().hex


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _registrar(doc: dict, emoji: str, texto: str, ahora: datetime) -> None:
    doc["eventos"] = [{"id": nuevo_id(), "e": emoji, "t": texto, "ts": ahora}, *doc["eventos"]][:MAX_EVENTOS]


def _copia(doc: dict) -> dict:
    return copy.deepcopy(doc)


# ───────── Contactos ─────────

def contactos_crear(doc: dict, filas: list[dict], canal: str, texto: str | None = None, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    if not filas:
        raise ErrorCrm(422, "No hay contactos para agregar.")
    if doc["total_contactos"] + len(filas) > MAX_CONTACTOS:
        raise ErrorCrm(422, f"Un CRM admite hasta {MAX_CONTACTOS} contactos por ahora.")
    out = _copia(doc)
    nuevos = [{
        "id": nuevo_id(), "n": f["n"], "det": f.get("det") or None, "canal": f.get("canal") or canal,
        "etapa": "Nuevo", "dueno": out["vendedores"][0], "ultimo_contacto": ahora,
    } for f in filas]
    out["contactos"] = [*nuevos, *out["contactos"]]
    out["total_contactos"] += len(nuevos)
    _registrar(out, "➕", texto or (f"Agregaste a {nuevos[0]['n']}" if len(nuevos) == 1 else f"Agregaste {len(nuevos)} contactos"), ahora)
    return out


def contactos_actualizar(doc: dict, contacto_id: str, cambios: dict[str, Any], texto: str | None = None, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    c = next((x for x in out["contactos"] if x["id"] == contacto_id), None)
    if c is None:
        raise ErrorCrm(404, "Ese contacto no existe.")
    if "etapa" in cambios and cambios["etapa"] not in ETAPAS:
        raise ErrorCrm(422, f"La etapa debe ser una de: {', '.join(ETAPAS)}.")
    if "dueno" in cambios and cambios["dueno"] not in out["vendedores"]:
        raise ErrorCrm(422, "Esa persona no está en tu equipo.")
    anterior = dict(c)
    for campo in ("n", "det", "canal", "etapa", "dueno"):
        if campo in cambios:
            c[campo] = cambios[campo]
    if "etapa" in cambios and cambios["etapa"] != anterior["etapa"]:
        c["ultimo_contacto"] = ahora  # pasar de etapa cuenta como contacto reciente
    if texto is None:
        if c["etapa"] != anterior["etapa"]:
            texto = f"{c['n']} pasó a “{c['etapa']}”"
        elif c["n"] != anterior["n"]:
            texto = f"{anterior['n']} ahora se llama {c['n']}"
        else:
            texto = f"Actualizaste a {c['n']}"
    _registrar(out, "🔁", texto, ahora)
    return out


def contactos_eliminar(doc: dict, contacto_id: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    c = next((x for x in out["contactos"] if x["id"] == contacto_id), None)
    if c is None:
        raise ErrorCrm(404, "Ese contacto no existe.")
    out["contactos"] = [x for x in out["contactos"] if x["id"] != contacto_id]
    out["total_contactos"] = max(0, out["total_contactos"] - 1)
    _registrar(out, "🗑️", f"Eliminaste a {c['n']}", ahora)
    return out


# ───────── Tareas ─────────

def _buscar_tarea(doc: dict, tarea_id: str) -> tuple[str, dict] | None:
    for col in IDS_COLUMNA:
        for x in doc["tareas"][col]:
            if x["id"] == tarea_id:
                return col, x
    return None


def tareas_crear(doc: dict, texto_tarea: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    out["tareas"]["porHacer"].append({"id": nuevo_id(), "t": texto_tarea})
    _registrar(out, "✅", f"Agregaste la tarea “{texto_tarea}”", ahora)
    return out


def tareas_mover(doc: dict, tarea_id: str, destino: str) -> dict:
    if destino not in IDS_COLUMNA:
        raise ErrorCrm(422, f"La columna debe ser una de: {', '.join(IDS_COLUMNA)}.")
    out = _copia(doc)
    hit = _buscar_tarea(out, tarea_id)
    if hit is None:
        raise ErrorCrm(404, "Esa tarea no existe.")
    col, tarea = hit
    if col != destino:
        out["tareas"][col] = [x for x in out["tareas"][col] if x["id"] != tarea_id]
        out["tareas"][destino].append(tarea)
    return out


def tareas_eliminar(doc: dict, tarea_id: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    hit = _buscar_tarea(out, tarea_id)
    if hit is None:
        raise ErrorCrm(404, "Esa tarea no existe.")
    col, tarea = hit
    out["tareas"][col] = [x for x in out["tareas"][col] if x["id"] != tarea_id]
    _registrar(out, "🗑️", f"Eliminaste la tarea “{tarea['t']}”", ahora)
    return out


# ───────── Automatizaciones y secciones ─────────

def automatizacion_fijar(doc: dict, auto_id: str, on: bool, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    out = _copia(doc)
    a = next((x for x in out["automatizaciones"] if x["id"] == auto_id), None)
    if a is None:
        raise ErrorCrm(404, "Esa automatización no existe.")
    if a["on"] != on:
        a["on"] = on
        _registrar(out, "⚡" if on else "⏸️", f"{'Activaste' if on else 'Apagaste'}: {a['t']}", ahora)
    return out


def seccion_renombrar(doc: dict, seccion_id: str, nombre: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    if seccion_id not in IDS_SECCION:
        raise ErrorCrm(404, "Esa sección no existe.")
    out = _copia(doc)
    rubro = (out.get("brief") or {}).get("rubro")
    anterior = titulo_seccion(rubro, seccion_id, out["secciones"])
    out["secciones"][seccion_id] = nombre
    _registrar(out, "✏️", f"Renombraste “{anterior}” a “{nombre}”", ahora)
    return out
