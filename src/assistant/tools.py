"""Herramientas del asistente (en español). Todas síncronas."""
import ast
import logging
import math
import operator
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from assistant import memory
from assistant.agent import Context
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
            raise ValueError("exponente demasiado grande")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "math":
        if node.attr in _NAMES:
            return _NAMES[node.attr]
        raise ValueError(f"constante no permitida: math.{node.attr}")
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
    raise ValueError("expresión no permitida")


@tool
def calculadora(expresion: str) -> str:
    """Calculator: evaluates a math expression and returns the exact result.

    Supports + - * / // % ** and parentheses, plus math functions/constants (sqrt, sin, cos, tan,
    log, log10, exp, factorial, abs, round, min, max, pi, e...). Example: "sqrt(144) + 2**10 / 4".
    Always use it for arithmetic instead of computing from memory.
    """
    try:
        tree = ast.parse(expresion.strip(), mode="eval")
        result = _eval_node(tree)
    except ZeroDivisionError:
        return "Error: división entre cero."
    except SyntaxError:
        return f"Error: expresión inválida: {expresion!r}"
    except (ValueError, TypeError, OverflowError) as exc:
        return f"Error: {exc}"
    if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
        result = int(result)
    return str(result)


# --------------------------------------------------------------------------- fecha y hora

@tool
def fecha_hora(zona: str = "local") -> str:
    """Returns the current date and time (ISO 8601) and the day of the week.

    `zona` is optional: "local" (default) or an IANA time zone name,
    e.g. "America/Mexico_City", "Europe/Madrid", "UTC".
    """
    try:
        if not zona or zona.strip().lower() == "local":
            now = datetime.now().astimezone()
        elif zona.strip().upper() == "UTC":
            now = datetime.now(timezone.utc)
        else:
            now = datetime.now(ZoneInfo(zona.strip()))
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return (
            f"Error: zona horaria desconocida o no disponible: {zona!r}. "
            "Usa un nombre IANA como 'America/Mexico_City'."
        )
    return f"{now.isoformat(timespec='seconds')} ({now:%A})"


# --------------------------------------------------------------------------- memoria


GUARDAR_RECUERDO_DOC = """Saves a stable fact about the user to long-term memory (name, likes, preferences,
work context). Only save what the user explicitly said about themselves, never your own assumptions.

Args:
    texto: The fact as a complete, self-contained sentence in the user's language,
        e.g. "El usuario se llama Ana y prefiere respuestas cortas".
    evidencia: The user's exact words that state this fact, copied verbatim from their message.
"""


def make_guardar_recuerdo(verifier=None) -> BaseTool:
    """`verifier` (MEMORY_VERIFY): (candidato, textos_usuario) -> (respaldado, cita); None = sin verificar."""

    @tool(description=GUARDAR_RECUERDO_DOC)
    def guardar_recuerdo(texto: str, runtime: ToolRuntime[Context], evidencia: str = "") -> str:
        texts = memory.user_texts(runtime.state.get("messages"))
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        return memory.remember(runtime.store, runtime.context.user_id, texto, evidencia, texts,
                               thread_id=thread_id, verifier=verifier)

    return guardar_recuerdo


guardar_recuerdo = make_guardar_recuerdo()


BUSCAR_RECUERDOS_DOC = """Searches long-term memory for what is known about the user. Pass topic keywords in the
language the memories were saved in, or an empty string to get the most recent memories.
Each result starts with its id, which actualizar_recuerdo needs."""

ACTUALIZAR_RECUERDO_DOC = """Replaces the text of an EXISTING memory (get its id from buscar_recuerdos). Use it when the
user confirms that a saved fact changed, instead of saving a second, contradictory memory. Only use it with what
the user explicitly said; never with your own assumptions. It cannot delete memories.

Args:
    id: The memory id shown by buscar_recuerdos.
    texto: The new fact as a complete, self-contained sentence in the user's language.
    evidencia: The user's exact words that state the new value, copied verbatim from their message.
"""


def make_buscar_recuerdos(min_score: float = 0.0) -> BaseTool:
    """`min_score` (MEMORY_MIN_SCORE) solo filtra la búsqueda semántica (Atlas)."""

    @tool(description=BUSCAR_RECUERDOS_DOC)
    def buscar_recuerdos(consulta: str, runtime: ToolRuntime[Context]) -> str:
        return memory.recall(runtime.store, runtime.context.user_id, consulta, min_score)

    return buscar_recuerdos


buscar_recuerdos = make_buscar_recuerdos()


def make_actualizar_recuerdo(verifier=None) -> BaseTool:
    """Misma verificación que guardar_recuerdo. Solo toca recuerdos del user_id del contexto."""

    @tool(description=ACTUALIZAR_RECUERDO_DOC)
    def actualizar_recuerdo(id: str, texto: str, runtime: ToolRuntime[Context], evidencia: str = "") -> str:  # noqa: A002
        texts = memory.user_texts(runtime.state.get("messages"))
        thread_id = (runtime.config.get("configurable") or {}).get("thread_id")
        return memory.revise(runtime.store, runtime.context.user_id, id, texto, evidencia, texts,
                             thread_id=thread_id, verifier=verifier)

    return actualizar_recuerdo


# --------------------------------------------------------------------------- HITL demo


@tool
def enviar_email_simulado(destinatario: str, asunto: str, cuerpo: str) -> str:
    """Sends an email (SIMULATED: nothing is actually sent). Requires human approval
    before it runs.
    """
    return f"Email simulado enviado a {destinatario} con asunto {asunto!r} ({len(cuerpo)} caracteres)."


# --------------------------------------------------------------------------- búsqueda web


def _ddg_search(query: str) -> str:
    from ddgs import DDGS

    results = DDGS().text(query, max_results=5)
    if not results:
        return "Sin resultados."
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
        ).bind_tools([{"type": "web_search"}])
        text = llm.invoke(query).text
        if not text or not text.strip():
            raise ValueError("respuesta vacía del web_search hospedado")
        return text, "openai_web_search"
    except Exception as exc:  # noqa: BLE001 - cualquier fallo cae a DuckDuckGo
        logger.warning("web_search de OpenAI falló (%s: %s); usando DuckDuckGo", type(exc).__name__, exc)
    return _ddg_search(query), "duckduckgo"


def make_buscar_web(settings: Settings, search_fn: Callable[[str, Settings], tuple[str, str]] = web_search) -> BaseTool:
    @tool
    def buscar_web(consulta: str) -> str:
        """Searches the web for current information and returns a summary with sources. Use it for
        news, recent data or anything that may have changed.
        """
        text, engine = search_fn(consulta, settings)
        return f"[motor: {engine}]\n{text}"

    return buscar_web


_INVESTIGADOR_PROMPT = (
    "You are a researcher. For the given task, run 3 to 5 web searches with the buscar_web tool "
    "(vary the queries), cross-check the sources and return a clear, concise summary with the "
    "sources (URLs) at the end. If something could not be confirmed, say so. Reply in the task's language."
)


INVESTIGADOR_DOC = """Delegates in-depth research to a sub-agent that runs several web searches and
returns a summary with sources. Use it for questions that need cross-checking several
sources; for a single fact use buscar_web."""


def make_subinvestigador(model: BaseChatModel, buscar_web_tool: BaseTool):
    return create_agent(model, [buscar_web_tool], system_prompt=_INVESTIGADOR_PROMPT)


def investigar(sub, tarea: str, write: Callable[[dict], None]) -> str:
    """Corre el subagente investigador; avisa cada búsqueda interna con `write` y devuelve su resumen."""
    # tags=["nostream"]: sus tokens no deben llegar al stream del agente principal.
    # Se usa stream (no invoke) para avisar a la UI de cada búsqueda interna mientras trabaja.
    final = ""
    for update in sub.stream(
        {"messages": [{"role": "user", "content": f"Current date: {datetime.now().astimezone():%Y-%m-%d}.\n\n{tarea}"}]},
        config={"tags": ["nostream"], "recursion_limit": 25},
        stream_mode="updates",
    ):
        for msg in (update.get("model") or {}).get("messages", []):
            for call in msg.tool_calls:
                write({"tipo": "progreso", "herramienta": call["name"], "args": call["args"]})
            if not msg.tool_calls and msg.text:
                final = msg.text
    return final


def make_investigador(model: BaseChatModel, buscar_web_tool: BaseTool) -> BaseTool:
    sub = make_subinvestigador(model, buscar_web_tool)

    @tool(description=INVESTIGADOR_DOC)
    def investigador_profundo(tarea: str, runtime: ToolRuntime[Context]) -> str:
        return investigar(sub, tarea, runtime.stream_writer)

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
    buscar_web = make_buscar_web(settings, search_fn)
    verifier = memory_verifier_for(settings, checker)
    tools: list[BaseTool] = [
        buscar_web,
        calculadora,
        fecha_hora,
        make_guardar_recuerdo(verifier),
        make_buscar_recuerdos(settings.memory_min_score),
        make_actualizar_recuerdo(verifier),
        make_investigador(model, buscar_web),
    ]
    if settings.enable_hitl_demo:
        tools.append(enviar_email_simulado)
    return tools
