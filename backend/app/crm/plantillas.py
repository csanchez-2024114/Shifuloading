"""Catálogos del sistema de diseño del laboratorio (D61, contrato §5), leídos de `app/crm/catalogos/*.json`.

Los JSON los genera `laboratorio/servidor/exportar-catalogos.mjs` desde los JS del laboratorio (la fuente mientras viva) y se
commitean; `test/crm/test_catalogos.py` falla si quedan viejos. Aquí solo se leen (una vez por proceso) y se consultan.

- `semillas()`, `biblioteca()`, `pestanas()`, `graficos()`, `vistas()`, `iconos()`, `fuentes()` devuelven el objeto en memoria,
  compartido: es de SOLO LECTURA (si lo vas a cambiar, `copy.deepcopy`).
- `plantilla_por_id(id)` devuelve una COPIA (se puede sembrar y cambiar sin tocar el catálogo), igual que `plantillaPorId`
  de `semillas.js`: primero las semillas, luego la biblioteca y, con `pestana-<id>`, la pestaña de la biblioteca vista sola.
- `compatibles(campos)` y `opciones_por_defecto(tipo, campos)` son el port de `graficos-catalogo.js` (mismas reglas, ver
  allí); se verifican contra `test/crm/fixtures/lab/compatibles.json`.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CARPETA = Path(__file__).resolve().parent / "catalogos"
_VISTAS_FIJAS = ("feed", "equipo", "interruptores")  # Historial, Equipo y Automatizaciones: van al final de cada plantilla


@lru_cache(maxsize=None)
def _leer(nombre: str) -> Any:
    with open(CARPETA / f"{nombre}.json", encoding="utf-8") as f:
        return json.load(f)


def semillas() -> list[dict]:
    """Las 6 plantillas de `semillas.js`, en su orden."""
    return _leer("plantillas")["semillas"]


def biblioteca() -> list[dict]:
    """Las 21 plantillas de `biblioteca/*.js`, por id."""
    return _leer("plantillas")["biblioteca"]


def pestanas() -> list[dict]:
    """Las 35 plantillas de pestaña (`biblioteca-pestanas/*.js`): {id, para, palabras, seccion, piezas}, por id."""
    return _leer("pestanas")


def graficos() -> dict[str, dict]:
    """{tipo: {nombre, familia, requiere, opciones, html?}} en el orden de `compatibles()`."""
    return _leer("graficos")


def vistas() -> dict[str, dict]:
    """`VISTAS` de `validar.js`: qué opciones pide cada vista y de qué tipo de campo."""
    return _leer("vistas")


def iconos() -> dict:
    """{familias, iconos}: el catálogo de íconos (concepto → nombre por familia y estilo)."""
    return _leer("iconos")


def fuentes() -> dict:
    """{fuentes, pares}: el catálogo de tipografías."""
    return _leer("fuentes")


@lru_cache(maxsize=None)
def _por_id() -> dict[str, dict]:
    tabla: dict[str, dict] = {}
    for p in [*semillas(), *biblioteca()]:
        tabla.setdefault(p["id"], p)  # como PLANTILLAS: si una de biblioteca repite un id de semilla, gana la semilla
    fijas = [s for s in semillas()[0]["secciones"] if s.get("vista") in _VISTAS_FIJAS]
    for p in pestanas():
        # Como PESTANAS_VISTA de semillas.js: un CRM mínimo con esa pestaña y sus piezas sugeridas en el inicio.
        tabla.setdefault(f"pestana-{p['id']}", {
            "id": f"pestana-{p['id']}", "nombre": p["seccion"]["titulo"], "para": p.get("para"), "interna": "pestana",
            "inicio": [{**w, "seccion": p["id"]} for w in p.get("piezas", [])],
            "secciones": [{**p["seccion"], "id": p["id"], "grupo": 0}, *fijas],
        })
    return tabla


def plantilla_por_id(plantilla_id: str) -> dict | None:
    """Copia de la plantilla (semilla, biblioteca o `pestana-<id>`), o None si no existe."""
    p = _por_id().get(plantilla_id)
    return copy.deepcopy(p) if p is not None else None


# ── Port de compatibles() (graficos-catalogo.js) ──────────────────────────────────────────────────────────────────────
# «Sin definir» de JS: una opción que vale esto no se escribe en el resultado (y tapa la de base, como `{...b, ...o}`).
_SIN = object()

_CLASES = {
    "estado": lambda c: c.get("tipo") == "estado",
    "estado3": lambda c: c.get("tipo") == "estado" and len(c.get("opciones") or []) >= 3,
    "fecha": lambda c: c.get("tipo") == "fecha",
    "hora": lambda c: c.get("tipo") == "hora",
    "medida": lambda c: c.get("tipo") in ("numero", "dinero"),
    "texto": lambda c: c.get("tipo") == "texto",
    "categoria": lambda c: c.get("tipo") in ("estado", "texto"),
}


def _de_clase(clase: str, campos: list[dict]) -> list[dict]:
    regla = _CLASES.get(clase)
    return [c for c in campos if regla(c)] if regla else []  # clase desconocida: no la cumple ningún campo


def cumple(requiere: dict | list, campos: list[dict]) -> bool:
    """Basta con cumplir UNA alternativa; una alternativa pide al menos n campos de cada clase."""
    alternativas = requiere if isinstance(requiere, list) else [requiere]
    return any(all(len(_de_clase(cl, campos)) >= n for cl, n in alt.items()) for alt in alternativas)


def base(campos: list[dict]) -> dict[str, Any]:
    """Campos que se eligen solos (sin definir = _SIN): 1.er estado, 1.a y 2.a fecha, 1.a hora, 1.a y 2.a medida
    (dinero antes que número), 1.er texto, y agrupar = estado o texto."""
    primero = lambda xs, i=0: xs[i]["id"] if len(xs) > i else _SIN  # noqa: E731
    medidas = [c for c in campos if c.get("tipo") == "dinero"] + [c for c in campos if c.get("tipo") == "numero"]
    estado, texto = primero(_de_clase("estado", campos)), primero(_de_clase("texto", campos))
    fechas = _de_clase("fecha", campos)
    return {"estado": estado, "fecha": primero(fechas), "fecha2": primero(fechas, 1), "hora": primero(_de_clase("hora", campos)),
            "valor": primero(medidas), "valor2": primero(medidas, 1), "texto": texto,
            "agrupar": estado if _con_valor(estado) else texto}


def _con_valor(v: Any) -> bool:
    """Verdadero de JS para lo que puede salir de base(): un id no vacío."""
    return v is not _SIN and bool(v)


def _valor_de(x: Any, b: dict, campos: list[dict]) -> Any:
    """Expresión de `opciones` del catálogo (formas documentadas en graficos-catalogo.js → valorDe)."""
    if isinstance(x, list):
        return list(x)
    if not isinstance(x, dict):
        return x
    if "primero" in x:
        for k in x["primero"]:
            if _con_valor(b.get(k, _SIN)):
                return b[k]
        return _valor_de(x["si_no"], b, campos) if "si_no" in x else _SIN
    if "si" in x:
        rama = "entonces" if _con_valor(b.get(x["si"], _SIN)) else "si_no"
        return _valor_de(x[rama], b, campos) if rama in x else _SIN
    if "clase" in x:
        xs = _de_clase(x["clase"], campos)
        return xs[0]["id"] if xs else _SIN
    return x


def opciones_por_defecto(tipo: str, campos: list[dict]) -> dict[str, Any]:
    """{...base, ...opciones del tipo}; lo «sin definir» no se escribe. Tipo desconocido → solo base."""
    b = base(campos)
    todo = dict(b)
    g = graficos().get(tipo)
    if g:
        todo.update({k: _valor_de(x, b, campos) for k, x in (g.get("opciones") or {}).items()})
    return {k: v for k, v in todo.items() if v is not _SIN}


def compatibles(campos: list[dict]) -> list[dict]:
    """Tipos del catálogo (en su orden) que se pueden dibujar con estos campos, con sus opciones por defecto."""
    return [{"id": tipo, "nombre": g["nombre"], "familia": g["familia"], "requiere": g["requiere"], "opciones": opciones_por_defecto(tipo, campos)}
            for tipo, g in graficos().items() if cumple(g["requiere"], campos)]
