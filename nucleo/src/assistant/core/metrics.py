"""TURN_METRICS (apagado por defecto): una fila por turno (/chat o /resume) en la colección turn_metrics de la base de
negocio, y su resumen para GET /metrics/summary.

La fila no lleva contenido de mensajes: ni lo que escribió el usuario, ni la respuesta, ni los argumentos o resultados
de las herramientas. Solo ids, tiempos, tokens, nombres y estados de herramientas, aprobaciones y el estado final.
Vive en su propio módulo para no sumar constantes a los que fija la huella."""
import time
import uuid
from collections import Counter
from datetime import datetime, timezone


class TurnRecorder:
    """Mira los eventos de un turno según salen y arma su fila al terminar (también si el cliente se desconecta)."""

    def __init__(self, payload, thread_id: str, user_id: str, settings, effort: str | None, effort_source: str,
                 profile_name: str, cut_notes: dict[str, str], recursion_note: str):
        decisions = []
        resume = getattr(payload, "resume", None)  # Command(resume={"decisions": [...]}) en /resume
        if isinstance(resume, dict):
            decisions = [d.get("type") for d in resume.get("decisions", []) if isinstance(d, dict)]
        self.start = time.monotonic()
        self.cut_notes = cut_notes
        self.recursion_note = recursion_note
        self.counter = None
        self.status = "disconnected"  # si nunca llega done ni error: el cliente cerró el stream
        self.cut = None
        self.interrupted = False
        self.record = {
            "turn_id": uuid.uuid4().hex, "run_id": None, "thread_id": thread_id, "user_id": user_id,
            "kind": "resume" if resume is not None else "chat", "ts": datetime.now(timezone.utc),
            "effort": effort, "effort_source": effort_source, "model": settings.llm_model, "profile": profile_name,
            "approved": decisions.count("approve"), "rejected": decisions.count("reject"), "tools": [],
        }

    def see(self, event: dict, counter) -> None:
        self.counter = self.counter or counter
        kind = event.get("type")
        if kind == "run":
            self.record["run_id"] = event.get("run_id")
        elif kind == "tool_end":
            self.record["tools"].append({"name": event.get("name"), "status": event.get("status")})
        elif kind == "interrupt":
            self.interrupted = True
        elif kind == "token" and event.get("text") in self.cut_notes:
            self.cut = self.cut_notes[event["text"]]
        elif kind == "error":
            self.status = "recursion" if event.get("message") == self.recursion_note else "error"
        elif kind == "done" and self.status == "disconnected":
            self.status = self.cut or ("interrupted" if self.interrupted else "done")

    def finish(self) -> dict:
        c = self.counter
        self.record.update({
            "status": self.status, "latency_ms": int((time.monotonic() - self.start) * 1000),
            "tokens_total": c.total if c else 0, "tokens_input": c.input if c else 0,
            "tokens_output": c.output if c else 0,
        })
        if self.record["run_id"]:
            self.record["turn_id"] = self.record["run_id"]  # con TRACE_METADATA, el mismo id que la traza
        return self.record


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p * (len(values) - 1))))]


def summarize(records: list[dict]) -> dict:
    """Resumen de filas de turn_metrics: conteos, latencias, tokens, herramientas, aprobaciones y estados."""
    latencies = [r.get("latency_ms", 0) for r in records]
    tokens = [r.get("tokens_total", 0) for r in records]
    tools: dict[str, Counter] = {}
    for r in records:
        for t in r.get("tools", []):
            tools.setdefault(t.get("name") or "?", Counter())[t.get("status") or "?"] += 1
    approved = sum(r.get("approved", 0) for r in records)
    rejected = sum(r.get("rejected", 0) for r in records)
    return {
        "turns": len(records),
        "status": dict(Counter(r.get("status") for r in records)),
        "latency_ms": {"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
        "tokens": {"total": sum(tokens), "avg": round(sum(tokens) / len(tokens)) if tokens else 0},
        "tools": {name: dict(c) for name, c in sorted(tools.items())},
        "approvals": {"approved": approved, "rejected": rejected,
                      "rejection_rate": round(rejected / (approved + rejected), 3) if approved + rejected else None},
    }
