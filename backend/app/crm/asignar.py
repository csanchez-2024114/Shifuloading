"""Regla de asignación (D23): con las respuestas del cuestionario se elige la plantilla de base. Copia de
`laboratorio/src/plantillas/asignar.js`.

La decide el CÓDIGO (rápida, predecible y explicable); la IA solo la cambia si la persona pide otra cosa. Puntaje por plantilla según sus
metadatos `asignacion`: rubro +3, ciclo +2, cada objetivo +1, y las palabras de «qué vendes» que aparecen en su nombre, su «para» o sus
ejemplos de negocio +2 cada una (hasta 2). Devuelve las 3 mejores con el porqué en palabras.

El catálogo de plantillas entra como argumento (`plantillas`: la lista de `catalogos/plantillas.json`, semillas + biblioteca, en ese
orden: el orden decide los empates).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_COMBINANTES = re.compile("[̀-ͯ]")
_NO_LETRA = re.compile(r"[^a-zñ]+")


def _norm(t: Any) -> str:
    return _COMBINANTES.sub("", unicodedata.normalize("NFD", str(t or "").lower()))


def _palabras(t: Any) -> list[str]:
    return [w for w in _NO_LETRA.split(_norm(t)) if len(w) > 3]


def asignar(respuestas: dict | None, plantillas: list[dict]) -> dict:
    """respuestas = {rubro, ciclo, objetivos: [str], que_vendes (o queVendes): str}.

    Devuelve {recomendada: opción | None, opciones: [hasta 3 opciones], ambiguo: bool}; cada opción = {id, nombre, puntos, porque: [str]}.
    `ambiguo` (D6): sin una ganadora clara (empate arriba o menos de 3 puntos) se muestran opciones en vez de adivinar.
    """
    r = respuestas or {}
    rubro, ciclo = r.get("rubro"), r.get("ciclo")
    objetivos = r.get("objetivos") or []
    que_vendes = r.get("que_vendes", r.get("queVendes", "")) or ""
    pv = list(dict.fromkeys(_palabras(que_vendes)))  # sin repetir, en el orden en que las escribió (como un Set de JS)
    res = []
    for p in plantillas:
        a = p.get("asignacion")
        if not a:
            continue
        por: list[str] = []
        pts = 0
        if rubro in a["rubros"]:
            pts += 3
            por.append("tu rubro")
        if ciclo in a["ciclos"]:
            pts += 2
            por.append("tu forma de vender")
        obj = [o for o in objetivos if o in (a.get("objetivos") or [])]
        if obj:
            pts += len(obj)
            por.append(f"{len(obj)} de tus objetivos")
        suyas = _palabras(" ".join("" if x is None else str(x) for x in [p.get("nombre"), p.get("para"), *a["negocios"]]))
        coincide = [w for w in pv if w in suyas]
        if coincide:
            pts += 2 * min(2, len(coincide))
            por.append("lo que vendes («" + "», «".join(coincide[:2]) + "»)")
        res.append({"id": p["id"], "nombre": p.get("nombre"), "puntos": pts, "porque": por})
    res.sort(key=lambda x: -x["puntos"])  # estable, como el sort de JS
    top = res[:3]
    ambiguo = not top or top[0]["puntos"] < 3 or (len(top) > 1 and top[1]["puntos"] == top[0]["puntos"])
    return {"recomendada": top[0] if top else None, "opciones": top, "ambiguo": ambiguo}
