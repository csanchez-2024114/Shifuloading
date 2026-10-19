"""El cerco de las vistas: qué vistas existen y qué exige cada una (port de `laboratorio/src/plantillas/validar.js`).

Funciones puras, sin pantalla ni base de datos. Una plantilla (o un cambio que pida la IA) que no lo cumple se rechaza con un mensaje
legible, en vez de dibujarse mal. Los textos son LITERALES del laboratorio: el modelo se midió leyendo esos.

- `VISTAS` es el catálogo compartido `catalogos/vistas.json` (lo genera `exportar-catalogos.mjs` desde `validar.js`).
- `revisar_vista`, `normalizar_opciones`, `campos_de` y `validar_plantilla` son `revisarVista`, `normalizarOpciones`, `camposDe` y
  `validarPlantilla`, con la «verdad» de JS (una lista o un objeto vacío cuentan como verdaderos; 0 y "" no).
"""
from __future__ import annotations

import math
from typing import Any

from app.crm import plantillas

TIPOS_CAMPO = ["texto", "numero", "dinero", "fecha", "hora", "estado"]
VISTAS: dict[str, dict] = plantillas.vistas()  # vista → {requiere, opcional, libre?, datos?}; de solo lectura


def verdad(x: Any) -> bool:
    """Lo «verdadero» de JS: listas y objetos vacíos cuentan como verdaderos; None, 0, "", False y NaN no."""
    if isinstance(x, (dict, list)):
        return True
    if isinstance(x, float) and math.isnan(x):
        return False
    return bool(x)


def campos_de(s: dict, por_id: dict) -> list[dict]:
    """Una sección con `fuente` muestra los registros de otra: usa los campos de esa otra."""
    if verdad(s.get("fuente")):
        return (por_id.get(s["fuente"]) or {}).get("campos") or []
    return s.get("campos") or []


def normalizar_opciones(vista: str, opciones: Any = None) -> Any:
    """Opciones que apuntan a UN campo: si el modelo manda una lista de un solo id (["monto"]), se toma ese id (calculable).
    Medido: «suma: ["monto"]» daba «el campo monto no existe» y el modelo terminaba creando campos que ya había."""
    if opciones is None:
        opciones = {}
    d = VISTAS.get(vista)
    if not d or d.get("libre") or not verdad(opciones):
        return opciones
    de_campo = {**d.get("requiere", {}), **{k: t for k, t in (d.get("opcional") or {}).items() if t != "libre" and t is not None}}
    out = dict(opciones)
    for op in de_campo:
        v = out.get(op)
        if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str):
            out[op] = v[0]
    return out


def revisar_vista(vista: str, opciones: Any, campos: list[dict], donde: str) -> list[str]:
    """Errores de una vista con sus opciones sobre esos campos (vacío = está bien)."""
    d = VISTAS.get(vista)
    if not d:
        return [f"{donde}: la vista «{vista}» no está en el catálogo ({', '.join(VISTAS)})."]
    if d.get("datos") is False or d.get("libre"):
        return []
    opciones = opciones if isinstance(opciones, dict) else {}
    errores: list[str] = []

    def tipo_de(i: Any) -> Any:
        return next((c.get("tipo") for c in campos if c.get("id") == i), None)

    for op, tipos in d["requiere"].items():
        v = opciones.get(op)
        if not verdad(v):
            errores.append(f"{donde}: la vista «{vista}» necesita la opción «{op}».")
            continue
        if isinstance(v, list):
            errores.append(f"{donde}: «{op}» debe ser el id de UN campo (texto), no una lista.")
        elif not verdad(tipo_de(v)):
            errores.append(f"{donde}: «{op}» apunta al campo «{_js(v)}», que no existe.")
        elif tipos and tipo_de(v) not in tipos:
            errores.append(f"{donde}: «{op}» debe ser un campo de tipo {' o '.join(tipos)}, y «{_js(v)}» es {tipo_de(v)}.")
    for op, tipos in (d.get("opcional") or {}).items():
        v = opciones.get(op)
        if tipos == "libre" or not verdad(v) or not isinstance(v, str) or op in ("dias", "excluir", "orden"):
            continue
        if not verdad(tipo_de(v)):
            errores.append(f"{donde}: «{op}» apunta al campo «{v}», que no existe.")
        elif tipos and tipo_de(v) not in tipos:
            errores.append(f"{donde}: «{op}» debe ser un campo de tipo {' o '.join(tipos)}.")
    for op in opciones:
        if op not in d["requiere"] and op not in (d.get("opcional") or {}) and op not in ("dias", "tipo"):
            errores.append(f"{donde}: la vista «{vista}» no tiene la opción «{op}».")
    return errores


def validar_plantilla(p: dict) -> list[str]:
    """Errores de la plantilla completa {id, nombre, secciones, inicio?} (vacío = es válida)."""
    errores: list[str] = []
    if not verdad((p or {}).get("id")) or not verdad((p or {}).get("nombre")):
        errores.append("La plantilla necesita id y nombre.")
    secciones = (p or {}).get("secciones") or []
    por_id = {s.get("id"): s for s in secciones}
    ids: set = set()
    for s in secciones:
        if s.get("id") in ids:
            errores.append(f"Hay dos secciones con el id «{s.get('id')}».")
        ids.add(s.get("id"))
        for c in s.get("campos") or []:
            if c.get("tipo") not in TIPOS_CAMPO:
                errores.append(f"«{s.get('titulo')}»: el campo «{c.get('nombre')}» tiene un tipo desconocido ({c.get('tipo')}).")
            if c.get("tipo") == "estado" and not len(c.get("opciones") or []) >= 2:
                errores.append(f"«{s.get('titulo')}»: el campo de estado «{c.get('nombre')}» necesita al menos 2 opciones.")
        errores.extend(revisar_vista(s.get("vista"), s.get("opciones"), campos_de(s, por_id), f"«{s.get('titulo')}»"))
    for i, w in enumerate((p or {}).get("inicio") or []):
        s = por_id.get(w.get("seccion"))
        if not s:
            errores.append(f"Inicio, bloque {i + 1}: la sección «{w.get('seccion')}» no existe.")
            continue
        errores.extend(revisar_vista(w.get("vista"), w.get("opciones"), campos_de(s, por_id),
                                     f"Inicio, bloque {i + 1} ({w.get('vista')} de «{s.get('titulo')}»)"))
    return errores


def _js(v: Any) -> str:
    """`${v}` de JS para lo que llega en una opción (números enteros sin «.0», booleanos en minúscula)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, dict):
        return "[object Object]"
    return str(v)
