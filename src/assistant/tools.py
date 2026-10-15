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
    """Evalúa una expresión matemática y devuelve el resultado exacto.

    Soporta + - * / // % ** y paréntesis, y funciones/constantes de math (sqrt, sin, cos, tan,
    log, log10, exp, factorial, abs, round, min, max, pi, e...). Ejemplo: "sqrt(144) + 2**10 / 4".
    Úsala siempre para cuentas en lugar de calcular de memoria.
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

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


@tool
def fecha_hora(zona: str = "local") -> str:
    """Devuelve la fecha y hora actuales (ISO 8601) y el día de la semana.

    `zona` es opcional: "local" (por defecto) o un nombre de zona horaria IANA,
    por ejemplo "America/Mexico_City", "Europe/Madrid", "UTC".
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
    return f"{now.isoformat(timespec='seconds')} ({_DIAS[now.weekday()]})"


# --------------------------------------------------------------------------- memoria


@tool
def guardar_recuerdo(texto: str, runtime: ToolRuntime[Context]) -> str:
    """Guarda en la memoria a largo plazo un dato estable del usuario (nombre, gustos,
    preferencias, contexto de trabajo). Escribe el dato como una frase completa y autosuficiente,
    por ejemplo "El usuario se llama Ana y prefiere respuestas cortas".
    """
    memory.save_memory(runtime.store, runtime.context.user_id, texto)
    return "Recuerdo guardado."


@tool
def buscar_recuerdos(consulta: str, runtime: ToolRuntime[Context]) -> str:
    """Busca en la memoria a largo plazo lo que se sabe del usuario. Pasa una consulta con
    palabras clave del tema, o una cadena vacía para obtener los recuerdos más recientes.
    """
    found = memory.search_memories(runtime.store, runtime.context.user_id, consulta)
    if not found:
        return "Sin recuerdos"
    return "\n".join(f"- {t}" for t in found)


# --------------------------------------------------------------------------- HITL demo


@tool
def enviar_email_simulado(destinatario: str, asunto: str, cuerpo: str) -> str:
    """Envía un correo electrónico (SIMULADO: no se envía nada real). Requiere aprobación
    humana antes de ejecutarse.
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
        """Busca información actual en la web y devuelve un resumen con fuentes. Úsala para
        noticias, datos recientes o cualquier cosa que pueda haber cambiado.
        """
        text, engine = search_fn(consulta, settings)
        return f"[motor: {engine}]\n{text}"

    return buscar_web


_INVESTIGADOR_PROMPT = (
    "Eres un investigador. Para la tarea recibida, haz entre 3 y 5 búsquedas web con la herramienta "
    "buscar_web (varía las consultas), contrasta las fuentes y devuelve un resumen claro y conciso "
    "con las fuentes (URLs) al final. Si algo no se pudo confirmar, dilo. Responde en el idioma de la tarea."
)


def make_investigador(model: BaseChatModel, buscar_web_tool: BaseTool) -> BaseTool:
    sub = create_agent(model, [buscar_web_tool], system_prompt=_INVESTIGADOR_PROMPT)

    @tool
    def investigador_profundo(tarea: str) -> str:
        """Delega una investigación a fondo en un subagente que hace varias búsquedas web y
        devuelve un resumen con fuentes. Úsalo para preguntas que requieren contrastar varias
        fuentes; para datos puntuales usa buscar_web.
        """
        # tags=["nostream"]: sus tokens no deben llegar al stream del agente principal.
        result = sub.invoke(
            {"messages": [{"role": "user", "content": f"Fecha actual: {datetime.now().astimezone():%Y-%m-%d}.\n\n{tarea}"}]},
            config={"tags": ["nostream"], "recursion_limit": 25},
        )
        return result["messages"][-1].text

    return investigador_profundo


def build_tools(model: BaseChatModel, settings: Settings, search_fn=web_search) -> list[BaseTool]:
    buscar_web = make_buscar_web(settings, search_fn)
    tools: list[BaseTool] = [
        buscar_web,
        calculadora,
        fecha_hora,
        guardar_recuerdo,
        buscar_recuerdos,
        make_investigador(model, buscar_web),
    ]
    if settings.enable_hitl_demo:
        tools.append(enviar_email_simulado)
    return tools
