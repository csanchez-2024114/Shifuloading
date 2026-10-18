"""Herramientas del asistente (en español). Todas síncronas."""
import ast
import logging
import math
import operator
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

from assistant.core import memory
from assistant.core import citations
from assistant.core.agent import Context
from assistant.core import untrusted
from assistant.core.config import Settings, llm_kwargs

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


# Topes de tamaño (S4 de la auditoría): solo afectan entradas patológicas. Un entero de más de ~14 000 bits ya no se
# podía mostrar (Python limita str(int) a 4300 dígitos), y ((10**10000)**10000)**10000 o factorial(10**6) colgaban el
# hilo del servidor. Van como defaults de función, no como constantes del módulo: la huella no cambia.
def _small_int(value, max_bits: int = 14_000):
    """`value` si no es un entero gigante; si lo es, ValueError antes de seguir calculando con él."""
    if isinstance(value, int) and value.bit_length() > max_bits:
        raise ValueError("result too large")
    return value


def _check_pow(left, right, max_bits: int = 14_000) -> None:
    """Estima el tamaño de left ** right (enteros) antes de calcularlo."""
    if isinstance(left, int) and isinstance(right, int) and right > 0 and abs(left) > 1:
        if right * math.log2(abs(left)) > max_bits:
            raise ValueError("result too large")


def _check_call(fn, args, max_factorial: int = 1000) -> None:
    if fn is math.factorial and args and isinstance(args[0], int) and args[0] > max_factorial:
        raise ValueError("factorial argument too large")


def _eval_node(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_POW:
                raise ValueError("exponent too large")
            _check_pow(left, right)
        return _small_int(_BIN_OPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _small_int(_UNARY_OPS[type(node.op)](_eval_node(node.operand)))
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
            args = [_eval_node(a) for a in node.args]
            _check_call(fn, args)
            return _small_int(fn(*args))
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


GUARDAR_RECUERDO_STRICT_DOC = """Saves a precise fact about the user to long-term memory, which is shared by all of the
user's conversations. Use it ONLY when the user explicitly asks you to remember something, states a durable personal
fact that is clearly useful in other conversations (where they live, their job, their pets or family, a stable
preference or a lasting technical constraint), or wants a specific dated event remembered. Never save conversation
content: explanations, tasks, calculations, tool or search results, topics discussed or details of the current
request. Only save what the user explicitly said about themselves, never your own assumptions.

Args:
    text: The fact as a short, self-contained sentence in the user's language, in neutral form with no subject:
        never start with "The user" or its equivalent in the user's language (e.g. "Lives in Madrid",
        "Works as a data engineer", "Birthday is on March 3").
    evidence: The user's exact words that state this fact, copied verbatim from their message.
"""

GUARDAR_RECUERDO_DOC = """Saves a lasting fact about the user to long-term memory: name, likes, preferences, job and
role, and durable technical constraints (language or library versions they must use, libraries they cannot install,
their operating system or environment). Only save what the user explicitly said about themselves, never your own
assumptions. Stable facts mentioned in passing while asking for something else (where they live, their diet, what
they like, their job) are still facts about the user: save them. Never save details of the current task: file names,
row counts, data values, error messages, amounts, dates or budget of a one-off plan, or what they are working on
today. Those are not facts about the user.

Args:
    text: The fact as a short, self-contained sentence in the user's language, in neutral form with no subject:
        never start with "The user" or its equivalent in the user's language (e.g. "Lives in Madrid",
        "Works as a data engineer", "Favorite food is pozole").
    evidence: The user's exact words that state this fact, copied verbatim from their message.
"""


def save_memory_doc(policy: str = "strict") -> str:
    """Descripción de save_memory según MEMORY_SAVE_POLICY ("broad" = la política anterior)."""
    return GUARDAR_RECUERDO_DOC if policy == "broad" else GUARDAR_RECUERDO_STRICT_DOC


def make_guardar_recuerdo(verifier=None, policy: str = "strict", max_per_turn: int = 0, dedup: bool = False,
                          dedup_score: float = 0.85) -> BaseTool:
    """`verifier` (MEMORY_VERIFY): (candidato, textos_usuario) -> (respaldado, cita); None = sin verificar.
    `max_per_turn` (MEMORY_MAX_PER_TURN): tope de recuerdos por mensaje; 0 = sin tope.
    `dedup` (MEMORY_DEDUP): rechaza datos equivalentes a uno existente."""

    @tool("save_memory", description=save_memory_doc(policy))
    def guardar_recuerdo(text: str, runtime: ToolRuntime[Context], evidence: str = "") -> str:
        messages = runtime.state.get("messages")
        texts = memory.user_texts(messages)
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        return memory.remember(runtime.store, runtime.context.user_id, text, evidence, texts,
                               thread_id=thread_id, verifier=verifier,
                               saved_this_turn=memory.turn_saves(messages, runtime.tool_call_id),
                               max_per_turn=max_per_turn, dedup=dedup, dedup_score=dedup_score)

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
            **llm_kwargs(settings),
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
    from assistant.core.agent import turn_tokens

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
    # la primera línea sigue siendo el motor (la lee _engine_from_output); el contenido de la web va envuelto
    return True, f"[engine: {engine}]\n{untrusted.wrap_if(settings, text)}", tokens


ONE_SEARCH_MSG = ("Not run: one search per step. Answer with what you have or ask the user; if another search is "
                  "really needed, run it in your next step.")


def extra_search(messages, tool_call_id: str | None = None, query: str | None = None) -> bool:
    """True si esta llamada no es la primera web_search de la respuesta del modelo que la pidió. Como máximo una
    búsqueda por llamada al modelo: en la prueba real, un seguimiento breve lanzó 3 en paralelo (35k tokens).
    Se identifica por el id de la llamada o, en bigtool (sin id inyectado), por la consulta."""
    from assistant.core.profile import tool_aliases

    names = tool_aliases(("web_search",))  # con sus nombres antiguos (hilos viejos)
    for m in reversed(messages or []):
        searches = [c for c in getattr(m, "tool_calls", None) or [] if c.get("name") in names]
        if not searches:
            continue
        if tool_call_id is not None and any(c.get("id") == tool_call_id for c in searches):
            return searches[0].get("id") != tool_call_id
        if query is not None:  # la respuesta más reciente del modelo con búsquedas
            return (searches[0].get("args") or {}).get("query") != query
    return False


def make_buscar_web(settings: Settings, search_fn: Callable[[str, Settings], tuple[str, str]] = web_search,
                    key_fn: Callable[[], tuple] | None = None) -> BaseTool:
    """web_search para bigtool (sin estado inyectado). `key_fn() -> (thread_id, turn_key, mensajes del hilo)`; sin
    él, sin topes."""

    @tool("web_search", description=BUSCAR_WEB_DOC)
    def buscar_web(query: str) -> str:
        thread_id, key, messages = key_fn() if key_fn else (None, None, [])
        if extra_search(messages, query=query):
            return ONE_SEARCH_MSG
        return run_search(settings, search_fn, query, turn_budget(key), thread_id)[1]

    return buscar_web


def make_buscar_web_con_presupuesto(settings: Settings, search_fn=web_search) -> BaseTool:
    """web_search del agente principal: comparte con el investigador los topes del mensaje (ver run_search)."""

    @tool("web_search", description=BUSCAR_WEB_DOC)
    def buscar_web(query: str, runtime: ToolRuntime[Context]) -> str:
        if extra_search(runtime.state.get("messages"), runtime.tool_call_id):
            return ONE_SEARCH_MSG
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        key = turn_key(thread_id, runtime.state.get("messages"))
        return run_search(settings, search_fn, query, turn_budget(key), thread_id)[1]

    return buscar_web


_INVESTIGADOR_PROMPT = (
    "You are a researcher. For the given task, run 2 to {max_searches} web searches with the web_search tool "
    "(vary the queries; never more than {max_searches}), cross-check the sources and return a clear, concise summary "
    "with the sources (URLs) at the end. If something could not be confirmed, say so. If web_search answers that the "
    "limit was reached, stop searching and write the summary with what you already found, saying it is partial. "
    "Only cite URLs that appear in your web_search results; never write a URL from memory. If no search returned "
    "results, do not include a sources section and say that the web could not be consulted. "
    "Reply in the task's language."
)


INVESTIGADOR_DOC = """Delegates in-depth research to a sub-agent that runs several web searches and
returns a summary with sources. Use it for questions that need cross-checking several
sources; for a single fact use web_search. Do not call it again for follow-up questions about research
already done in this conversation: answer from those results unless a needed fact is missing. Call it
directly; the app asks the user to confirm before it runs."""

SEARCH_LIMIT_MSG = "LIMIT REACHED: no more searches allowed. Write the final summary now with what you already found."
FOLLOW_UP_MSG = ("Not run: this conversation already has research on this. This is a short follow-up, so answer it "
                 "from the earlier research results below; use web_search only for one specific missing fact.\n\n"
                 "Earlier research results:\n{previous}")
_RAW_FINDINGS_CHARS = 8000


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


NO_WEB_NOTE = ("[No web search could be run for this research: the summary below comes from the researcher's own "
               "knowledge, not from the web, and has no sources. Tell the user the web could not be consulted; do not "
               "present any link as a consulted source.]")


def make_subinvestigador(model: BaseChatModel, buscar_web_tool: BaseTool, max_searches: int = 4):
    return create_agent(model, [buscar_web_tool], system_prompt=_INVESTIGADOR_PROMPT.format(max_searches=max_searches))


def investigar(model: BaseChatModel, settings: Settings, search_fn, task: str, write: Callable[[dict], None], *,
               turn_key: tuple | None = None) -> str:
    """Corre el subagente investigador; avisa cada búsqueda interna con `write` y devuelve su resumen.
    Topes: INVESTIGATOR_MAX_SEARCHES propias y los del mensaje, compartidos con web_search (run_search). Si se corta,
    devuelve lo hallado con un aviso, nunca una respuesta vacía."""
    from assistant.core.agent import turn_tokens

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
                stop["reason"] = {WEB_LIMIT_MSG: "searches", TURN_CAP_TOOL_MSG: "turn_cap"}.get(text, "tokens")
                return SEARCH_LIMIT_MSG
            stop["started"] += 1
        found.append(f"[{query}]\n{text}")
        return text

    pending: dict[str, dict] = {}  # llamadas a web_search pedidas por el modelo, por id: se avisan solo si corren

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
            pending.update({call["id"]: call for call in msg.tool_calls})
            if not msg.tool_calls:
                final, cut = msg.text or "", _was_cut(msg)
        # el chip cuenta solo las búsquedas que se ejecutaron: las rechazadas por un tope no son búsquedas
        for msg in (update.get("tools") or {}).get("messages", []):
            call = pending.pop(getattr(msg, "tool_call_id", None), None)
            if call and msg.text != SEARCH_LIMIT_MSG and getattr(msg, "status", None) != "error":
                write({"tipo": "progreso", "herramienta": call["name"], "args": call["args"]})
        # corte duro: sus propias llamadas ya agotaron el tope del mensaje o el presupuesto del investigador
        if settings.turn_token_cap and turn_tokens(thread_id) >= settings.turn_token_cap:
            stop["reason"] = "turn_cap"
            break
        if token_budget and budget is not None and budget.tokens >= token_budget:
            stop["reason"] = "tokens"
            break

    notes = []
    if stop["reason"] == "searches":
        notes.append("[Research stopped at the search limit for this message; it covers only what was found. "
                     "Tell the user it is partial; do not run more searches to complete it.]")
    elif stop["reason"] == "tokens":
        notes.append(f"[Research stopped at the research token budget for this message ({token_budget:,} tokens); it "
                     "covers only what was found. Tell the user it is partial; do not run more searches to complete it.]")
    elif stop["reason"] == "turn_cap":
        notes.append(f"[Research stopped at the overall token cap for this message ({settings.turn_token_cap:,} tokens); "
                     "it covers only what was found. Tell the user it is partial; do not run more searches to complete "
                     "it.]")
    if cut or not final.strip():
        notes.append("[The researcher's final summary was cut before it finished; below is what it found so far. "
                     "Tell the user the result is partial; do not run more searches to complete it.]")
        raw = "\n\n---\n\n".join(found)[:_RAW_FINDINGS_CHARS]
        final = "\n\n".join(p for p in (final.strip(), f"Raw findings so far:\n{raw}" if raw else "") if p)
        final = final or "No search results were obtained."
    # solo valen las URLs de las búsquedas que se ejecutaron; sin búsquedas, no hay sección de fuentes
    final, _ = citations.keep_supported(final, "\n".join(found))
    if not found:
        final = citations.drop_sources_section(final)
        notes.append(NO_WEB_NOTE)
    # las notas son nuestras; el resumen se escribió a partir de páginas de terceros
    return "\n".join(notes + [untrusted.wrap_if(settings, final)])


def earlier_research(messages, tool_name: str = "deep_research") -> str | None:
    """Resultado de una investigación anterior del hilo si el mensaje actual es un seguimiento breve que no pide
    investigar de nuevo; None en otro caso. Evita relanzar la investigación (en la prueba larga, H13 gastó 240k)."""
    from assistant.core.profile import active_profile

    profile = active_profile()
    legacy = profile.legacy_tool_names  # hilos viejos: nombres antiguos de las herramientas
    rules = profile.intents  # qué es un seguimiento breve y qué pide investigar de nuevo
    messages = messages or []
    idx = max((i for i, m in enumerate(messages) if getattr(m, "type", None) == "human"
               and (m.additional_kwargs or {}).get("lc_source") != memory.SUMMARY_SOURCE), default=None)
    if idx is None:
        return None
    text = memory._normalize(messages[idx].text if isinstance(messages[idx].content, str) else str(messages[idx].content))
    if len(text) > rules.follow_up_max_chars or rules.research_again.search(text):
        return None
    previous = [m for m in messages[:idx] if getattr(m, "type", None) == "tool"
                and legacy.get(m.name, m.name) == tool_name
                and not str(m.content).startswith("Not run:")]
    return str(previous[-1].content)[:_RAW_FINDINGS_CHARS] if previous else None


RESEARCH_DECLINED_MSG = ("Not run: the user declined the in-depth research. Answer with what you already know, without "
                         "searching, and say in one line that it was not researched in depth.")


def research_needs_confirmation(messages) -> bool:
    """deep_research tarda 1-2 minutos y gasta mucho más: se confirma con el usuario salvo que lo haya pedido
    explícitamente en su último mensaje o que sea un seguimiento que reutiliza una investigación anterior (no corre).
    Prueba real: el primer mensaje de un plan de viaje lanzó la investigación sin pedirla (95 s, 35k tokens)."""
    messages = messages or []
    human = next((m for m in reversed(messages) if getattr(m, "type", None) == "human"
                  and (m.additional_kwargs or {}).get("lc_source") != memory.SUMMARY_SOURCE), None)
    text = memory._normalize(human.text if human is not None and isinstance(human.content, str) else str(
        getattr(human, "content", "")))
    from assistant.core.profile import active_profile

    explicit = active_profile().intents.explicit_research  # el usuario pide investigar en ESTE mensaje
    return not explicit.search(text) and earlier_research(messages) is None


def _research_when(request) -> bool:
    return research_needs_confirmation(request.state.get("messages"))


def research_approval() -> dict:
    """Aprobación de deep_research para HumanInTheLoopMiddleware (ToolPolicy.approval): tarjeta con aprobar/rechazar,
    salvo que el usuario haya pedido investigar en ese mensaje. El texto de la tarjeta lo pone build_agent desde el
    catálogo del perfil (ToolPolicy.description_key = "tools.deep_research_confirm")."""
    return {"allowed_decisions": ["approve", "reject"], "when": _research_when}


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
        from assistant.core.agent import make_checker_model

        checker = make_checker_model(settings)
    return memory.make_memory_verifier(checker)


SYNTAX_MAX_CHARS = 200_000
SYNTAX_OK_MSG = "OK: no syntax errors. The code was only parsed, not run, so runtime errors are still possible."


@tool("check_python_syntax")
def check_python_syntax(code: str) -> str:
    """Check whether Python code is syntactically valid WITHOUT running it (it is only parsed). Use it before giving
    the user Python code longer than 15 lines, and fix any error it reports. Returns OK, or the error with its line
    and column."""
    # Solo ast.parse: no compila a bytecode, no ejecuta, no importa, sin archivos ni red.
    if len(code) > SYNTAX_MAX_CHARS:
        return f"Not checked: the code is longer than {SYNTAX_MAX_CHARS} characters."
    try:
        ast.parse(code, filename="<code>", mode="exec")
    except SyntaxError as exc:
        line = (exc.text or "").rstrip("\n")
        pointer = f"\n{line}\n{' ' * max((exc.offset or 1) - 1, 0)}^" if line else ""
        if exc.lineno is None:  # p. ej. bytes nulos: el parser no da posición
            return f"SyntaxError: {exc.msg}"
        return f"SyntaxError at line {exc.lineno}, column {exc.offset}: {exc.msg}{pointer}"
    except (ValueError, RecursionError, MemoryError) as exc:  # bytes nulos, anidamiento extremo
        return f"Not checked: the parser failed ({type(exc).__name__}: {exc})."
    return SYNTAX_OK_MSG


def base_tools(model: BaseChatModel, settings: Settings, search_fn=web_search, checker=None) -> list[BaseTool]:
    """Herramientas base del núcleo, en su orden. El perfil decide cuáles usa (build_tools)."""
    verifier = memory_verifier_for(settings, checker)
    return [
        make_buscar_web_con_presupuesto(settings, search_fn),
        calculadora,
        fecha_hora,
        check_python_syntax,
        make_guardar_recuerdo(verifier, settings.memory_save_policy, settings.memory_max_per_turn,
                              settings.memory_dedup, settings.memory_dedup_score),
        make_buscar_recuerdos(settings.memory_min_score),
        make_actualizar_recuerdo(verifier),
        make_investigador(model, settings, search_fn),
    ]


def build_tools(model: BaseChatModel, settings: Settings, search_fn=web_search, checker=None,
                profile=None) -> list[BaseTool]:
    """Herramientas del agente normal según el perfil (el activo si no se pasa)."""
    from assistant.core.profile import active_profile

    return (profile or active_profile()).build_tools(model, settings, base_tools(model, settings, search_fn, checker))
