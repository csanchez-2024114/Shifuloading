"""Construcción del agente y traducción de su stream a eventos SSE (dicts). Todo síncrono."""
import logging
import re
import threading
import unicodedata
import uuid
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
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph._internal._constants import CONFIG_KEY_RUNTIME
from langgraph.config import get_config
from langgraph.errors import GraphRecursionError
from langgraph.runtime import Runtime

from assistant import citations
from assistant.config import Settings, read_system_prompt
from assistant.memory import SUMMARY_SOURCE

logger = logging.getLogger(__name__)

OUTPUT_PREVIEW_CHARS = 500
MODEL_NODES = ("model", "agent")  # "agent" = nodo del modelo en langgraph-bigtool

# Esfuerzo automático: nivel -> (tope de llamadas al modelo en el turno, reasoning effort de Luna).
# El tope de "alto" sale de EFFORT_HIGH_MAX_CALLS (ver contexto_para).
ESFUERZOS = {"bajo": (5, "low"), "medio": (15, "medium"), "alto": (15, "high")}
ESFUERZO_SIN_CLASIFICAR = "bajo"  # mensajes cortos y triviales: no se llama al clasificador
LIMIT_MSG = "Se alcanzó el límite de llamadas al modelo para este mensaje; detuve el proceso. Escribe «continúa» para seguir."
LAST_STEP_NOTE = ("This is your last step for this message: do not call tools. Answer now with what you already have and "
                  "say in one short line, in the user's language, that you stopped at the step limit and they can ask "
                  "you to continue.")
REPEAT_LIMIT_MSG = ("Not run: {name} was already used {limit} times for this message (limit). Do not call it again: "
                    "answer with what you already have and tell the user the work was cut at the tool limit.")
CUT_NOTE = ("\n\n⚠️ La respuesta se cortó por el límite de longitud (MAX_TOKENS). Escribe «continúa» y sigo justo "
            "donde me quedé, sin repetir lo anterior.")
CONTINUE_NOTE = ("Your previous answer was cut by the output limit (the system removed its cut notice). The user asked "
                 "you to continue: continue exactly where it stopped. Do not repeat, summarize or rewrite anything "
                 "already written. If it stopped inside a code block, open a new code block with the same language and "
                 "continue from the next line.")
# "continúa", "sigue", "continue"... como mensaje corto tras una respuesta cortada
_CONTINUE_RE = re.compile(r"^\W*(contin[uú]a|continuar|sigue|segu[ií]|seguir|dale|continue|go on|keep going)\b", re.I)


@dataclass
class Context:
    user_id: str = "anon"
    max_llamadas: int = 15       # 0 = sin tope
    razonamiento: str | None = None  # None = default del modelo
    max_tokens: int | None = None    # tope de salida de este mensaje (esfuerzo alto); None = MAX_TOKENS


# Señales de que un mensaje corto aún necesita clasificarse: dígitos, operadores, código o verbos de trabajo.
_SIGNAL_RE = re.compile(r"\d|[+*/=^%×÷√<>]|```")
_SIGNAL_WORDS = ("calcul", "resuelv", "resolv", "optimi", "demuestr", "demostr", "plan", "disen", "codigo",
                 "program", "investig", "compar", "analiz", "calculate", "solve", "optimiz", "prove", "design",
                 "code", "research", "compare",
                 # actualidad: "¿quién ganó el último partido?" es corto pero necesita buscar (sin tildes: ya normalizado)
                 "ultim", "hoy", "ayer", "gano", "ganador", "precio", "noticia", "cotiza",
                 "latest", "last", "today", "yesterday", "won", "winner", "price", "news")
SHORT_MESSAGE_CHARS = 60


def necesita_clasificador(mensaje: str) -> bool:
    """False solo para mensajes cortos sin dígitos, operadores, código ni palabras de trabajo ("hola", "gracias")."""
    texto = _strip_accents(mensaje.strip().lower())
    if len(texto) > SHORT_MESSAGE_CHARS or _SIGNAL_RE.search(texto):
        return True
    return any(w.startswith(sig) for w in re.findall(r"\w+", texto) for sig in _SIGNAL_WORDS)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def elegir_esfuerzo(settings: Settings, mensaje: str, elegido: str | None, classify) -> tuple[str | None, str]:
    """(esfuerzo, origen). origen: "manual" (selector de la UI), "auto" (clasificador) o "regla" (mensaje corto).
    Con MODEL_CALL_LIMIT>0 no hay esfuerzo (tope fijo)."""
    if settings.model_call_limit > 0:
        return None, "fijo"
    if elegido in ESFUERZOS:
        return elegido, "manual"
    if not necesita_clasificador(mensaje):
        return ESFUERZO_SIN_CLASIFICAR, "regla"
    return classify(settings, mensaje), "auto"


_CLASSIFIER_LEVELS = {"low": "bajo", "medium": "medio", "high": "alto"}  # el prompt del modelo va en inglés
CLASSIFIER_PROMPT = (
    "Classify the effort this message requires from an assistant with tools. "
    "Reply with ONLY one of these words: low, medium, high.\n"
    "low = greeting, small talk, a simple fact, a single quick lookup or calculation, or a request the assistant "
    "cannot do (set alarms, send messages, call someone);\n"
    "medium = a web search, a short multi-step calculation, a normal explanation, ordinary code (a script, a query, a "
    "fix) or a plan or text written from the details given;\n"
    "high = ONLY when the user asks for in-depth research or a comparison across several sources, or for a genuinely "
    "hard problem (a proof, a complex optimization, debugging a large program). A trip or study plan, ordinary code "
    "or anything the assistant cannot do is never high.\n\n"
    "Message: "
)


def clasificar_esfuerzo(settings: Settings, mensaje: str) -> str:
    """Clasifica el esfuerzo del mensaje (bajo/medio/alto) con una llamada rápida sin razonamiento.
    Ante cualquier fallo devuelve "medio"."""
    try:
        llm = ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key or None,
                         use_responses_api=True, reasoning={"effort": "none"}, max_tokens=16)
        palabra = llm.invoke(CLASSIFIER_PROMPT + mensaje[:2000]).text.strip().lower()
        return next((nivel for word, nivel in _CLASSIFIER_LEVELS.items() if word in palabra), "medio")
    except Exception as exc:  # noqa: BLE001
        logger.warning("No pude clasificar el esfuerzo (%s); uso 'medio'", exc)
        return "medio"


def contexto_para(user_id: str, settings: Settings, esfuerzo: str | None) -> Context:
    """MODEL_CALL_LIMIT>0 fija el tope; 0 = automático según el esfuerzo."""
    if settings.model_call_limit > 0 or esfuerzo not in ESFUERZOS:
        return Context(user_id=user_id, max_llamadas=settings.model_call_limit or 15)
    max_llamadas, razonamiento = ESFUERZOS[esfuerzo]
    max_tokens = None
    if esfuerzo == "alto":
        max_llamadas = settings.effort_high_max_calls
        # margen de salida: con esfuerzo alto el razonamiento se comía MAX_TOKENS (prueba real: código cortado a
        # mitad con 7,370 de 8,000 tokens razonando). Sin tocar MAX_TOKENS=0 (sin tope) ni bajar un valor mayor.
        if settings.max_tokens and settings.effort_high_max_tokens > settings.max_tokens:
            max_tokens = settings.effort_high_max_tokens
    return Context(user_id=user_id, max_llamadas=max_llamadas, razonamiento=razonamiento, max_tokens=max_tokens)


class LimiteLlamadas(ModelCallLimitMiddleware):
    """Como ModelCallLimitMiddleware, pero el tope sale de runtime.context.max_llamadas (por mensaje).
    La última llamada permitida va sin herramientas: el modelo responde con lo que tiene y avisa del corte."""

    def __init__(self):
        super().__init__(run_limit=10**9, exit_behavior="end")  # el tope real viene del contexto

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        limite = getattr(runtime.context, "max_llamadas", 0)
        if limite and state.get("run_model_call_count", 0) >= limite:
            return {"jump_to": "end", "messages": [AIMessage(content=LIMIT_MSG)]}
        return None

    def wrap_model_call(self, request, handler):
        limite = getattr(request.runtime.context, "max_llamadas", 0)
        if limite > 1 and request.tools and request.state.get("run_model_call_count", 0) == limite - 1:
            system = request.system_message.text if request.system_message else ""
            request = request.override(tool_choice="none",
                                       system_message=SystemMessage(content=f"{system}\n\n{LAST_STEP_NOTE}".strip()))
        return handler(request)


def _turn_messages(messages) -> list:
    """Mensajes del turno en curso: desde el último mensaje del usuario (el resumen no cuenta como usuario)."""
    start = max((i for i, m in enumerate(messages) if m.type == "human"
                 and m.additional_kwargs.get("lc_source") != SUMMARY_SOURCE), default=-1)
    return messages[start + 1:]


class LimiteRepeticiones(AgentMiddleware):
    """TOOL_REPEAT_LIMIT: una misma herramienta no corre más de N veces por mensaje; a partir de ahí devuelve un
    aviso (sin ejecutarla) para que el modelo responda con lo que tiene."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def wrap_tool_call(self, request, handler):
        name, call_id = request.tool_call["name"], request.tool_call.get("id")
        calls = [c.get("id") for m in _turn_messages(request.state.get("messages") or [])
                 if isinstance(m, AIMessage) for c in m.tool_calls if c.get("name") == name]
        if self.limit and call_id in calls and calls.index(call_id) >= self.limit:
            return ToolMessage(content=REPEAT_LIMIT_MSG.format(name=name, limit=self.limit),
                               tool_call_id=call_id, name=name, status="error")
        return handler(request)


def _cut_and_empty(response) -> bool:
    msg = next((m for m in reversed(getattr(response, "result", None) or []) if isinstance(m, AIMessage)), None)
    meta = getattr(msg, "response_metadata", None) or {}
    return (msg is not None and not msg.tool_calls and not _content_text(msg).strip()
            and (meta.get("incomplete_details") or {}).get("reason") == "max_output_tokens")


class AvisoCorte(AgentMiddleware):
    """Si la respuesta final se cortó por MAX_TOKENS (max_output_tokens), lo dice al final del mensaje y ofrece
    continuar, en vez de terminar a media frase sin explicación.
    Si se cortó SIN texto (MAX_TOKENS incluye el razonamiento: con esfuerzo alto puede agotarse antes de escribir),
    repite esa llamada una vez con razonamiento bajo. Prueba real: H12 con MAX_TOKENS=2000 y esfuerzo alto terminó en
    una respuesta vacía aunque la investigación había salido bien."""

    def wrap_model_call(self, request, handler):
        request = _continue_cut(request)
        response = handler(request)
        if _cut_and_empty(response):
            logger.info("Respuesta vacía por MAX_TOKENS (todo fue razonamiento); repito con razonamiento bajo")
            response = handler(request.override(
                model_settings={**request.model_settings, "reasoning": {"effort": "low"}}))
        return response

    def after_model(self, state, runtime):
        last = (state.get("messages") or [None])[-1]
        meta = getattr(last, "response_metadata", None) or {}
        reason = (meta.get("incomplete_details") or {}).get("reason")
        if not isinstance(last, AIMessage) or last.tool_calls or reason != "max_output_tokens":
            return None
        runtime.stream_writer({"tipo": "corte"})
        return {"messages": [AIMessage(id=last.id, content=_content_text(last) + CUT_NOTE, additional_kwargs={"cut": True},
                                       response_metadata=meta, usage_metadata=last.usage_metadata)]}


def _continue_cut(request):
    """Tras una respuesta cortada, un "continúa" debe seguir donde quedó, no rehacerla: el modelo ve la respuesta sin el
    aviso (en español, para el usuario) y CONTINUE_NOTE. Prueba real: rehízo el script entero en vez de continuarlo."""
    msgs = request.messages
    if len(msgs) < 2 or msgs[-1].type != "human" or not _CONTINUE_RE.match(_content_text(msgs[-1])):
        return request
    i = next((k for k in range(len(msgs) - 2, -1, -1) if isinstance(msgs[k], AIMessage)), None)
    if i is None or not msgs[i].additional_kwargs.get("cut"):
        return request
    text = _content_text(msgs[i])
    cut = msgs[i].model_copy(update={"content": text[:-len(CUT_NOTE)] if text.endswith(CUT_NOTE) else text})
    system = request.system_message.text if request.system_message else ""
    return request.override(messages=[*msgs[:i], cut, *msgs[i + 1:]],
                            system_message=SystemMessage(content=f"{system}\n\n{CONTINUE_NOTE}".strip()))


# Nombres anteriores (en español) de las herramientas. Los hilos guardados antes del cambio los tienen en su
# historial (llamadas y resultados) y bigtool en selected_tool_ids.
OLD_TOOL_NAMES = {"buscar_web": "web_search", "calculadora": "calculator", "fecha_hora": "current_datetime",
                  "guardar_recuerdo": "save_memory", "buscar_recuerdos": "search_memories",
                  "actualizar_recuerdo": "update_memory", "investigador_profundo": "deep_research",
                  "enviar_email_simulado": "send_simulated_email"}


def rename_old_tools(messages) -> list:
    """Copia de los mensajes con los nombres antiguos de herramientas cambiados por los actuales, para que el modelo
    no vea llamadas a herramientas que ya no existen. No toca el historial guardado."""
    out = []
    for m in messages:
        if isinstance(m, AIMessage) and any(c.get("name") in OLD_TOOL_NAMES for c in m.tool_calls):
            calls = [{**c, "name": OLD_TOOL_NAMES.get(c["name"], c["name"])} for c in m.tool_calls]
            content = m.content
            if isinstance(content, list):  # Responses API: también hay bloques function_call con el nombre
                content = [{**b, "name": OLD_TOOL_NAMES[b["name"]]} if isinstance(b, dict) and b.get("name")
                           in OLD_TOOL_NAMES else b for b in content]
            m = m.model_copy(update={"tool_calls": calls, "content": content})
        elif isinstance(m, ToolMessage) and m.name in OLD_TOOL_NAMES:
            m = m.model_copy(update={"name": OLD_TOOL_NAMES[m.name]})
        out.append(m)
    return out


@wrap_model_call
def _nombres_antiguos(request, handler):
    return handler(request.override(messages=rename_old_tools(request.messages)))


@wrap_model_call
def _razonamiento(request, handler):
    effort = getattr(request.runtime.context, "razonamiento", None)
    if effort:
        request = request.override(model_settings={**request.model_settings, "reasoning": {"effort": effort}})
    if max_tokens := getattr(request.runtime.context, "max_tokens", None):
        request = request.override(model_settings={**request.model_settings, "max_tokens": max_tokens})
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
- the user's stated preferences, likes, dislikes and personal facts (name, job, city...), attributed to the user;
- open questions, pending tasks and commitments the assistant made.

Always end with a section "Problems solved so far": one bullet per problem, question or task already answered
(the oldest first), each with its final result or answer verbatim (numbers, names, chosen option). Keep every item
from the earlier summary's list and add the new ones; never drop one.

Rules:
- If the messages start with an earlier summary, merge it in: keep all of its facts unless the user corrected them.
- Write facts the user stated as "The user said ...". Do not add facts, guesses or interpretations.
- Mark clearly what came from tools (web results, calculations) versus from the user.
- Write in the conversation's language. Use short bullet points grouped by topic. No preamble.

<messages>
{messages}
</messages>"""


class ResumenPorTurno(SummarizationMiddleware):
    """SummarizationMiddleware con dos cambios (MEMORY_SUMMARIZE):
    - como máximo un resumen por turno: el mensaje de resumen guarda el id del mensaje del usuario que abría el turno;
    - el disparo mira solo los tokens de los mensajes, igual que `keep`. El nativo también dispara con el uso
      reportado por el último AIMessage, que suma system prompt, herramientas y salida: tras resumir seguía por
      encima del umbral y volvía a resumir en cada llamada (hasta 3 resúmenes en un turno en la prueba larga)."""

    def _should_summarize_based_on_reported_tokens(self, messages, threshold):
        return False

    def before_model(self, state, runtime):
        messages = state["messages"]
        self._ensure_message_ids(messages)
        human = next((m for m in reversed(messages) if m.type == "human"
                      and m.additional_kwargs.get("lc_source") != SUMMARY_SOURCE), None)
        # sin mensaje del usuario en el estado: el resumen de este turno ya se lo llevó
        if human is None or any(m.additional_kwargs.get("summary_turn") == human.id for m in messages
                                if m.type == "human"):
            return None
        update = super().before_model(state, runtime)
        for m in (update or {}).get("messages", []):
            if isinstance(m, HumanMessage) and m.additional_kwargs.get("lc_source") == SUMMARY_SOURCE:
                m.additional_kwargs["summary_turn"] = human.id
        return update


def _confirm_text() -> str:
    from assistant.tools import DEEP_RESEARCH_CONFIRM
    return DEEP_RESEARCH_CONFIRM


def _research_needs_confirmation(request) -> bool:
    from assistant.tools import research_needs_confirmation
    return research_needs_confirmation(request.state.get("messages"))


def _on_tool_error(exc: Exception, request) -> str:
    return f"Tool error ({type(exc).__name__}): {exc}. Try another approach."


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


EVIDENCE_TOOLS = ("web_search", "deep_research")
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


# resultados de herramientas que NO se ejecutaron: límites, cancelaciones por tope y rechazos del usuario
NOT_RUN_PREFIXES = ("Not run:", "Cancelled:", "User rejected the tool call")
_REUSED_RESEARCH = "Not run: this conversation already has research"  # trae los resultados anteriores: sí es evidencia


def tool_ran(output: str) -> bool:
    return not output.lstrip().startswith(NOT_RUN_PREFIXES)


def is_evidence(output: str) -> bool:
    return tool_ran(output) or output.lstrip().startswith(_REUSED_RESEARCH)


class AnswerVerifier(AgentMiddleware):
    """ANSWER_VERIFY: al terminar el turno, si se usó web_search/deep_research, una llamada barata
    contrasta la respuesta con lo recuperado. Si corrige, reemplaza el mensaje (mismo id) y avisa a la UI con el
    original: el cambio nunca es silencioso. Sin búsqueda en el turno no hace nada (0 tokens)."""

    def __init__(self, checker):
        super().__init__()
        self.checker = checker

    def after_agent(self, state, runtime):
        messages = state.get("messages") or []
        start = max((i for i, m in enumerate(messages) if m.type == "human"), default=-1) + 1
        turn = messages[start:]
        # solo lo que se ejecutó de verdad es evidencia: una búsqueda rechazada ("Not run: …") no aporta nada
        evidence = [_content_text(m) for m in turn if isinstance(m, ToolMessage) and m.name in EVIDENCE_TOOLS
                    and is_evidence(_content_text(m))]
        last = turn[-1] if turn else None
        if not evidence or not isinstance(last, AIMessage) or last.tool_calls or not _content_text(last).strip():
            return None
        original = _content_text(last)
        runtime.stream_writer({"tipo": "fase", "fase": "verifying"})  # la UI muestra "verificando…" mientras tanto
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
        _nombres_antiguos,
        _razonamiento,
        LimiteLlamadas(),
        AterrizajeSuave(settings.turn_token_cap),
        ToolErrorMiddleware(on_error=_on_tool_error),
        LimiteRepeticiones(settings.tool_repeat_limit),
        HumanInTheLoopMiddleware(interrupt_on={
            "send_simulated_email": True,
            # pausa con la tarjeta de aprobación, salvo que el usuario haya pedido investigar en ese mensaje
            "deep_research": {"allowed_decisions": ["approve", "reject"], "description": _confirm_text(),
                              "when": _research_needs_confirmation},
        }),
        AvisoCorte(),
    ]
    if settings.memory_summarize:
        middleware.insert(0, ResumenPorTurno(
            summarizer or make_summary_model(settings),
            trigger=("tokens", settings.summary_trigger_tokens),
            # lo conservado queda muy por debajo del umbral: si no, el siguiente mensaje vuelve a dispararlo
            keep=("tokens", min(settings.summary_keep_tokens, settings.summary_trigger_tokens // 2)),
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
    if first.startswith("[engine:") and first.endswith("]"):
        return first[len("[engine:"):-1].strip() or None
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
        if node.startswith(("ResumenPorTurno", "SummarizationMiddleware")) and node_update.get("messages"):
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
            # el rechazo en la tarjeta de aprobación lo escribe el middleware HITL, no el nodo "tools"
            elif (node in ("tools", "select_tools") or node.startswith("HumanInTheLoopMiddleware")) \
                    and isinstance(msg, ToolMessage):
                output = _content_text(msg)
                yield {
                    "type": "tool_end",
                    "id": msg.tool_call_id,
                    "name": msg.name or ("retrieve_tools" if node == "select_tools" else None),
                    "output": output[:OUTPUT_PREVIEW_CHARS],
                    "status": _tool_status(msg, output),
                    "engine": _engine_from_output(output),
                }


# avisos al usuario: texto plano (la interfaz no interpreta _cursiva_ y mostraba los guiones bajos)
TURN_CAP_MSG = ("\n\n⚠️ Detuve este mensaje: superó el tope de {cap} tokens por mensaje (TURN_TOKEN_CAP). Lo que "
                "alcancé a hacer puede estar incompleto; si lo necesitas, pídemelo con una pregunta más acotada.")
SOFT_CAP_RATIO = 0.8  # al llegar a este % de TURN_TOKEN_CAP, última llamada sin herramientas


def turn_cap_msg(cap: int) -> str:
    return TURN_CAP_MSG.format(cap=f"{cap:,}".replace(",", "."))  # 45.000, como se escribe en español


def _step_kind(chunk) -> str | None:
    """Qué paso del grafo raíz cierra este chunk: "final" (el modelo respondió sin herramientas), "tools" (el modelo
    pidió herramientas), "other" (otro nodo, p. ej. herramientas) o None (tokens, avisos o subgrafos)."""
    if chunk.get("ns") or chunk.get("type") != "updates":
        return None
    for node, update in (chunk.get("data") or {}).items():
        msgs = (update or {}).get("messages") if node in MODEL_NODES and isinstance(update, dict) else None
        if msgs and isinstance(msgs[-1], AIMessage):
            return "tools" if msgs[-1].tool_calls else "final"
    return "other"
SOFT_CAP_NOTE = ("This message is close to its token budget: do not call tools. Answer now using only what you already "
                 "retrieved, and tell the user in one short line, in their language, what you could not complete and "
                 "that they can ask for it in a new, narrower message.")
CANCELLED_TOOL_MSG = "Cancelled: this message reached its token cap before the tool finished."


class TurnTokens(BaseCallbackHandler):
    """TURN_TOKEN_CAP: suma entrada+salida de todas las llamadas al modelo de un mensaje (agente, resumen,
    verificadores, investigador y búsquedas hospedadas, que heredan los callbacks de la config)."""

    def __init__(self):
        self.total = 0
        self.landing = False  # ya se hizo la última llamada sin herramientas (aterrizaje suave)
        self._lock = threading.Lock()

    def on_llm_end(self, response, **kwargs):
        for gens in response.generations:
            for g in gens:
                usage = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                with self._lock:
                    self.total += usage.get("total_tokens", 0) or 0


_ACTIVE_TURNS: dict[str, TurnTokens] = {}  # hilo -> contador del mensaje en curso


def landing_due(cap: int) -> TurnTokens | None:
    """Contador del mensaje en curso si ya llegó al SOFT_CAP_RATIO de TURN_TOKEN_CAP (hay que aterrizar); si no, None.
    Se llama dentro del grafo: el hilo sale de la config de la ejecución."""
    if not cap:
        return None
    try:
        thread_id = get_config()["configurable"].get("thread_id")
    except RuntimeError:  # fuera de un grafo
        return None
    counter = _ACTIVE_TURNS.get(thread_id)
    return counter if counter and counter.total >= cap * SOFT_CAP_RATIO else None


class AterrizajeSuave(AgentMiddleware):
    """TURN_TOKEN_CAP con aterrizaje suave: al llegar al 80% del tope, la siguiente llamada va sin herramientas y con
    SOFT_CAP_NOTE, así el usuario recibe una respuesta con lo ya recuperado en vez de solo el aviso de aborto."""

    def __init__(self, cap: int):
        super().__init__()
        self.cap = cap

    def wrap_model_call(self, request, handler):
        if request.tools and (counter := landing_due(self.cap)):
            counter.landing = True
            system = request.system_message.text if request.system_message else ""
            request = request.override(tool_choice="none",
                                       system_message=SystemMessage(content=f"{system}\n\n{SOFT_CAP_NOTE}".strip()))
        return handler(request)


def turn_tokens(thread_id: str | None) -> int:
    """Tokens gastados por el mensaje en curso del hilo (0 si no hay ninguno). Las búsquedas lo consultan antes de
    lanzarse."""
    counter = _ACTIVE_TURNS.get(thread_id) if thread_id else None
    return counter.total if counter else 0


def _close_aborted_turn(agent, config, note: str) -> None:
    """Deja el hilo consistente tras abortar: las llamadas a herramientas sin respuesta reciben un "cancelado" (si no,
    el siguiente mensaje fallaría en la API) y el aviso queda guardado como respuesta del asistente.

    El aborto suele llegar a mitad de un paso del grafo: lo que ya produjo el paso (la respuesta del modelo con sus
    llamadas, las herramientas que terminaron) solo está en las escrituras pendientes del último checkpoint.
    `update_state` reutilizaría el id de tarea de ese nodo y escribiría en el mismo checkpoint con el mismo índice
    (MongoDB lo rechaza con E11000). Por eso va con un id de tarea propio y reenvía los mensajes del turno tal como
    los ve `get_state` (que incluye lo pendiente): `add_messages` reemplaza por id los ya guardados y agrega el resto."""
    cancelled: list = []
    try:
        messages = (agent.get_state(config).values or {}).get("messages") or []
        turn = _turn_messages(messages)
        answered = {m.tool_call_id for m in turn if isinstance(m, ToolMessage)}
        cancelled = [ToolMessage(content=CANCELLED_TOOL_MSG, tool_call_id=c["id"], name=c.get("name"), status="error")
                     for m in turn if isinstance(m, AIMessage) for c in m.tool_calls if c.get("id") not in answered]
        node = "model" if "model" in agent.nodes else "agent"  # create_agent / langgraph-bigtool
        cfg = config
        if getattr(agent, "store", None) is not None:
            # update_state no da el store a las ramas (el bucle del grafo sí, vía Runtime en la config): sin esto,
            # la rama should_continue de bigtool falla con "Missing required config key 'store'"
            cfg = {**config, "configurable": {**config["configurable"], CONFIG_KEY_RUNTIME: Runtime(store=agent.store)}}
        agent.update_state(cfg, {"messages": [*turn, *cancelled, AIMessage(content=note.strip())]},
                           as_node=node, task_id=str(uuid.uuid4()))
    except Exception:  # noqa: BLE001 - el aviso al usuario sale igual
        logger.exception(
            "Mensaje abortado por TURN_TOKEN_CAP en el hilo %s: NO se guardó su cierre (%d llamada(s) a herramientas "
            "como canceladas y el aviso al usuario). El usuario sí recibió el aviso; el siguiente mensaje parte del "
            "último checkpoint guardado.", config.get("configurable", {}).get("thread_id"), len(cancelled))


def stream_events(agent, payload, thread_id: str, user_id: str, settings: Settings,
                  esfuerzo: str | None = None, origen: str = "auto") -> Iterator[dict]:
    ctx = contexto_para(user_id, settings, esfuerzo)
    if esfuerzo in ESFUERZOS and settings.model_call_limit == 0:
        yield {"type": "effort", "level": esfuerzo, "max_calls": ctx.max_llamadas, "reasoning": ctx.razonamiento,
               "source": origen}
    config = run_config(thread_id, settings)
    # cada llamada al modelo gasta ~6 pasos del grafo (middlewares + tools): el límite de pasos acompaña al tope
    config["recursion_limit"] = max(config["recursion_limit"], ctx.max_llamadas * 8)
    counter = TurnTokens()
    config["callbacks"] = [counter]  # cuenta todas las llamadas del mensaje (agente, investigador, búsquedas...)
    _ACTIVE_TURNS[thread_id] = counter
    cap = settings.turn_token_cap
    try:
        stream = agent.stream(
            payload,
            config=config,
            context=ctx,
            stream_mode=["messages", "updates", "custom"],
            version="v2",
        )
        for chunk in stream:
            # último recurso: se cruzó el tope sin aterrizaje suave (p. ej. del 70% al 110% en una llamada). Se
            # espera al cierre del paso: si el modelo ya dio la respuesta final, el mensaje termina solo (prueba real:
            # el aviso se pegaba detrás de una respuesta completa); si pidió herramientas o terminó otro nodo, se
            # aborta antes de la siguiente llamada. Los tokens de la llamada que cruzó el tope siguen llegando.
            step = _step_kind(chunk) if cap and counter.total >= cap and not counter.landing else None
            if step == "final":
                counter.landing = True
            elif step in ("tools", "other"):
                stream.close()  # aborta el turno: no se lanzan más llamadas
                note = turn_cap_msg(cap)
                _close_aborted_turn(agent, config, note)
                yield {"type": "token", "text": note}
                break
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
            elif kind == "custom" and isinstance(data, dict) and data.get("tipo") == "fase":
                yield {"type": "phase", "phase": data.get("fase")}
            elif kind == "custom" and isinstance(data, dict) and data.get("tipo") == "corte":
                yield {"type": "token", "text": CUT_NOTE}  # la respuesta se cortó por MAX_TOKENS
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
    finally:
        _ACTIVE_TURNS.pop(thread_id, None)
    yield {"type": "done", "thread_id": thread_id}


def _tool_status(msg: ToolMessage, output: str) -> str:
    """"skipped" si la herramienta no se ejecutó (la UI no debe mostrar "✓"), "error" o "success"."""
    if not tool_ran(output):
        return "skipped"
    return "error" if msg.status == "error" else "success"


def get_history(agent, thread_id: str, settings: Settings) -> list[dict]:
    state = agent.get_state(run_config(thread_id, settings))
    out: list[dict] = []
    messages = (state.values or {}).get("messages", [])
    results = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
    for msg in messages:
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
                result = results.get(call.get("id"))
                if result is not None and (status := _tool_status(result, _content_text(result))) != "success":
                    out[-1]["status"] = status  # "skipped" o "error": se ve igual al recargar
    return out
