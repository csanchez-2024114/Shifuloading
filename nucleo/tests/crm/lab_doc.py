"""Ayuda de pruebas: el documento del CRM equivalente a un estado del laboratorio (plantilla + estado), y la traducción de vuelta.

- Cada sección de la plantilla con campos es una lista `l_<id>` (contrato §1); las que tienen `fuente` no existen en el CRM.
- Contactos, tareas, cobros e importar quedan ocultos: la pantalla tiene solo lo de la plantilla (y Historial, Equipo y
  Automatizaciones, las fijas de Carlos que también tiene el laboratorio).
- `bloques` → `inicio`, `estructura.paginas` → `paginas` (con los ids con `l_`), `marca` → `marca`, `vista` → la del contexto.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone

from assistant.packs.crm import estructura, plantillas
from assistant.packs.crm.generador import generar

AHORA = datetime(2026, 10, 16, 18, 0, tzinfo=timezone.utc)
OCULTAS = ["contactos", "desarrollo", "cobros", "importar"]


def l_(sid: str) -> str:
    return f"l_{sid}"


def _bloque(b: dict) -> dict:
    out = {**copy.deepcopy(b), "seccion": l_(b["seccion"])}
    if str(b.get("uid", "")).startswith("p_"):
        out["uid"] = f"p_{l_(b['uid'][2:])}"
    return out


def doc_de_lab(plantilla_id: str, estado: dict) -> tuple[dict, dict]:
    """(doc, contexto) equivalentes al estado del laboratorio."""
    p = plantillas.plantilla_por_id(plantilla_id)
    doc = estructura.normalizar(generar("u1", {"nombre": "Prueba", "rubro": "salud", "equipo": "solo"}, AHORA))
    doc["ocultas"] = list(OCULTAS)
    doc["plantilla"] = {"id": plantilla_id, "origen": "asignar", "porque": []}
    for s in p["secciones"]:
        if s.get("campos") is None or s.get("fuente"):
            continue
        l = {"id": l_(s["id"]), "nombre": s["titulo"], "campos": [{k: c[k] for k in ("id", "nombre", "tipo", "opciones") if k in c} for c in s["campos"]],
             "registros": [], "vista": s.get("vista") or "tabla", "icono": s.get("icono") or "tabla", "grupo": s.get("grupo", 0)}
        if s.get("opciones"):
            l["opciones"] = s["opciones"]
        doc["listas"].append(l)
    doc["inicio"] = [_bloque(b) for b in estado.get("bloques") or []]
    doc["paginas"] = {l_(k): [_bloque(b) for b in bs] for k, bs in ((estado.get("estructura") or {}).get("paginas") or {}).items()}
    doc["marca"] = copy.deepcopy(estado.get("marca") or {})
    if estado.get("toma"):
        doc["toma"] = copy.deepcopy(estado["toma"])
    vista = estado.get("vista") or "inicio"
    return doc, {"vista": vista if vista == "inicio" else l_(vista)}


def args_de_lab(args: dict) -> dict:
    """Los args del modelo con los ids del CRM: solo cambian las piezas por defecto de una pestaña (p_miembros → p_l_miembros).
    `seccion` y `pestana` se dejan como en el laboratorio: edicion.py acepta el id sin `l_`."""
    out = copy.deepcopy(args)
    if isinstance(out.get("bloque"), str) and out["bloque"].startswith("p_"):
        out["bloque"] = f"p_{l_(out['bloque'][2:])}"
    return out


_L = re.compile(r"(^|[^a-z0-9])(p_)?l_")
_UID = re.compile(r"\bn[0-9a-z]{11}\b")  # n + Date.now() en base 36 (8) + 3 al azar


def a_lab(x, uids: dict | None = None):
    """Lo del CRM con el vocabulario del laboratorio: sin el prefijo `l_` y con los uid nuevos numerados (NUEVO1, NUEVO2…)."""
    texto = json.dumps(x, ensure_ascii=False)
    texto = _L.sub(lambda m: m.group(1) + (m.group(2) or ""), texto)
    return json.loads(uids_en_orden(texto, uids))


def uids_en_orden(texto: str, uids: dict | None = None) -> str:
    uids = {} if uids is None else uids
    return _UID.sub(lambda m: uids.setdefault(m.group(0), f"NUEVO{len(uids) + 1}"), texto)
