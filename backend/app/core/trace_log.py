"""
trace_log — registro COMPLETO de cada turno del agente, para auditar si cada mini agente actuó bien.

Una línea JSON por turno en logs/agent_traces/AAAA-MM-DD.jsonl (lo lee a mano o con scripts/review_traces.py):
  - la petición (usuario, conversación, modelo pedido, agente/personalidad activa),
  - TODAS las llamadas a un modelo, en orden: nodo, etiquetas (p. ej. el chequeo que juzga), modelo y parámetros,
    los mensajes COMPLETOS que recibió, lo que respondió (texto o argumentos de la herramienta estructurada),
    tokens, costo, latencia, intento y errores,
  - la salida de cada nodo del grafo (decisiones: intención, apps, validaciones, veredicto del evaluador),
  - reinicios por reintento, y al final la respuesta entregada, la calidad y el gasto.

Es opt-in: SHIFU_TRACE_LOG=1 (SHIFU_TRACE_DIR cambia la carpeta). Ojo: guarda los prompts tal cual, incluido lo que el usuario
escribió (si pega una contraseña queda aquí también). Úsalo en desarrollo; la carpeta logs/ está fuera de git.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def enabled() -> bool:
    # Guarda lo que escribe el usuario (contraseñas incluidas): solo junto con SHIFU_DEV_UI=1, que nunca va en produccion.
    return os.getenv("SHIFU_TRACE_LOG", "").lower() in ("1", "true", "yes") and os.getenv("SHIFU_DEV_UI") == "1"


def _dir() -> Path:
    return Path(os.getenv("SHIFU_TRACE_DIR") or Path(__file__).resolve().parents[2] / "logs" / "agent_traces")


class TurnTrace:
    """Acumula los eventos de UN turno y los escribe como una línea JSON al terminar."""

    def __init__(self, header: dict) -> None:
        self.header = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **header}
        self.events: list[dict] = []
        self._t0 = time.perf_counter()
        self._done = False

    def event(self, kind: str, **data: Any) -> None:
        self.events.append({"t_ms": round((time.perf_counter() - self._t0) * 1000), "kind": kind, **data})

    def finish(self, **final: Any) -> None:
        if self._done:
            return
        self._done = True
        record = {**self.header, "total_ms": round((time.perf_counter() - self._t0) * 1000), "events": self.events, **final}
        try:  # el registro nunca debe romper un turno
            folder = _dir()
            folder.mkdir(parents=True, exist_ok=True)
            with open(folder / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception:
            logger.exception("[trace_log] no se pudo escribir el registro del turno")


def new_turn(header: dict) -> Optional[TurnTrace]:
    return TurnTrace(header) if enabled() else None
