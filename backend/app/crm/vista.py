"""Convierte el documento interno del CRM en la forma que espera el frontend (ver `API.md`).

Los tiempos se guardan como fechas reales y aquí se vuelven textos relativos ("hace 5 min", "hace 2 días"): así siempre
están al día, sin que nadie tenga que reescribirlos.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.crm.operaciones import ahora_utc


def _utc(d: datetime) -> datetime:
    # Mongo devuelve fechas sin zona horaria (siempre UTC): se les vuelve a poner.
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def hace(ts: datetime, ahora: datetime) -> str:
    seg = max(0, int((ahora - _utc(ts)).total_seconds()))
    if seg < 60:
        return "ahora"
    if seg < 3600:
        return f"hace {seg // 60} min"
    if seg < 86400:
        return f"hace {seg // 3600} h"
    dias = seg // 86400
    return f"hace {dias} {'día' if dias == 1 else 'días'}"


def vista_crm(doc: dict, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    return {
        "brief": doc["brief"],
        "totalContactos": doc["total_contactos"],
        "contactos": [{
            "id": c["id"], "n": c["n"], "det": c.get("det"), "canal": c["canal"], "etapa": c["etapa"], "dueno": c["dueno"],
            "dias": max(0, (ahora - _utc(c["ultimo_contacto"])).days),
        } for c in doc["contactos"]],
        "vendedores": doc["vendedores"],
        "tareas": doc["tareas"],
        "eventos": [{"id": e["id"], "e": e["e"], "t": e["t"], "h": hace(e["ts"], ahora)} for e in doc["eventos"]],
        "automatizaciones": doc["automatizaciones"],
        "secciones": doc["secciones"],
    }
