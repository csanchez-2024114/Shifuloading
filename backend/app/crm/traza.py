"""Trazas de los turnos del chat del CRM, para revisar casos reales después (punto 46).

Solo con `CRM_TRAZA=1`. Cada turno del agente de diseño deja UNA línea JSON en `<carpeta>/AAAA-MM-DD.jsonl` (día UTC).
La carpeta es `CRM_TRAZA_DIR` o, si no se define, `backend/trazas_chat/` (ignorada por git).

Qué se guarda: el texto de la persona, cada vuelta del modelo y cada herramienta en orden (nombre, argumentos, resultado y
milisegundos), los avisos del código, los cambios y fallos, la respuesta final y el tiempo total. Qué NO: el documento del CRM,
la imagen, el contenido de archivos adjuntos o enlaces (solo su largo o su URL), el historial (solo cuántos mensajes) ni nada
de la configuración. Los textos largos se recortan y lo que tenga forma de clave (sk-…, Bearer …, JWT) se tapa.

Escribir la traza nunca rompe el turno: si falla, se avisa en el log y la persona recibe su respuesta igual. Sin `CRM_TRAZA=1`
no se mide ni se escribe nada (el camino normal no cambia).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CARPETA_POR_DEFECTO = Path(__file__).resolve().parents[2] / "trazas_chat"
LARGO_TEXTO = 2000
LARGO_RESPUESTA = 4000
LARGO_ARGS = 1500
LARGO_RESULTADO = 1500

_SECRETOS = re.compile(r"sk-[A-Za-z0-9_\-]{12,}|(?i:bearer)\s+[A-Za-z0-9._\-]{12,}|eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}")

# Los pasos del turno en curso (None = no se está trazando). ContextVar: cada petición tiene la suya aunque corran a la vez.
_PASOS: ContextVar[list[dict] | None] = ContextVar("crm_traza_pasos", default=None)


def activa() -> bool:
    return os.getenv("CRM_TRAZA", "0").strip() == "1"


def carpeta() -> Path:
    propia = os.getenv("CRM_TRAZA_DIR", "").strip()
    return Path(propia).expanduser() if propia else CARPETA_POR_DEFECTO


def _limpio(texto: Any, largo: int) -> str:
    t = _SECRETOS.sub("[oculto]", str(texto if texto is not None else ""))
    return t if len(t) <= largo else t[:largo] + f"…(+{len(t) - largo})"


def _json_corto(v: Any, largo: int) -> str:
    try:
        t = json.dumps(v, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        t = str(v)
    return _limpio(t, largo)


def ms_desde(t0: float) -> int:
    return round((time.perf_counter() - t0) * 1000)


def empezar() -> Any:
    """Abre la lista de pasos del turno. Devuelve el token para `terminar` (o None si no se traza)."""
    return _PASOS.set([]) if activa() else None


def pasos() -> list[dict]:
    return list(_PASOS.get() or [])


def terminar(token: Any) -> None:
    if token is not None:
        _PASOS.reset(token)


def paso_modelo(ms: int, llamadas: list[dict] | None = None, contenido: str = "", etapa: str = "vuelta") -> None:
    """Una llamada al modelo: cuánto tardó, qué herramientas pidió y (recortado) qué escribió."""
    lista = _PASOS.get()
    if lista is None:
        return
    lista.append({"tipo": "modelo", "etapa": etapa, "ms": ms, "pidio": [str(ll.get("name") or "") for ll in (llamadas or [])],
                  "texto": _limpio(contenido, 600)})


def paso_herramienta(nombre: str, args: Any, resultado: Any, ms: int) -> None:
    lista = _PASOS.get()
    if lista is None:
        return
    lista.append({"tipo": "herramienta", "nombre": str(nombre), "ms": ms, "args": _json_corto(args, LARGO_ARGS),
                  "resultado": _limpio(resultado, LARGO_RESULTADO)})


def _lista_corta(xs: Any, largo: int = LARGO_RESULTADO) -> list:
    out = []
    for x in xs or []:
        if isinstance(x, dict):
            out.append({k: (_json_corto(v, LARGO_ARGS) if k == "args" else _limpio(v, largo)) for k, v in x.items()})
        else:
            out.append(_limpio(x, largo))
    return out


def linea_turno(*, doc: dict, texto: str, ms: int, salida: dict | None = None, error: BaseException | None = None,
                historial: list | None = None, seccion: str | None = None, imagen: bool = False, adjunto: str | None = None,
                ahora: datetime | None = None, pasos_turno: list[dict] | None = None) -> dict:
    """La línea de traza de un turno (sin escribirla). `ts` y el archivo del día son la hora REAL en que corrió (UTC); `ahora` es la
    hora que usó el turno (en pruebas y bancos se fija a mano) y se anota aparte solo si se pasó."""
    brief = doc.get("brief") or {}
    linea: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "ahora_turno": ahora.isoformat() if ahora else None,
        "negocio": _limpio(brief.get("nombre"), 80),
        "plantilla": (doc.get("plantilla") or {}).get("id"),
        "version_crm": doc.get("version"),
        "texto": _limpio(texto, LARGO_TEXTO),
        "seccion": seccion,
        "imagen": bool(imagen),
        "adjunto_largo": len(adjunto or ""),
        "historial_mensajes": len(historial or []),
        "ms_total": ms,
        "pasos": pasos_turno or [],
    }
    if error is not None:
        linea["error"] = type(error).__name__
        return linea
    s = salida or {}
    linea.update({
        "modo": s.get("modo"),
        "respuesta": _limpio(s.get("respuesta"), LARGO_RESPUESTA),
        "cambios": _lista_corta(s.get("cambios")),
        "fallos": _lista_corta(s.get("fallos")),
        "intentos": _lista_corta(s.get("intentos")),
        "consultas": _lista_corta(s.get("consultas"), 600),
        "avisos": _lista_corta(s.get("avisos")),
        "enlaces": [_limpio(e.get("url"), 300) for e in s.get("enlaces") or [] if isinstance(e, dict)],
        "pendiente": bool(s.get("pendiente")),
        "deshizo": sorted((s.get("deshacer") or {}).get("deshechos") or []),
    })
    return linea


def escribir(linea: dict) -> Path | None:
    """Agrega la línea al archivo del día. Nunca lanza: devuelve la ruta o None si no se pudo."""
    try:
        dia = str(linea.get("ts") or datetime.now(timezone.utc).isoformat())[:10]
        destino = carpeta()
        destino.mkdir(parents=True, exist_ok=True)
        archivo = destino / f"{dia}.jsonl"
        with archivo.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
        return archivo
    except Exception as e:  # una traza que no se puede escribir no le quita la respuesta a nadie
        logger.warning("No se pudo escribir la traza del chat: %s", type(e).__name__)
        return None
