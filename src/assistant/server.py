"""FastAPI: chat con streaming SSE, historial y reanudación human-in-the-loop."""
import json
import logging
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from assistant import agent as agent_mod
from assistant import memory
from assistant.config import ROOT, ConfigError, Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("assistant")


class ChatIn(BaseModel):
    message: str
    thread_id: str
    user_id: str = "anon"


class ResumeIn(BaseModel):
    thread_id: str
    user_id: str = "anon"
    decisions: list[dict]


def _build_real_agent(settings: Settings):
    client = memory.startup_checks(settings)
    from assistant.tools import build_tools

    model = agent_mod.make_model(settings)
    checkpointer = memory.build_checkpointer(client, settings.mongodb_db)
    store = memory.build_store(client, settings.mongodb_db, settings.memory_semantic, settings.openai_api_key)
    if settings.use_bigtool:
        from assistant.bigtool_agent import build_bigtool_agent

        log.info("Agente: langgraph-bigtool (demo tools: %s)", settings.bigtool_demo_tools)
        return build_bigtool_agent(model, settings, checkpointer=checkpointer, memories_store=store)
    return agent_mod.build_agent(model, build_tools(model, settings), settings, checkpointer=checkpointer, store=store)


def create_app(agent=None, settings: Settings | None = None, classify=None) -> FastAPI:
    settings = settings or Settings.from_env()
    if classify is None:
        # agente inyectado (tests) → sin llamadas reales a OpenAI para clasificar
        classify = agent_mod.clasificar_esfuerzo if agent is None else (lambda s, m: "medio")
    if agent is None:
        agent = _build_real_agent(settings)
        host = settings.mongodb_uri.rsplit("@", 1)[-1]  # nunca loguear usuario/contraseña
        log.info("Modelo: %s | MongoDB: %s (db %s)", settings.llm_model, host, settings.mongodb_db)

    app = FastAPI(title="Agente 0")

    def sse(payload, thread_id: str, user_id: str, esfuerzo: str | None = None):
        for event in agent_mod.stream_events(agent, payload, thread_id, user_id, settings, esfuerzo):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

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
        esfuerzo = classify(settings, body.message) if settings.model_call_limit == 0 else None
        return sse_response(sse(payload, body.thread_id, body.user_id, esfuerzo))

    @app.post("/resume")
    def resume(body: ResumeIn):
        return sse_response(sse(Command(resume={"decisions": body.decisions}), body.thread_id, body.user_id))

    @app.get("/history/{thread_id}")
    def history(thread_id: str):
        return {"thread_id": thread_id, "messages": agent_mod.get_history(agent, thread_id, settings)}

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
