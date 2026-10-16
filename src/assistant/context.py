"""Contexto de cada conversación: medidor (tokens que enviaría la siguiente llamada), poda de resultados viejos de
herramientas (COMPACT_PRUNE_TOOLS) y registro de compactaciones. Todo es por hilo: vive en su checkpoint."""
import json
import logging
import operator
from functools import lru_cache
from typing import Annotated

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from typing_extensions import NotRequired

from assistant.memory import SUMMARY_SOURCE

logger = logging.getLogger(__name__)


class ContextState(AgentState):
    """Campos extra del estado del hilo (MedidorContexto y la compactación)."""
    context_stats: NotRequired[dict]                              # totales consumidos, último turno, overhead medido
    compaction_log: NotRequired[Annotated[list, operator.add]]   # un registro por compactación


# --------------------------------------------------------------------------- conteo


MESSAGE_OVERHEAD = 4  # tokens de formato por mensaje (rol y separadores)


@lru_cache(maxsize=1)
def _encoding():
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")  # la de los modelos actuales de OpenAI
    except Exception:  # noqa: BLE001 - sin tiktoken: estimación por caracteres
        return None


def message_tokens(messages) -> int:
    """Tokens de lo que se reenvía de cada mensaje: su texto y sus llamadas a herramientas (nombre y argumentos).
    No usa el contenido crudo: con la Responses API trae bloques con ids y anotaciones que no son texto (prueba real:
    count_tokens_approximately daba 2,499 a una respuesta de 1,209 tokens reales)."""
    enc = _encoding()
    if enc is None:
        return count_tokens_approximately(messages)
    total = 0
    for m in messages:
        total += MESSAGE_OVERHEAD + len(enc.encode(_text(m)))
        for call in getattr(m, "tool_calls", None) or []:
            total += MESSAGE_OVERHEAD + len(enc.encode(call.get("name", "") + json.dumps(call.get("args", {}),
                                                                                         ensure_ascii=False)))
    return total


TOOL_OVERHEAD = 2  # tokens de formato por herramienta


def prompt_tokens(system_text: str, tools=()) -> int:
    """Contexto base de una conversación: prompt del sistema + herramientas. De cada herramienta cuenta nombre,
    descripción y propiedades de los parámetros: el JSON completo del esquema sobrestimaba (prueba real: 2,740
    estimados frente a ~2,435 reales; así, 2,431)."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    functions = [convert_to_openai_tool(t)["function"] for t in tools]
    enc = _encoding()
    if enc is None:
        return count_tokens_approximately([system_text]) + len(json.dumps(functions, ensure_ascii=False)) // 4
    return len(enc.encode(system_text)) + sum(
        TOOL_OVERHEAD + len(enc.encode(f["name"] + f.get("description", "")
                                       + json.dumps((f.get("parameters") or {}).get("properties", {}), ensure_ascii=False)))
        for f in functions)


# --------------------------------------------------------------------------- capa 1: poda


# Excepciones de la poda: la memoria global (lo que dijo el usuario y sus ids para update_memory) y, por ser del turno
# en curso, la evidencia que ANSWER_VERIFY contrasta (solo usa herramientas del turno actual).
PRUNE_KEEP_TOOLS = ("save_memory", "search_memories", "update_memory",
                    "guardar_recuerdo", "buscar_recuerdos", "actualizar_recuerdo")  # nombres antiguos incluidos
PRUNE_MIN_TOKENS = 60  # un resultado más corto que esto pesa casi lo mismo que el aviso: no se poda
PRUNED_MSG = "[tool result pruned: {name}, {tokens} tokens. Ask again or re-run the tool if needed.]"
_PRUNED_PREFIX = "[tool result pruned:"


def turn_start(messages) -> int:
    """Índice del último mensaje del usuario (el resumen no cuenta como usuario); -1 si no hay."""
    return max((i for i, m in enumerate(messages) if m.type == "human"
                and (m.additional_kwargs or {}).get("lc_source") != SUMMARY_SOURCE), default=-1)


def _text(msg) -> str:
    try:
        return msg.text or ""
    except Exception:  # noqa: BLE001
        return str(msg.content)


def prune_tool_results(messages, age: int) -> list:
    """Copia de `messages` con el contenido de los resultados de herramientas de más de `age` mensajes de antigüedad
    reemplazado por PRUNED_MSG. Conserva la llamada (nombre y argumentos, en el AIMessage) y la respuesta del asistente
    que interpretó el resultado. No toca el turno en curso ni las herramientas de PRUNE_KEEP_TOOLS. No modifica el
    historial guardado: es solo la vista que recibe el modelo."""
    if age <= 0:
        return list(messages)
    start, last = turn_start(messages), len(messages) - 1
    out = []
    for i, m in enumerate(messages):
        if (isinstance(m, ToolMessage) and i < start and last - i > age and m.name not in PRUNE_KEEP_TOOLS
                and not _text(m).startswith(_PRUNED_PREFIX)):
            tokens = message_tokens([m])
            if tokens >= PRUNE_MIN_TOKENS:
                m = m.model_copy(update={"content": PRUNED_MSG.format(name=m.name or "tool", tokens=tokens)})
        out.append(m)
    return out


class PodaHerramientas(AgentMiddleware):
    """COMPACT_PRUNE_TOOLS: antes de cada llamada al modelo poda los resultados viejos de herramientas (ver
    prune_tool_results). El checkpoint y la interfaz siguen teniendo el resultado completo."""

    def __init__(self, age: int):
        super().__init__()
        self.age = age

    def wrap_model_call(self, request, handler):
        return handler(request.override(messages=prune_tool_results(request.messages, self.age)))


# --------------------------------------------------------------------------- medidor


def visible_output(usage: dict) -> int:
    """Salida que vuelve a entrar en la siguiente llamada: el razonamiento no se reenvía."""
    reasoning = (usage.get("output_token_details") or {}).get("reasoning", 0) or 0
    return max(0, (usage.get("output_tokens", 0) or 0) - reasoning)


def _last_compaction(messages) -> dict:
    summary = next((m for m in messages if m.type == "human"
                    and (m.additional_kwargs or {}).get("lc_source") == SUMMARY_SOURCE), None)
    return (summary.additional_kwargs or {}).get("compaction") or {} if summary is not None else {}


def context_in_use(messages, base: int, prune_age: int = 0, overhead: int | None = None) -> tuple[int, bool]:
    """(tokens que enviaría la siguiente llamada, estimado). Con una respuesta del modelo posterior a la última
    compactación: su uso real (entrada + salida visible) más lo que se añadió después. Si no hay (hilo nuevo, recién
    compactado o modelo sin usage_metadata): prompt y herramientas (`overhead` medido o `base`) + la vista del modelo
    estimada, y se marca como estimado."""
    view = prune_tool_results(messages, prune_age) if prune_age else list(messages)
    stale = set(_last_compaction(view).get("kept_ids") or ())  # su uso real es de antes de compactar
    for i in range(len(view) - 1, -1, -1):
        m = view[i]
        usage = getattr(m, "usage_metadata", None) if isinstance(m, AIMessage) else None
        if usage and usage.get("input_tokens") and m.id not in stale:
            after = message_tokens(view[i + 1:]) if i + 1 < len(view) else 0
            return usage["input_tokens"] + visible_output(usage) + after, False
    return (overhead or base) + (message_tokens(view) if view else 0), True


def measured_overhead(messages, prune_age: int = 0) -> int | None:
    """Lo que pesan prompt del sistema + herramientas según la última llamada real: su entrada menos la vista
    estimada. Mejora la estimación tras compactar (calibrada con el uso real de este hilo)."""
    if not messages or not isinstance(messages[-1], AIMessage):
        return None
    usage = messages[-1].usage_metadata or {}
    if not usage.get("input_tokens"):
        return None
    view = prune_tool_results(messages[:-1], prune_age) if prune_age else messages[:-1]
    return max(0, usage["input_tokens"] - message_tokens(view))


class MedidorContexto(AgentMiddleware):
    """Medidor de contexto por hilo. Tras cada respuesta del modelo emite el contexto en uso (evento "context") y
    guarda el overhead medido; al terminar el turno suma su gasto (todas las llamadas: agente, resumen, verificadores,
    investigador, búsquedas) al total de la conversación. Va primero en la pila: sus hooks after_* corren al final."""

    state_schema = ContextState

    def __init__(self, base: int, prune_age: int = 0):
        super().__init__()
        self.base = base
        self.prune_age = prune_age

    def after_model(self, state, runtime):
        messages = state.get("messages") or []
        overhead = measured_overhead(messages, self.prune_age)
        if overhead is None:
            return None
        tokens, estimated = context_in_use(messages, self.base, self.prune_age, overhead)
        runtime.stream_writer({"tipo": "contexto", "tokens": tokens, "estimated": estimated})
        return {"context_stats": {**(state.get("context_stats") or {}), "overhead": overhead}}

    def after_agent(self, state, runtime):
        from assistant.agent import _turn_counter

        counter = _turn_counter()
        if counter is None:
            return None
        return {"context_stats": add_turn(state.get("context_stats") or {}, counter.total + counter.carry,
                                          counter.input + counter.carry_input, counter.output + counter.carry_output)}


def add_turn(stats: dict, total: int, inp: int, out: int) -> dict:
    return {**stats, "total": stats.get("total", 0) + total, "total_input": stats.get("total_input", 0) + inp,
            "total_output": stats.get("total_output", 0) + out, "last_turn": total, "turns": stats.get("turns", 0) + 1}


def context_report(values: dict, settings, base: int, can_compact: bool) -> dict:
    """Respuesta de GET /threads/{id}/context, a partir del estado guardado del hilo (sin llamar al modelo)."""
    messages = values.get("messages") or []
    stats = values.get("context_stats") or {}
    prune_age = settings.compact_prune_age if settings.compact_prune_tools else 0
    tokens, estimated = context_in_use(messages, base, prune_age, stats.get("overhead"))
    if stats.get("total") is None:  # hilos sin medidor (anteriores o bigtool): suma del uso de sus respuestas
        usage = [m.usage_metadata for m in messages if isinstance(m, AIMessage) and m.usage_metadata]
        stats = {"total": sum(u.get("total_tokens", 0) or 0 for u in usage),
                 "total_input": sum(u.get("input_tokens", 0) or 0 for u in usage),
                 "total_output": sum(u.get("output_tokens", 0) or 0 for u in usage), "last_turn": None}
    window = settings.context_window()
    log = values.get("compaction_log") or []
    return {
        "tokens": tokens, "estimated": estimated, "window": window, "percent": round(100 * tokens / window, 1),
        "warn_pct": settings.compact_warn_pct, "trigger_pct": settings.compact_trigger_pct,
        "trigger_tokens": settings.compact_trigger(), "auto_compact": settings.memory_summarize,
        "total_consumed": stats.get("total", 0), "total_input": stats.get("total_input", 0),
        "total_output": stats.get("total_output", 0), "last_turn": stats.get("last_turn"),
        "compactions": len(log), "last_compaction": log[-1] if log else None, "can_compact": can_compact,
    }
