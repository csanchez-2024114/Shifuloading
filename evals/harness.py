"""Medición de turnos para las evals, sin tocar el núcleo. Es el montaje del servidor medido de la validación E2E:
- `Meter` envuelve `agent.stream_events` (y el clasificador de esfuerzo) y registra por turno los tokens de
  `TurnTokens` (agente, investigador, búsquedas hospedadas, verificadores) más el clasificador, la latencia, los
  eventos y las herramientas. Ningún contenido de mensajes va al registro.
- `install` añade a la app las rutas `/_eval/*` y el tope duro acumulado (429 antes de /chat o /resume si el gasto
  más el margen del siguiente mensaje pasa el tope).
El modo falso y el real usan exactamente esto; cambia solo quién construye el agente."""
import json
import threading
import time
from pathlib import Path

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import HumanMessage, ToolMessage
from starlette.responses import JSONResponse

from assistant.core import agent as agent_mod


class Meter:
    def __init__(self, log_path: Path | None = None):
        self.log_path = Path(log_path) if log_path else None
        self.turns: list[dict] = []
        self.margin = 0
        self._clf = 0
        self._lock = threading.Lock()
        self._saved = None

    # ------------------------------------------------------------ registro
    def spent(self) -> int:
        """Gasto acumulado. Con registro en disco cuenta también los arranques anteriores del mismo log."""
        if self.log_path and self.log_path.exists():
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
            return sum(json.loads(line).get("tokens_total", 0) for line in lines if line.strip())
        return sum(t.get("tokens_total", 0) for t in self.turns)

    def _log(self, rec: dict) -> None:
        with self._lock:
            self.turns.append(rec)
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def for_thread(self, thread_id: str) -> list[dict]:
        with self._lock:
            return [t for t in self.turns if t.get("thread") == thread_id]

    # ------------------------------------------------------------ envolturas
    def __enter__(self):
        """Parchea el módulo del agente; antes de `create_app` (el servidor captura ahí el clasificador)."""
        self._saved = (agent_mod.stream_events, agent_mod.clasificar_esfuerzo)
        stream, classify = self._saved

        def clasificar_medido(settings, mensaje):
            with get_usage_metadata_callback() as cb:
                nivel = classify(settings, mensaje)
            self._clf = sum(u.get("total_tokens", 0) or 0 for u in cb.usage_metadata.values())
            return nivel

        def stream_medido(agent, payload, thread_id, user_id, settings, esfuerzo=None, origen="auto", **kwargs):
            start, events, tools, counter = time.monotonic(), [], [], None
            clf, self._clf = self._clf, 0
            status = "open"
            try:
                for ev in stream(agent, payload, thread_id, user_id, settings, esfuerzo, origen, **kwargs):
                    counter = counter or agent_mod._ACTIVE_TURNS.get(thread_id)
                    events.append(ev["type"])
                    if ev["type"] == "tool_end":
                        tools.append({"name": ev.get("name"), "status": ev.get("status")})
                    if ev["type"] in ("done", "error"):
                        status = ev["type"]
                    yield ev
            finally:
                turn = counter.total if counter else 0
                self._log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "thread": thread_id,
                           "kind": "chat" if isinstance(payload, dict) else "resume", "effort": esfuerzo,
                           "origin": origen, "events": events, "tools": tools, "status": status,
                           "tokens_turn": turn, "tokens_input": counter.input if counter else 0,
                           "tokens_output": counter.output if counter else 0, "tokens_classifier": clf,
                           "tokens_total": turn + clf, "seconds": round(time.monotonic() - start, 2),
                           "cap": settings.turn_token_cap})

        agent_mod.stream_events, agent_mod.clasificar_esfuerzo = stream_medido, clasificar_medido
        return self

    def __exit__(self, *exc):
        agent_mod.stream_events, agent_mod.clasificar_esfuerzo = self._saved
        return False


def evidence_text(agent, thread_id: str, settings) -> str:
    """Lo que devolvieron las herramientas y lo que escribió el usuario en el hilo, completo (los tool_end del SSE
    vienen recortados)."""
    state = agent.get_state(agent_mod.run_config(thread_id, settings))
    msgs = (state.values or {}).get("messages", [])
    return "\n".join(agent_mod._content_text(m) for m in msgs if isinstance(m, (ToolMessage, HumanMessage)))


def install(app, meter: Meter, get_agent, settings, hard_cap: int | None = None) -> None:
    """Rutas de medición y, con `hard_cap`, el tope duro acumulado de la corrida."""

    @app.middleware("http")
    async def tope_duro(request, call_next):
        if hard_cap and request.method == "POST" and request.url.path in ("/chat", "/resume"):
            spent = meter.spent()
            if spent + meter.margin > hard_cap:
                meter._log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "blocked": request.url.path, "spent": spent,
                            "margin": meter.margin, "tokens_total": 0})
                return JSONResponse({"detail": f"Tope duro de las evals: gastado {spent} + margen {meter.margin} "
                                               f"> {hard_cap}"}, status_code=429)
        return await call_next(request)

    @app.get("/_eval")
    def estado():
        return {"spent": meter.spent(), "hard_cap": hard_cap, "margin": meter.margin,
                "cap": settings.turn_token_cap, "model": settings.llm_model, "db": settings.mongodb_db}

    @app.post("/_eval/margin")
    def margen(n: int):
        meter.margin = n
        return {"margin": n, "spent": meter.spent(), "fits": not hard_cap or meter.spent() + n <= hard_cap}

    @app.get("/_eval/turns")
    def turnos(thread_id: str):
        return {"turns": meter.for_thread(thread_id)}

    @app.get("/_eval/evidence/{thread_id}")
    def evidencia(thread_id: str):
        return {"text": evidence_text(get_agent(), thread_id, settings)}
