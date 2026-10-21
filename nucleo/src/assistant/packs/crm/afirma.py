"""¿La respuesta AFIRMA que Shifu cambió algo? Lo usa el cerco de honestidad: si lo afirma y ninguna herramienta cambió nada, el código
le pide decir la verdad. Copia de `laboratorio/servidor/afirma.js` (misma regla, mismos casos).

No cuentan (medido en la prueba de cliente, D51):
- las preguntas: «¿quieres que cree la sección?», «¿lo agrego?»;
- el subjuntivo sin tilde: «que agregue», «que cree» (la afirmación lleva tilde: agregué, creé);
- las negaciones: «no hice ningún cambio», «todavía no lo agregué».
"""
from __future__ import annotations

from typing import Any

import regex  # \p{L} igual que en JS (el `re` de la biblioteca estándar no lo tiene)

_VERBO = regex.compile(r"(?<!\p{L})(agregué|quité|cambié|moví|achiqué|agrandé|puse|creé|hice|listo|lista|ajusté|reemplacé|renombré|borré|deshice|marqué)(?!\p{L})",
                       regex.IGNORECASE)
_NIEGA = regex.compile(r"(?<!\p{L})(no|nunca|ni|sin|todavía no|aún no)(\s+\p{L}+){0,2}\s*\Z", regex.IGNORECASE)
_PREGUNTA = regex.compile(r"¿[^?]*\?")
_PREGUNTA_SIN_ABRIR = regex.compile(r"[^.!\n]*\?")
_ORACION = regex.compile(r"(?<=[.!\n;:])")


def afirma_cambio(texto: Any) -> bool:
    """True si alguna oración afirma un cambio (un verbo de cambio en pasado, sin negación delante y fuera de una pregunta)."""
    return afirma_con(texto, _VERBO)


def sin_preguntas(texto: Any) -> str:
    """El texto sin sus preguntas («¿quieres que la cree?» no afirma ni promete nada)."""
    return _PREGUNTA_SIN_ABRIR.sub(" ", _PREGUNTA.sub(" ", str(texto or "")))


def afirma_con(texto: Any, verbo: Any) -> bool:
    """La misma regla con otro vocabulario (`verbo`: un patrón con `finditer`): las preguntas y lo negado no cuentan. La usa el agente
    para las frases de logro de Carlos («registré», «he agregado»…) con el sistema de diseño."""
    for oracion in _ORACION.split(sin_preguntas(texto)):
        for m in verbo.finditer(oracion):
            if not _NIEGA.search(oracion[: m.start()]):
                return True
    return False
