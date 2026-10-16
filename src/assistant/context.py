"""Contexto de cada conversación: medidor (tokens que enviaría la siguiente llamada) y registro de compactaciones.
Todo es por hilo: vive en su checkpoint."""
import logging
import operator
from typing import Annotated

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage
from langchain_core.messages.utils import count_tokens_approximately
from typing_extensions import NotRequired

from assistant.memory import SUMMARY_SOURCE

logger = logging.getLogger(__name__)


class ContextState(AgentState):
    """Campos extra del estado del hilo (MedidorContexto y la compactación)."""
    context_stats: NotRequired[dict]                              # totales consumidos, último turno, overhead medido
    compaction_log: NotRequired[Annotated[list, operator.add]]   # un registro por compactación


# --------------------------------------------------------------------------- medidor


def visible_output(usage: dict) -> int:
    """Salida que vuelve a entrar en la siguiente llamada: el razonamiento no se reenvía."""
    reasoning = (usage.get("output_token_details") or {}).get("reasoning", 0) or 0
    return max(0, (usage.get("output_tokens", 0) or 0) - reasoning)


def _last_compaction(messages) -> dict:
    summary = next((m for m in messages if m.type == "human"
                    and (m.additional_kwargs or {}).get("lc_source") == SUMMARY_SOURCE), None)
    return (summary.additional_kwargs or {}).get("compaction") or {} if summary is not None else {}


def context_in_use(messages, base: int, overhead: int | None = None) -> tuple[int, bool]:
    """(tokens que enviaría la siguiente llamada, estimado). Con una respuesta del modelo posterior a la última
    compactación: su uso real (entrada + salida visible) más lo que se añadió después. Si no hay (hilo nuevo, recién
    compactado o modelo sin usage_metadata): prompt y herramientas (`overhead` medido o `base`) + la vista del modelo
    estimada, y se marca como estimado."""
    view = list(messages)
    stale = set(_last_compaction(view).get("kept_ids") or ())  # su uso real es de antes de compactar
    for i in range(len(view) - 1, -1, -1):
        m = view[i]
        usage = getattr(m, "usage_metadata", None) if isinstance(m, AIMessage) else None
        if usage and usage.get("input_tokens") and m.id not in stale:
            after = count_tokens_approximately(view[i + 1:]) if i + 1 < len(view) else 0
            return usage["input_tokens"] + visible_output(usage) + after, False
    return (overhead or base) + (count_tokens_approximately(view) if view else 0), True


def measured_overhead(messages) -> int | None:
    """Lo que pesan prompt del sistema + herramientas según la última llamada real: su entrada menos la vista
    estimada. Mejora la estimación tras compactar (calibrada con el uso real de este hilo)."""
    if not messages or not isinstance(messages[-1], AIMessage):
        return None
    usage = messages[-1].usage_metadata or {}
    if not usage.get("input_tokens"):
        return None
    view = messages[:-1]
    return max(0, usage["input_tokens"] - count_tokens_approximately(view))


class MedidorContexto(AgentMiddleware):
    """Medidor de contexto por hilo. Tras cada respuesta del modelo emite el contexto en uso (evento "context") y
    guarda el overhead medido; al terminar el turno suma su gasto (todas las llamadas: agente, resumen, verificadores,
    investigador, búsquedas) al total de la conversación. Va primero en la pila: sus hooks after_* corren al final."""

    state_schema = ContextState

    def __init__(self, base: int):
        super().__init__()
        self.base = base

    def after_model(self, state, runtime):
        messages = state.get("messages") or []
        overhead = measured_overhead(messages)
        if overhead is None:
            return None
        tokens, estimated = context_in_use(messages, self.base, overhead)
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
    tokens, estimated = context_in_use(messages, base, stats.get("overhead"))
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
