"""FastAPI: chat con streaming SSE, historial y reanudación human-in-the-loop."""
import contextvars
import json
import logging
import queue
import sys
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from assistant import agent as agent_mod
from assistant import context as context_mod
from assistant import memory
from assistant.config import ROOT, ConfigError, Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("assistant")


class ChatIn(BaseModel):
    message: str
    thread_id: str
    user_id: str = "anon"
    effort: str | None = None  # bajo/medio/alto desde el selector de la UI; None o "auto" = clasificador


class ResumeIn(BaseModel):
    thread_id: str
    user_id: str = "anon"
    decisions: list[dict]


def _build_real_agent(settings: Settings):
    """Devuelve (agente, store de recuerdos)."""
    client = memory.startup_checks(settings)
    from assistant.tools import build_tools

    model = agent_mod.make_model(settings)
    checkpointer = memory.build_checkpointer(client, settings.mongodb_db)
    store = memory.build_store(client, settings.mongodb_db, settings.memory_semantic, settings.openai_api_key)
    if settings.use_bigtool:
        from assistant.bigtool_agent import BIGTOOL_PROMPT, build_bigtool_agent

        log.info("Agente: langgraph-bigtool (demo tools: %s)", settings.bigtool_demo_tools)
        # antes de buscar solo ve retrieve_tools
        agent_mod.check_turn_cap(settings, extra_prompt=BIGTOOL_PROMPT)
        agent = build_bigtool_agent(model, settings, checkpointer=checkpointer, memories_store=store)
        # bigtool no tiene medidor en vivo: el endpoint usa el uso real guardado
        agent.base_context_tokens = context_mod.prompt_tokens(agent_mod.system_prompt_text(settings) + BIGTOOL_PROMPT)
        return agent, store
    tools = build_tools(model, settings)
    agent_mod.check_turn_cap(settings, tools)
    return agent_mod.build_agent(model, tools, settings, checkpointer=checkpointer, store=store), store


PING = ": ping\n\n"  # comentario SSE: el cliente lo ignora, pero mantiene viva la conexión en proxies
_END = object()


def with_keepalive(events, interval: float):
    """Reenvía `events` (iterador bloqueante) y emite PING cada `interval` segundos sin eventos.
    El iterador corre en un hilo aparte (con el contexto actual); si el cliente se va, se detiene en el
    siguiente evento."""
    if not interval or interval <= 0:
        yield from events
        return
    q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def produce():
        try:
            for item in events:
                q.put(item)
                if stop.is_set():
                    break
        except BaseException as exc:  # noqa: BLE001 - se re-lanza en el hilo del servidor
            q.put(exc)
        finally:
            close = getattr(events, "close", None)
            if close:
                close()
            q.put(_END)

    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(produce,), daemon=True).start()
    try:
        while True:
            try:
                item = q.get(timeout=interval)
            except queue.Empty:
                yield PING
                continue
            if item is _END:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop.set()


def create_app(agent=None, settings: Settings | None = None, classify=None, store=None) -> FastAPI:
    settings = settings or Settings.from_env()
    if classify is None:
        # agente inyectado (tests) → sin llamadas reales a OpenAI para clasificar
        classify = agent_mod.clasificar_esfuerzo if agent is None else (lambda s, m: "medio")
    if agent is None:
        agent, store = _build_real_agent(settings)
        host = settings.mongodb_uri.rsplit("@", 1)[-1]  # nunca loguear usuario/contraseña
        log.info("Modelo: %s | MongoDB: %s (db %s)", settings.llm_model, host, settings.mongodb_db)

    app = FastAPI(title="Agente 0")

    def sse(payload, thread_id: str, user_id: str, esfuerzo: str | None = None, origen: str = "auto"):
        events = (f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n" for event in
                  agent_mod.stream_events(agent, payload, thread_id, user_id, settings, esfuerzo, origen))
        return with_keepalive(events, settings.sse_ping_seconds)

    def sse_response(gen):
        return StreamingResponse(gen, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/")
    def index():
        return FileResponse(ROOT / "static" / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True, "model": settings.llm_model}

    @app.post("/chat")
    def chat(body: ChatIn):
        payload = {"messages": [{"role": "user", "content": body.message}]}
        esfuerzo, origen = agent_mod.elegir_esfuerzo(settings, body.message, body.effort, classify)
        return sse_response(sse(payload, body.thread_id, body.user_id, esfuerzo, origen))

    @app.post("/resume")
    def resume(body: ResumeIn):
        return sse_response(sse(Command(resume={"decisions": body.decisions}), body.thread_id, body.user_id))

    @app.get("/history/{thread_id}")
    def history(thread_id: str):
        return {"thread_id": thread_id, "messages": agent_mod.get_history(agent, thread_id, settings)}

    base_tokens = (getattr(agent, "base_context_tokens", None)
                   or context_mod.prompt_tokens(agent_mod.system_prompt_text(settings)))
    can_compact = getattr(agent, "compactor", None) is not None

    @app.get("/threads/{thread_id}/context")
    def thread_context(thread_id: str):
        """Medidor de contexto del hilo, desde su checkpoint (sin llamar al modelo)."""
        values = agent.get_state(agent_mod.run_config(thread_id, settings)).values or {}
        return {"thread_id": thread_id, **context_mod.context_report(values, settings, base_tokens, can_compact)}

    @app.post("/threads/{thread_id}/compact")
    def compact(thread_id: str):
        """Compactación manual ("Compactar ahora"): resume la parte más antigua del hilo."""
        try:
            record = agent_mod.compact_thread(agent, thread_id, settings)
        except ValueError as exc:
            raise HTTPException(501, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"thread_id": thread_id, "compacted": record is not None, "record": record}

    def _store():
        if store is None:
            raise HTTPException(503, "El almacén de recuerdos no está disponible")
        return store

    # ponytail: sin autenticación; user_id es texto libre (app local). Cada endpoint solo toca su namespace.
    @app.get("/memories/{user_id}")
    def list_memories(user_id: str):
        return {"user_id": user_id, "memories": memory.list_memories(_store(), user_id)}

    @app.delete("/memories/{user_id}/{key}")
    def delete_memory(user_id: str, key: str):
        if not memory.delete_memory(_store(), user_id, key):
            raise HTTPException(404, "Recuerdo no encontrado")
        return {"deleted": key}

    return app


def __getattr__(name: str):
    # ponytail: `app` se crea perezosamente para que importar el módulo (tests) no conecte a Mongo/OpenAI.
    if name != "app":
        raise AttributeError(name)
    try:
        globals()["app"] = create_app()
    except ConfigError as e:
        print(f"\nERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
    return globals()["app"]
