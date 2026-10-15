"""Construcción del agente y traducción de su stream a eventos SSE (dicts). Todo síncrono."""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ToolErrorMiddleware,
    dynamic_prompt,
    wrap_model_call,
)
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from assistant.config import Settings, read_system_prompt

logger = logging.getLogger(__name__)

OUTPUT_PREVIEW_CHARS = 500

# Esfuerzo automático: nivel -> (tope de llamadas al modelo en el turno, reasoning effort de Luna)
ESFUERZOS = {"bajo": (5, "low"), "medio": (15, "medium"), "alto": (40, "high")}
LIMIT_MSG = "Se alcanzó el límite de llamadas al modelo para este mensaje; detuve el proceso. Escribe «continúa» para seguir."


@dataclass
class Context:
    user_id: str = "anon"
    max_llamadas: int = 15       # 0 = sin tope
    razonamiento: str | None = None  # None = default del modelo


def clasificar_esfuerzo(settings: Settings, mensaje: str) -> str:
    """Clasifica el esfuerzo del mensaje (bajo/medio/alto) con una llamada rápida sin razonamiento.
    Ante cualquier fallo devuelve "medio"."""
    try:
        llm = ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key or None,
                         use_responses_api=True, reasoning={"effort": "none"}, max_tokens=16)
        prompt = (
            "Clasifica el esfuerzo que requiere este mensaje para un asistente con herramientas. "
            "Responde SOLO una palabra:\n"
            "bajo = saludo, charla, dato simple o una sola consulta rápida;\n"
            "medio = una búsqueda web, un cálculo o una explicación normal;\n"
            "alto = varios pasos o cálculos encadenados, comparar fuentes, investigar a fondo, planear o razonar algo difícil.\n\n"
            f"Mensaje: {mensaje[:2000]}"
        )
        palabra = llm.invoke(prompt).text.strip().lower()
        return next((n for n in ESFUERZOS if n in palabra), "medio")
    except Exception as exc:  # noqa: BLE001
        logger.warning("No pude clasificar el esfuerzo (%s); uso 'medio'", exc)
        return "medio"


def contexto_para(user_id: str, settings: Settings, esfuerzo: str | None) -> Context:
    """MODEL_CALL_LIMIT>0 fija el tope; 0 = automático según el esfuerzo."""
    if settings.model_call_limit > 0 or esfuerzo not in ESFUERZOS:
        return Context(user_id=user_id, max_llamadas=settings.model_call_limit or 15)
    max_llamadas, razonamiento = ESFUERZOS[esfuerzo]
    return Context(user_id=user_id, max_llamadas=max_llamadas, razonamiento=razonamiento)


class LimiteLlamadas(ModelCallLimitMiddleware):
    """Como ModelCallLimitMiddleware, pero el tope sale de runtime.context.max_llamadas (por mensaje)."""

    def __init__(self):
        super().__init__(run_limit=10**9, exit_behavior="end")  # el tope real viene del contexto

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        limite = getattr(runtime.context, "max_llamadas", 0)
        if limite and state.get("run_model_call_count", 0) >= limite:
            return {"jump_to": "end", "messages": [AIMessage(content=LIMIT_MSG)]}
        return None


@wrap_model_call
def _razonamiento(request, handler):
    effort = getattr(request.runtime.context, "razonamiento", None)
    if effort:
        request = request.override(model_settings={**request.model_settings, "reasoning": {"effort": effort}})
    return handler(request)


def make_model(settings: Settings) -> ChatOpenAI:
    # use_responses_api=True es obligatorio: gpt-6-luna solo hace function calling + web_search
    # hospedado en la Responses API.
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key or None,
        use_responses_api=True,
        max_tokens=settings.max_tokens or None,  # 0 = sin tope (el modelo decide; máx. 128k)
        streaming=True,
    )


def _on_tool_error(exc: Exception, request) -> str:
    return f"Error en la herramienta ({type(exc).__name__}): {exc}. Intenta otra cosa."


_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


@dynamic_prompt
def _system_prompt(request) -> str:
    # Fecha local en cada llamada: el modelo no la sabe y la búsqueda web va en UTC.
    now = datetime.now().astimezone()
    return (
        f"{read_system_prompt()}\n\n"
        f"Fecha y hora actual del usuario: {_DIAS[now.weekday()]} {now:%Y-%m-%d %H:%M} (UTC{now:%z}). "
        "Úsala como 'hoy'; no la deduzcas de resultados de búsqueda."
    )


def build_agent(model, tools, settings: Settings, checkpointer=None, store=None):
    return create_agent(
        model,
        tools,
        context_schema=Context,
        checkpointer=checkpointer,
        store=store,
        middleware=[
            _system_prompt,
            _razonamiento,
            LimiteLlamadas(),
            ToolErrorMiddleware(on_error=_on_tool_error),
            HumanInTheLoopMiddleware(interrupt_on={"enviar_email_simulado": True}),
        ],
    )


def run_config(thread_id: str, settings: Settings) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.recursion_limit,
    }


def _engine_from_output(output: str) -> str | None:
    first = output.split("\n", 1)[0].strip()
    if first.startswith("[motor:") and first.endswith("]"):
        return first[len("[motor:"):-1].strip() or None
    return None


def _content_text(msg) -> str:
    try:
        return msg.text or ""
    except Exception:  # noqa: BLE001
        return str(msg.content)


def _interrupt_event(intr) -> dict:
    value = getattr(intr, "value", intr)
    requests = value.get("action_requests", []) if isinstance(value, dict) else []
    return {
        "type": "interrupt",
        "id": getattr(intr, "id", None),
        "action_requests": [
            {
                "name": r.get("name"),
                "args": r.get("args", {}),
                "description": r.get("description", ""),
            }
            for r in requests
        ],
    }


def _update_events(update: dict) -> Iterator[dict]:
    for node, node_update in update.items():
        if node == "__interrupt__":
            intrs = node_update if isinstance(node_update, (list, tuple)) else [node_update]
            for intr in intrs:
                yield _interrupt_event(intr)
            continue
        if not isinstance(node_update, dict):
            continue
        if node.startswith("LimiteLlamadas") and node_update.get("messages"):
            # el middleware corta el turno con un AIMessage que no se streamea.
            yield {"type": "token", "text": f"\n\n_{LIMIT_MSG}_"}
            continue
        for msg in node_update.get("messages", []) or []:
            if node == "model" and isinstance(msg, AIMessage):
                for call in msg.tool_calls:
                    yield {
                        "type": "tool_start",
                        "id": call.get("id"),
                        "name": call.get("name"),
                        "args": call.get("args", {}),
                    }
            elif node == "tools" and isinstance(msg, ToolMessage):
                output = _content_text(msg)
                yield {
                    "type": "tool_end",
                    "id": msg.tool_call_id,
                    "name": msg.name,
                    "output": output[:OUTPUT_PREVIEW_CHARS],
                    "status": "error" if msg.status == "error" else "success",
                    "engine": _engine_from_output(output),
                }


def stream_events(agent, payload, thread_id: str, user_id: str, settings: Settings,
                  esfuerzo: str | None = None) -> Iterator[dict]:
    ctx = contexto_para(user_id, settings, esfuerzo)
    if esfuerzo in ESFUERZOS and settings.model_call_limit == 0:
        yield {"type": "effort", "level": esfuerzo, "max_calls": ctx.max_llamadas, "reasoning": ctx.razonamiento}
    config = run_config(thread_id, settings)
    # cada llamada al modelo gasta ~5 pasos del grafo (middlewares + tools): el límite de pasos acompaña al tope
    config["recursion_limit"] = max(config["recursion_limit"], ctx.max_llamadas * 6)
    try:
        stream = agent.stream(
            payload,
            config=config,
            context=ctx,
            stream_mode=["messages", "updates", "custom"],
            version="v2",
        )
        for chunk in stream:
            if chunk.get("ns"):  # solo el grafo raíz; ignora subagentes
                continue
            kind, data = chunk["type"], chunk["data"]
            if kind == "messages":
                token, metadata = data
                if metadata.get("langgraph_node") != "model":
                    continue
                if "nostream" in (metadata.get("tags") or []):
                    continue
                text = _content_text(token)
                if text:
                    yield {"type": "token", "text": text}
            elif kind == "updates":
                yield from _update_events(data)
            elif kind == "custom" and isinstance(data, dict) and data.get("tipo") == "progreso":
                # avance del investigador profundo (búsquedas internas mientras trabaja)
                yield {"type": "progress", "name": data.get("herramienta"), "args": data.get("args", {})}
    except GraphRecursionError:
        yield {"type": "error", "message": (
            f"Me detuve: la tarea superó {settings.recursion_limit} pasos internos. "
            "Pídeme que continúe o sube RECURSION_LIMIT en .env."
        )}
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error durante el stream del agente")
        yield {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
        return
    yield {"type": "done", "thread_id": thread_id}


def get_history(agent, thread_id: str, settings: Settings) -> list[dict]:
    state = agent.get_state(run_config(thread_id, settings))
    out: list[dict] = []
    for msg in (state.values or {}).get("messages", []):
        if isinstance(msg, HumanMessage):
            out.append({"role": "user", "content": _content_text(msg)})
        elif isinstance(msg, AIMessage):
            text = _content_text(msg)
            if text:
                out.append({"role": "assistant", "content": text})
            for call in msg.tool_calls:
                out.append({"role": "tool", "name": call.get("name")})
    return out
