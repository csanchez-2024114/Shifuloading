"""Convierte el documento interno del CRM en la forma que espera el frontend (ver `API.md`).

Los tiempos se guardan como fechas reales y aquí se vuelven textos relativos ("hace 5 min", "hace 2 días"): así siempre
están al día, sin que nadie tenga que reescribirlos.
"""
from __future__ import annotations

from datetime import datetime, timezone

from assistant.packs.crm import automatizaciones
from assistant.packs.crm import calculos
from assistant.packs.crm.estructura import ESQUEMA, esquema2_faltante
from assistant.packs.crm.operaciones import ahora_utc, hora_local

# Lo opcional de cada lista (esquema 2) que llega a la pantalla, con su nombre en camelCase.
_LISTA_V2 = (("vista", "vista"), ("opciones", "opciones"), ("icono", "icono"), ("grupo", "grupo"), ("ficha", "ficha"), ("tarjeta", "tarjeta"),
             ("opciones_estado", "opcionesEstado"), ("origen", "origen"))


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


def _tarea(x: dict, nombres: dict[str, str]) -> dict:
    """La tarea tal como la ve el frontend: con su fecha, hora y el nombre del contacto si los tiene."""
    salida = {"id": x["id"], "t": x["t"]}
    if x.get("vence"):
        salida["vence"] = x["vence"]
        if x.get("hora"):
            salida["hora"] = x["hora"]
    if x.get("contacto_id") in nombres:
        salida["contacto"] = nombres[x["contacto_id"]]
    if x.get("auto"):
        salida["auto"] = True  # la creó una automatización, no la persona
    return salida


def _registro(r: dict) -> dict:
    return {"id": r["id"], "valores": r["valores"], **({"ejemplo": True} if r.get("ejemplo") else {})}


def _lista_v2(l: dict) -> dict:
    return {nuevo: l[viejo] for viejo, nuevo in _LISTA_V2 if l.get(viejo) is not None}


def vista_puntos(puntos: list[dict]) -> list[dict]:
    """Los puntos de deshacer para la pantalla: los últimos 30, sin foto."""
    return [{"n": p["n"], "antesDe": p.get("antes_de", ""), "hora": p.get("hora"), "cambio": p.get("cambio") or []}
            for p in sorted(puntos, key=lambda x: x["n"])[-30:]]


def vista_crm(doc: dict, ahora: datetime | None = None, puntos: list[dict] | None = None) -> dict:
    """Un CRM de esquema 2 (ya normalizado) suma lo del sistema de diseño; uno de antes sale exactamente como siempre.
    `puntos` (opcional): la lista de `crm_puntos`; si se pasa, sale en `puntos` (sin foto)."""
    # Los calculados (calculos.py) se llenan aquí, al leer: la pantalla los ve como cualquier número o dinero, y nunca se guardan.
    doc = calculos.con_calculos(doc, hora_local(ahora or ahora_utc(), doc).date())
    salida = _vista_v1(doc, ahora)
    if (doc.get("esquema") or 1) >= ESQUEMA:
        v2 = {**{k: doc.get(k) for k in ("plantilla", "inicio", "paginas", "marca", "toma")}, **esquema2_faltante(doc)}
        salida.update(esquema=doc["esquema"], plantilla=v2["plantilla"], inicio=v2["inicio"], paginas=v2["paginas"], marca=v2["marca"], toma=v2["toma"])
        if doc.get("saludo_ejemplos"):  # pedidos de ejemplo del saludo, con las secciones que de verdad se crearon (lista 29)
            salida["saludoEjemplos"] = list(doc["saludo_ejemplos"])
    if puntos is not None:
        salida["puntos"] = vista_puntos(puntos)
    return salida


def _vista_v1(doc: dict, ahora: datetime | None = None) -> dict:
    ahora = ahora or ahora_utc()
    nombres = {c["id"]: c["n"] for c in doc["contactos"]}
    return {
        "brief": doc["brief"],
        "totalContactos": doc["total_contactos"],
        "contactos": [{
            "id": c["id"], "n": c["n"], "det": c.get("det"), "canal": c["canal"], "etapa": c["etapa"], "dueno": c["dueno"],
            "dias": max(0, (ahora - _utc(c["ultimo_contacto"])).days), "extra": c.get("extra") or {},
        } for c in doc["contactos"]],
        "etapas": doc["etapas"],
        "camposContacto": doc["campos_contacto"],
        "ocultas": doc["ocultas"],
        "listas": [{"id": l["id"], "nombre": l["nombre"], "tipo": l.get("tipo"), "campos": l["campos"], **_lista_v2(l),
                    "registros": [_registro(r) for r in l["registros"]],
                    # Las importaciones que siguen teniendo registros (si ya se borraron todos a mano, no se muestra).
                    "importaciones": [{"id": i["id"], "nombre": i["nombre"], "creado": i["creado"].isoformat() if hasattr(i["creado"], "isoformat") else str(i["creado"]),
                                       "cantidad": sum(1 for r in l["registros"] if r.get("lote") == i["id"])}
                                      for i in l.get("importaciones", []) if any(r.get("lote") == i["id"] for r in l["registros"])]} for l in doc["listas"]],
        "vendedores": doc["vendedores"],
        "tareas": {col: [_tarea(x, nombres) for x in lista] for col, lista in doc["tareas"].items()},
        "eventos": [{"id": e["id"], "e": e["e"], "t": e["t"], "h": hace(e["ts"], ahora)} for e in doc["eventos"]],
        "automatizaciones": [{**a, **automatizaciones.detalle(a["id"])} for a in doc["automatizaciones"]],
        "secciones": doc["secciones"],
        "resumenIA": doc.get("resumen_ia"),
    }
