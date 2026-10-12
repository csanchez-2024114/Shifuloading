"""
error_handler_node — catches any exception that escaped a wrapped node.

Receives state["agent_error"] = {"node": str, "exc": str, "traceback": str},
logs the full context, and returns a friendly user-facing message so the WS
client never sees a raw exception string.
"""
import logging

from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

_FRIENDLY_MSG = (
    "Ups, algo salió mal de mi lado. 🔧 "
    "Ya quedó registrado y lo revisaré pronto. "
    "¿Puedes intentarlo de nuevo?"
)


async def error_handler_node(state) -> dict:
    err = state.get("agent_error") or {}
    logger.error(
        "[error_handler] node=%s | %s\n%s",
        err.get("node", "unknown"),
        err.get("exc", "unknown error"),
        err.get("traceback", ""),
    )
    return {"messages": [AIMessage(content=_FRIENDLY_MSG)]}
