"""Construcción del agente y traducción de su stream a eventos SSE (dicts). Todo síncrono."""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
    ToolErrorMiddleware,
    dynamic_prompt,
    wrap_model_call,
)
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from assistant import citations
from assistant.config import Settings, read_system_prompt
from assistant.memory import SUMMARY_SOURCE

logger = logging.getLogger(__name__)

OUTPUT_PREVIEW_CHARS = 500
MODEL_NODES = ("model", "agent")  # "agent" = nodo del modelo en langgraph-bigtool

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
            "Classify the effort this message requires from an assistant with tools. "
            "Reply with ONLY one of these words: bajo, medio, alto.\n"
            "bajo = greeting, small talk, a simple fact or a single quick lookup;\n"
            "medio = one web search, one calculation or a normal explanation;\n"
            "alto = several steps or chained calculations, comparing sources, in-depth research, planning or hard reasoning.\n\n"
            f"Message: {mensaje[:2000]}"
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


def make_checker_model(settings: Settings) -> ChatOpenAI:
    """Modelo barato para verificaciones (recuerdos, respuestas): sin razonamiento y fuera del stream."""
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key or None, use_responses_api=True,
                      reasoning={"effort": "none"}, tags=["nostream"])


def make_summary_model(settings: Settings) -> ChatOpenAI:
    # tags=["nostream"]: sin esto el texto del resumen llega a la UI como tokens (stream_mode="messages").
    return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key or None, use_responses_api=True,
                      reasoning={"effort": "low"}, tags=["nostream"])


SUMMARY_PROMPT = """Summarize the earlier part of a conversation between a user and an assistant so the assistant can \
continue it without the original messages. The summary replaces those messages, so anything you leave out is lost.

Keep VERBATIM (exact spelling, values and units):
- names of people, places, products, projects and organizations;
- every number, amount, date, time, quantity and result of calculations;
- decisions the user made and options they rejected, with their reasons;
- the user's stated preferences, likes, dislikes and personal facts, attributed to the user;
- open questions, pending tasks and commitments the assistant made.

Rules:
- If the messages start with an earlier summary, merge it in: keep all of its facts unless the user corrected them.
- Write facts the user stated as "The user said ...". Do not add facts, guesses or interpretations.
- Mark clearly what came from tools (web results, calculations) versus from the user.
- Write in the conversation's language. Use short bullet points grouped by topic. No preamble.

<messages>
{messages}
</messages>"""


def _on_tool_error(exc: Exception, request) -> str:
    return f"Error en la herramienta ({type(exc).__name__}): {exc}. Intenta otra cosa."


def system_prompt_text() -> str:
    # Fecha local en cada llamada: el modelo no la sabe y la búsqueda web va en UTC.
    now = datetime.now().astimezone()
    return (
        f"{read_system_prompt()}\n\n"
        f"User's current local date and time: {now:%A %Y-%m-%d %H:%M} (UTC{now:%z}). "
        "Treat it as 'today'; never infer the date from search results."
    )


@dynamic_prompt
def _system_prompt(request) -> str:
    return system_prompt_text()


EVIDENCE_TOOLS = ("buscar_web", "investigador_profundo")
_EVIDENCE_CHARS = 12000

VERIFY_ANSWER_PROMPT = """You are a fact-checker. Given an ANSWER and the EVIDENCE the assistant retrieved in this turn, \
check every factual claim in the ANSWER (names, numbers, dates, quotes, citations).
A claim is SUPPORTED only if the EVIDENCE states it or directly implies it.
Common general knowledge, opinions, advice and things the user said need no support.
Citations are checked separately: two URLs are the same if domain and path match (ignore ?utm_source and other query
parameters). Never remove or change a citation link whose URL appears in the EVIDENCE.

Output:
- If every claim is supported: output exactly OK (do not rewrite or rephrase a correct answer).
- Otherwise: output only the corrected answer. Keep the language, wording, structure, citation links and supported
  content unchanged; remove or soften only the unsupported claims (e.g. "I couldn't verify X", in the answer's
  language); fix wrong numbers using the EVIDENCE. Never add new claims, numbers or dates.

EVIDENCE:
{evidence}

ANSWER:
{answer}"""


class AnswerVerifier(AgentMiddleware):
    """ANSWER_VERIFY: al terminar el turno, si se usó buscar_web/investigador_profundo, una llamada barata
    contrasta la respuesta con lo recuperado. Si corrige, reemplaza el mensaje (mismo id) y avisa a la UI con el
    original: el cambio nunca es silencioso. Sin búsqueda en el turno no hace nada (0 tokens)."""

    def __init__(self, checker):
        super().__init__()
        self.checker = checker

    def after_agent(self, state, runtime):
        messages = state.get("messages") or []
        start = max((i for i, m in enumerate(messages) if m.type == "human"), default=-1) + 1
        turn = messages[start:]
        evidence = [_content_text(m) for m in turn if isinstance(m, ToolMessage) and m.name in EVIDENCE_TOOLS]
        last = turn[-1] if turn else None
        if not evidence or not isinstance(last, AIMessage) or last.tool_calls or not _content_text(last).strip():
            return None
        original = _content_text(last)
        try:
            resp = self.checker.invoke(VERIFY_ANSWER_PROMPT.format(
                evidence="\n\n---\n\n".join(evidence)[-_EVIDENCE_CHARS:], answer=original))
        except Exception as exc:  # noqa: BLE001 - la verificación es opcional: si falla, se deja la respuesta
            logger.warning("No pude verificar la respuesta (%s)", exc)
            return None
        verdict = (resp.text or "").strip()
        tokens = (getattr(resp, "usage_metadata", None) or {}).get("total_tokens")
        correction = None if not verdict or verdict.strip(" .").upper() == "OK" else verdict
        # las reglas de citas y de datos nuevos se aplican en código sobre lo que diga el verificador
        text, status, notes = citations.enforce(original, correction, "\n\n".join(evidence))
        event = {"tipo": "verificacion", "status": status, "notes": notes, "tokens": tokens}
        if text == original:
            runtime.stream_writer(event)
            return None
        runtime.stream_writer({**event, "text": text, "original": original})
        # el original queda guardado en el mensaje: al recargar el historial la corrección sigue siendo visible
        return {"messages": [AIMessage(id=last.id, content=text, additional_kwargs={
            "answer_verify": {"original": original, "status": status, "notes": notes}})]}


def build_agent(model, tools, settings: Settings, checkpointer=None, store=None, summarizer=None, checker=None):
    """`summarizer`/`checker`: modelos para MEMORY_SUMMARIZE/ANSWER_VERIFY (se inyectan en tests)."""
    middleware = [
        _system_prompt,
        _razonamiento,
        LimiteLlamadas(),
        ToolErrorMiddleware(on_error=_on_tool_error),
        HumanInTheLoopMiddleware(interrupt_on={"enviar_email_simulado": True}),
    ]
    if settings.memory_summarize:
        middleware.insert(0, SummarizationMiddleware(
            summarizer or make_summary_model(settings),
            trigger=("tokens", settings.summary_trigger_tokens),
            keep=("messages", settings.summary_keep_messages),
            summary_prompt=SUMMARY_PROMPT,
            # ponytail: el default (4000, estrategia "last") recorta lo más viejo antes de resumir, y eso incluye el
            # resumen anterior: los datos del inicio se perderían en el segundo resumen. El umbral ya acota la entrada.
            trim_tokens_to_summarize=None,
        ))
    if settings.answer_verify:
        middleware.append(AnswerVerifier(checker or make_checker_model(settings)))
    return create_agent(
        model,
        tools,
        context_schema=Context,
        checkpointer=checkpointer,
        store=store,
        middleware=middleware,
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
        if node.startswith("SummarizationMiddleware") and node_update.get("messages"):
            yield {"type": "summarized"}
            continue
        if node.startswith("AnswerVerifier"):
            continue  # la corrección ya llegó como evento "verify"
        if node.startswith("LimiteLlamadas") and node_update.get("messages"):
            # el middleware corta el turno con un AIMessage que no se streamea.
            yield {"type": "token", "text": f"\n\n_{LIMIT_MSG}_"}
            continue
        for msg in node_update.get("messages", []) or []:
            # nodos de create_agent ("model"/"tools") y de langgraph-bigtool ("agent"/"tools"/"select_tools")
            if node in MODEL_NODES and isinstance(msg, AIMessage):
                for call in msg.tool_calls:
                    yield {
                        "type": "tool_start",
                        "id": call.get("id"),
                        "name": call.get("name"),
                        "args": call.get("args", {}),
                    }
            elif node in ("tools", "select_tools") and isinstance(msg, ToolMessage):
                output = _content_text(msg)
                yield {
                    "type": "tool_end",
                    "id": msg.tool_call_id,
                    "name": msg.name or ("retrieve_tools" if node == "select_tools" else None),
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
                if metadata.get("langgraph_node") not in MODEL_NODES:
                    continue
                if "nostream" in (metadata.get("tags") or []) or metadata.get("lc_source") == SUMMARY_SOURCE:
                    continue
                text = _content_text(token)
                if text:
                    yield {"type": "token", "text": text}
            elif kind == "updates":
                yield from _update_events(data)
            elif kind == "custom" and isinstance(data, dict) and data.get("tipo") == "progreso":
                # avance del investigador profundo (búsquedas internas mientras trabaja)
                yield {"type": "progress", "name": data.get("herramienta"), "args": data.get("args", {})}
            elif kind == "custom" and isinstance(data, dict) and data.get("tipo") == "verificacion":
                yield {"type": "verify", **{k: v for k, v in data.items() if k != "tipo"}}
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
        if isinstance(msg, HumanMessage) and msg.additional_kwargs.get("lc_source") == SUMMARY_SOURCE:
            out.append({"role": "summary"})  # la conversación anterior se resumió (MEMORY_SUMMARIZE)
        elif isinstance(msg, HumanMessage):
            out.append({"role": "user", "content": _content_text(msg)})
        elif isinstance(msg, AIMessage):
            text = _content_text(msg)
            if text:
                out.append({"role": "assistant", "content": text})
                if corrected := msg.additional_kwargs.get("answer_verify"):
                    out[-1]["original"] = corrected.get("original", "")
                    out[-1]["verify"] = {"status": corrected.get("status", "corrected"), "notes": corrected.get("notes", [])}
            for call in msg.tool_calls:
                out.append({"role": "tool", "name": call.get("name")})
    return out
