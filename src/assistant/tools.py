"""Herramientas del asistente (en español). Todas síncronas."""
import ast
import logging
import math
import operator
import re
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.callbacks import BaseCallbackHandler, get_usage_metadata_callback
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from assistant import memory
from assistant.agent import OLD_TOOL_NAMES, Context
from assistant.config import Settings

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- calculadora

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}
_FUNCS = {
    name: getattr(math, name)
    for name in (
        "sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "log", "log10", "log2",
        "exp", "floor", "ceil", "fabs", "factorial", "radians", "degrees", "hypot", "gcd",
    )
}
_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})
_MAX_POW = 10_000  # evita 9**9**9 y similares


def _eval_node(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POW:
            raise ValueError("exponent too large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "math":
        if node.attr in _NAMES:
            return _NAMES[node.attr]
        raise ValueError(f"constant not allowed: math.{node.attr}")
    if isinstance(node, ast.Call) and not node.keywords:
        fn = None
        if isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            fn = _FUNCS[node.func.id]
        elif (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "math"
            and node.func.attr in _FUNCS
        ):
            fn = _FUNCS[node.func.attr]
        if fn is not None:
            return fn(*[_eval_node(a) for a in node.args])
    raise ValueError("expression not allowed")


@tool("calculator")
def calculadora(expression: str) -> str:
    """Calculator: evaluates a math expression and returns the exact result.

    Supports + - * / // % ** and parentheses, plus math functions/constants (sqrt, sin, cos, tan,
    log, log10, exp, factorial, abs, round, min, max, pi, e...). Example: "sqrt(144) + 2**10 / 4".
    Always use it for arithmetic instead of computing from memory.
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree)
    except ZeroDivisionError:
        return "Error: division by zero."
    except SyntaxError:
        return f"Error: invalid expression: {expression!r}"
    except (ValueError, TypeError, OverflowError) as exc:
        return f"Error: {exc}"
    if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
        result = int(result)
    return str(result)


# --------------------------------------------------------------------------- fecha y hora

@tool("current_datetime")
def fecha_hora(time_zone: str = "local") -> str:
    """Returns the current date and time (ISO 8601) and the day of the week.

    `time_zone` is optional: "local" (default) or an IANA time zone name,
    e.g. "America/Mexico_City", "Europe/Madrid", "UTC".
    """
    try:
        if not time_zone or time_zone.strip().lower() == "local":
            now = datetime.now().astimezone()
        elif time_zone.strip().upper() == "UTC":
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now(ZoneInfo(time_zone.strip()))
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return (
            f"Error: unknown or unavailable time zone: {time_zone!r}. "
            "Use an IANA name such as 'America/Mexico_City'."
        )
    return f"{now.isoformat(timespec='seconds')} ({now:%A})"


# --------------------------------------------------------------------------- memoria


GUARDAR_RECUERDO_DOC = """Saves a stable fact about the user to long-term memory (name, likes, preferences,
work context). Only save what the user explicitly said about themselves, never your own assumptions.

Args:
    text: The fact as a complete, self-contained sentence written in the user's language
        (e.g. for an English speaker: "The user's name is Ana and they prefer short answers").
    evidence: The user's exact words that state this fact, copied verbatim from their message.
"""


def make_guardar_recuerdo(verifier=None) -> BaseTool:
    """`verifier` (MEMORY_VERIFY): (candidato, textos_usuario) -> (respaldado, cita); None = sin verificar."""

    @tool("save_memory", description=GUARDAR_RECUERDO_DOC)
    def guardar_recuerdo(text: str, runtime: ToolRuntime[Context], evidence: str = "") -> str:
        texts = memory.user_texts(runtime.state.get("messages"))
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        return memory.remember(runtime.store, runtime.context.user_id, text, evidence, texts,
                               thread_id=thread_id, verifier=verifier)

    return guardar_recuerdo


guardar_recuerdo = make_guardar_recuerdo()


BUSCAR_RECUERDOS_DOC = """Searches long-term memory for what is known about the user. Pass topic keywords in the
language the memories were saved in, or an empty string to get the most recent memories.
Each result starts with its id, which update_memory needs."""

ACTUALIZAR_RECUERDO_DOC = """Replaces the text of an EXISTING memory (get its id from search_memories). Use it when the
user confirms that a saved fact changed, instead of saving a second, contradictory memory. Only use it with what
the user explicitly said; never with your own assumptions. It cannot delete memories.

Args:
    id: The memory id shown by search_memories.
    text: The new fact as a complete, self-contained sentence in the user's language.
    evidence: The user's exact words that state the new value, copied verbatim from their message.
"""


def make_buscar_recuerdos(min_score: float = 0.0) -> BaseTool:
    """`min_score` (MEMORY_MIN_SCORE) solo filtra la búsqueda semántica (Atlas)."""

    @tool("search_memories", description=BUSCAR_RECUERDOS_DOC)
    def buscar_recuerdos(query: str, runtime: ToolRuntime[Context]) -> str:
        return memory.recall(runtime.store, runtime.context.user_id, query, min_score)

    return buscar_recuerdos


buscar_recuerdos = make_buscar_recuerdos()


def make_actualizar_recuerdo(verifier=None) -> BaseTool:
    """Misma verificación que save_memory. Solo toca recuerdos del user_id del contexto."""

    @tool("update_memory", description=ACTUALIZAR_RECUERDO_DOC)
    def actualizar_recuerdo(id: str, text: str, runtime: ToolRuntime[Context], evidence: str = "") -> str:  # noqa: A002
        texts = memory.user_texts(runtime.state.get("messages"))
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        return memory.revise(runtime.store, runtime.context.user_id, id, text, evidence, texts,
                             thread_id=thread_id, verifier=verifier)

    return actualizar_recuerdo


# --------------------------------------------------------------------------- HITL demo


@tool("send_simulated_email")
def enviar_email_simulado(recipient: str, subject: str, body: str) -> str:
    """Sends an email (SIMULATED: nothing is actually sent). Requires human approval
    before it runs.
    """
    return f"Simulated email sent to {recipient} with subject {subject!r} ({len(body)} characters)."


# --------------------------------------------------------------------------- búsqueda web


def _ddg_search(query: str) -> str:
    from ddgs import DDGS

    results = DDGS().text(query, max_results=5)
    if not results:
        return "No results."
    blocks = []
    for r in results:
        blocks.append(f"{r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')}")
    return "\n\n".join(blocks)


def web_search(query: str, settings: Settings) -> tuple[str, str]:
    """Devuelve (texto, motor). Primero web_search hospedado de OpenAI; si falla, DuckDuckGo."""
    try:
        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key or None,
            use_responses_api=True,
            tags=["nostream"],
        ).bind_tools([{"type": "web_search", "search_context_size": settings.search_context_size}],
                     # max_tool_calls: tope de búsquedas internas en esta llamada (cada una suma páginas como entrada)
                     **({"max_tool_calls": settings.search_max_tool_calls} if settings.search_max_tool_calls else {}))
        text = llm.invoke(query).text
        if not text or not text.strip():
            raise ValueError("respuesta vacía del web_search hospedado")
        return text, "openai_web_search"
    except Exception as exc:  # noqa: BLE001 - cualquier fallo cae a DuckDuckGo
        logger.warning("web_search de OpenAI falló (%s: %s); usando DuckDuckGo", type(exc).__name__, exc)
    return _ddg_search(query), "duckduckgo"


BUSCAR_WEB_DOC = """Searches the web for current information and returns a summary with sources. Use it for
news, recent data or anything that may have changed."""
WEB_BUDGET_MSG = ("Not run: the web search budget for this message is used up. Do not search again: answer with what "
                  "you already have and tell the user the result may be incomplete.")
WEB_LIMIT_MSG = ("Not run: the maximum number of web searches for this message was reached. Do not search again: "
                 "answer with what you already have and tell the user the result may be incomplete.")
TURN_CAP_TOOL_MSG = ("Not run: this message is close to its token cap. Do not search again: answer now with what you "
                     "already have and tell the user the result may be incomplete.")


class TurnBudget:
    """Gasto en búsqueda web de un mensaje del usuario, compartido por web_search y el investigador: tokens (búsquedas
    hospedadas + llamadas del investigador) y número de búsquedas. El candado hace que las búsquedas del mismo
    mensaje vayan de una en una, para que el tope se cumpla aunque el modelo las pida en paralelo."""

    def __init__(self):
        self.tokens = 0
        self.searches = 0
        self.lock = threading.Lock()


_TURNS: OrderedDict = OrderedDict()  # (hilo, id del mensaje del usuario) -> TurnBudget
_TURNS_GUARD = threading.Lock()


def turn_budget(key) -> TurnBudget | None:
    if not key:
        return None
    with _TURNS_GUARD:
        budget = _TURNS.setdefault(key, TurnBudget())
        while len(_TURNS) > 256:
            _TURNS.popitem(last=False)
        return budget


def turn_key(thread_id: str | None, messages) -> tuple | None:
    """(hilo, id del mensaje del usuario que abrió el turno): agrupa el gasto de búsqueda por mensaje."""
    human = next((m for m in reversed(messages or []) if getattr(m, "type", None) == "human"
                  and (m.additional_kwargs or {}).get("lc_source") != memory.SUMMARY_SOURCE), None)
    return (thread_id, human.id) if thread_id and human is not None and human.id else None


def run_search(settings: Settings, search_fn, query: str, budget: TurnBudget | None,
               thread_id: str | None = None) -> tuple[bool, str, int]:
    """(se hizo, texto para el modelo, tokens). Antes de buscar reserva el costo estimado (SEARCH_COST_ESTIMATE): no
    busca si con él se pasaría INVESTIGATOR_TOKEN_BUDGET, TURN_MAX_SEARCHES o TURN_TOKEN_CAP. Así el presupuesto solo
    se supera si una búsqueda cuesta más que su estimado."""
    from assistant.agent import turn_tokens

    est = settings.search_cost_estimate
    with budget.lock if budget else threading.Lock():
        if budget is not None:
            if settings.turn_max_searches and budget.searches >= settings.turn_max_searches:
                return False, WEB_LIMIT_MSG, 0
            if settings.investigator_token_budget and budget.tokens + est > settings.investigator_token_budget:
                return False, WEB_BUDGET_MSG, 0
        if settings.turn_token_cap and thread_id and turn_tokens(thread_id) + est > settings.turn_token_cap:
            return False, TURN_CAP_TOOL_MSG, 0
        with get_usage_metadata_callback() as usage:
            text, engine = search_fn(query, settings)
        tokens = sum(u.get("total_tokens", 0) or 0 for u in usage.usage_metadata.values())
        if budget is not None:
            budget.searches += 1
            budget.tokens += tokens
    return True, f"[engine: {engine}]\n{text}", tokens


def make_buscar_web(settings: Settings, search_fn: Callable[[str, Settings], tuple[str, str]] = web_search,
                    key_fn: Callable[[], tuple] | None = None) -> BaseTool:
    """web_search para bigtool (sin estado inyectado). `key_fn() -> (thread_id, turn_key)`; sin él, sin topes."""

    @tool("web_search", description=BUSCAR_WEB_DOC)
    def buscar_web(query: str) -> str:
        thread_id, key = key_fn() if key_fn else (None, None)
        return run_search(settings, search_fn, query, turn_budget(key), thread_id)[1]

    return buscar_web


def make_buscar_web_con_presupuesto(settings: Settings, search_fn=web_search) -> BaseTool:
    """web_search del agente principal: comparte con el investigador los topes del mensaje (ver run_search)."""

    @tool("web_search", description=BUSCAR_WEB_DOC)
    def buscar_web(query: str, runtime: ToolRuntime[Context]) -> str:
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        key = turn_key(thread_id, runtime.state.get("messages"))
        return run_search(settings, search_fn, query, turn_budget(key), thread_id)[1]

    return buscar_web


_INVESTIGADOR_PROMPT = (
    "You are a researcher. For the given task, run 2 to {max_searches} web searches with the web_search tool "
    "(vary the queries; never more than {max_searches}), cross-check the sources and return a clear, concise summary "
    "with the sources (URLs) at the end. If something could not be confirmed, say so. If web_search answers that the "
    "limit was reached, stop searching and write the summary with what you already found, saying it is partial. "
    "Reply in the task's language."
)


INVESTIGADOR_DOC = """Delegates in-depth research to a sub-agent that runs several web searches and
returns a summary with sources. Use it for questions that need cross-checking several
sources; for a single fact use web_search. Do not call it again for follow-up questions about research
already done in this conversation: answer from those results unless a needed fact is missing."""

SEARCH_LIMIT_MSG = "LIMIT REACHED: no more searches allowed. Write the final summary now with what you already found."
FOLLOW_UP_MSG = ("Not run: this conversation already has research on this. This is a short follow-up, so answer it "
                 "from the earlier research results below; use web_search only for one specific missing fact.\n\n"
                 "Earlier research results:\n{previous}")
_RAW_FINDINGS_CHARS = 8000
# palabras con las que el usuario pide investigar de nuevo (sin acentos)
_RESEARCH_AGAIN = re.compile(r"\b(investiga\w*|busca\w*|de nuevo|otra vez|nuevamente|actualiza\w*|research\w*|"
                             r"search\w*|look (it )?up|again)\b")
FOLLOW_UP_MAX_CHARS = 200


class _TokenCounter(BaseCallbackHandler):
    """Suma al presupuesto del mensaje los tokens de las llamadas del modelo del investigador. Va pegado al modelo
    (no a la config), así que no cuenta las búsquedas hospedadas: esas las suma run_search."""

    def __init__(self, budget: TurnBudget | None):
        self.budget = budget
        self.total = 0

    def on_llm_end(self, response, **kwargs):
        for gens in response.generations:
            for g in gens:
                usage = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                tokens = usage.get("total_tokens", 0) or 0
                self.total += tokens
                if self.budget is not None:
                    with self.budget.lock:
                        self.budget.tokens += tokens


def _was_cut(msg) -> bool:
    meta = getattr(msg, "response_metadata", None) or {}
    return bool(meta.get("incomplete_details")) or meta.get("status") == "incomplete"


def make_subinvestigador(model: BaseChatModel, buscar_web_tool: BaseTool, max_searches: int = 4):
    return create_agent(model, [buscar_web_tool], system_prompt=_INVESTIGADOR_PROMPT.format(max_searches=max_searches))


def investigar(model: BaseChatModel, settings: Settings, search_fn, task: str, write: Callable[[dict], None], *,
               turn_key: tuple | None = None) -> str:
    """Corre el subagente investigador; avisa cada búsqueda interna con `write` y devuelve su resumen.
    Topes: INVESTIGATOR_MAX_SEARCHES propias y los del mensaje, compartidos con web_search (run_search). Si se corta,
    devuelve lo hallado con un aviso, nunca una respuesta vacía."""
    from assistant.agent import turn_tokens

    max_searches, token_budget = settings.investigator_max_searches, settings.investigator_token_budget
    budget = turn_budget(turn_key)
    thread_id = turn_key[0] if turn_key else None
    counter = _TokenCounter(budget)
    found: list[str] = []
    stop: dict = {"reason": None, "started": 0}
    own_lock = threading.Lock()  # sin turn_key (tests, bigtool sin hilo) igual van de una en una

    @tool("web_search", description=BUSCAR_WEB_DOC)
    def buscar_limitado(query: str) -> str:
        with own_lock:
            if stop["started"] >= max_searches:
                stop["reason"] = stop["reason"] or "searches"
                return SEARCH_LIMIT_MSG
            ok, text, _ = run_search(settings, search_fn, query, budget, thread_id)
            if not ok:
                stop["reason"] = "searches" if text == WEB_LIMIT_MSG else "tokens"
                return SEARCH_LIMIT_MSG
            stop["started"] += 1
        found.append(f"[{query}]\n{text}")
        return text

    sub = make_subinvestigador(model.model_copy(update={"callbacks": [counter]}), buscar_limitado, max_searches)
    final, cut = "", False
    # tags=["nostream"]: sus tokens no deben llegar al stream del agente principal.
    # Se usa stream (no invoke) para avisar a la UI de cada búsqueda interna mientras trabaja.
    for update in sub.stream(
        {"messages": [{"role": "user", "content": f"Current date: {datetime.now().astimezone():%Y-%m-%d}.\n\n{task}"}]},
        config={"tags": ["nostream"], "recursion_limit": 4 * max_searches + 8},
        stream_mode="updates",
    ):
        for msg in (update.get("model") or {}).get("messages", []):
            for call in msg.tool_calls:
                write({"tipo": "progreso", "herramienta": call["name"], "args": call["args"]})
            if not msg.tool_calls:
                final, cut = msg.text or "", _was_cut(msg)
        if (token_budget and budget is not None and budget.tokens >= token_budget) or (
                settings.turn_token_cap and turn_tokens(thread_id) >= settings.turn_token_cap):
            stop["reason"] = "tokens"  # corte duro: sus propias llamadas ya agotaron el presupuesto o el tope
            break

    notes = []
    if stop["reason"] == "searches":
        notes.append("[Research stopped at the search limit for this message; it covers only what was found. "
                     "Tell the user it is partial; do not run more searches to complete it.]")
    elif stop["reason"] == "tokens":
        notes.append(f"[Research stopped at the token budget for this message ({token_budget}); it covers only what "
                     "was found. Tell the user it is partial; do not run more searches to complete it.]")
    if cut or not final.strip():
        notes.append("[The researcher's final summary was cut before it finished; below is what it found so far. "
                     "Tell the user the result is partial; do not run more searches to complete it.]")
        raw = "\n\n---\n\n".join(found)[:_RAW_FINDINGS_CHARS]
        final = "\n\n".join(p for p in (final.strip(), f"Raw findings so far:\n{raw}" if raw else "") if p)
        final = final or "No search results were obtained."
    return "\n".join(notes + [final])


def earlier_research(messages, tool_name: str = "deep_research") -> str | None:
    """Resultado de una investigación anterior del hilo si el mensaje actual es un seguimiento breve que no pide
    investigar de nuevo; None en otro caso. Evita relanzar la investigación (en la prueba larga, H13 gastó 240k)."""
    messages = messages or []
    idx = max((i for i, m in enumerate(messages) if getattr(m, "type", None) == "human"
               and (m.additional_kwargs or {}).get("lc_source") != memory.SUMMARY_SOURCE), default=None)
    if idx is None:
        return None
    text = memory._normalize(messages[idx].text if isinstance(messages[idx].content, str) else str(messages[idx].content))
    if len(text) > FOLLOW_UP_MAX_CHARS or _RESEARCH_AGAIN.search(text):
        return None
    previous = [m for m in messages[:idx] if getattr(m, "type", None) == "tool"
                and OLD_TOOL_NAMES.get(m.name, m.name) == tool_name  # hilos viejos: investigador_profundo
                and not str(m.content).startswith("Not run:")]
    return str(previous[-1].content)[:_RAW_FINDINGS_CHARS] if previous else None


def investigator_model(model: BaseChatModel, settings: Settings) -> BaseChatModel:
    """MAX_TOKENS no se aplica al investigador: con 2000, su razonamiento agotaba el tope y el resumen salía vacío."""
    if isinstance(model, ChatOpenAI):
        return model.model_copy(update={"max_tokens": settings.investigator_max_tokens or None})
    return model


def make_investigador(model: BaseChatModel, settings: Settings, search_fn=web_search) -> BaseTool:
    inv_model = investigator_model(model, settings)

    @tool("deep_research", description=INVESTIGADOR_DOC)
    def investigador_profundo(task: str, runtime: ToolRuntime[Context]) -> str:
        messages = runtime.state.get("messages")
        previous = earlier_research(messages)
        if previous is not None:
            return FOLLOW_UP_MSG.format(previous=previous)
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        return investigar(inv_model, settings, search_fn, task, runtime.stream_writer,
                          turn_key=turn_key(thread_id, messages))

    return investigador_profundo


def memory_verifier_for(settings: Settings, checker=None):
    """Verificador de recuerdos si MEMORY_VERIFY=1 (checker = modelo barato; se inyecta en tests)."""
    if not settings.memory_verify:
        return None
    if checker is None:
        from assistant.agent import make_checker_model

        checker = make_checker_model(settings)
    return memory.make_memory_verifier(checker)


def build_tools(model: BaseChatModel, settings: Settings, search_fn=web_search, checker=None) -> list[BaseTool]:
    verifier = memory_verifier_for(settings, checker)
    tools: list[BaseTool] = [
        make_buscar_web_con_presupuesto(settings, search_fn),
        calculadora,
        fecha_hora,
        make_guardar_recuerdo(verifier),
        make_buscar_recuerdos(settings.memory_min_score),
        make_actualizar_recuerdo(verifier),
        make_investigador(model, settings, search_fn),
    ]
    if settings.enable_hitl_demo:
        tools.append(enviar_email_simulado)
    return tools
