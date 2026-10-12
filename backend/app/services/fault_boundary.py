"""
fault_boundary — Agent OS fault isolation

Wraps async graph nodes so they NEVER raise to the LangGraph runtime.
On failure:
  1. ERROR logged with full traceback
  2. Fault written to node_fault_log (fire-and-forget, non-blocking)
  3. Returns empty dict {} — turn continues with partial state

Usage:
    @safe_node
    async def my_node(state, config): ...

    # Or wrap explicitly in graph.py:
    _builder.add_node("chat", safe_node(chat_node, node_name="chat"))
"""

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_COL = "node_fault_log"


async def _log_fault(node_name: str, exc: Exception, user_id: str) -> None:
    try:
        from app.database import get_async_database
        db = get_async_database()
        await db[_COL].insert_one({
            "node":       node_name,
            "user_id":    user_id,
            "error_type": type(exc).__name__,
            "error_msg":  str(exc)[:500],
            "traceback":  traceback.format_exc()[:2000],
            "timestamp":  datetime.now(timezone.utc),
        })
    except Exception as log_exc:
        logger.debug("[fault_boundary] fault log write failed: %s", log_exc)


def safe_node(
    fn: Optional[Callable] = None,
    *,
    node_name: Optional[str] = None,
    fallback: Optional[dict] = None,
):
    """
    Decorator/wrapper ensuring an async graph node never raises.

    Can be used as a bare decorator (@safe_node), with arguments
    (@safe_node(node_name="chat")), or as a plain function call
    (safe_node(fn, node_name="chat")).
    """
    def decorator(inner_fn: Callable) -> Callable:
        name = node_name or inner_fn.__name__

        @wraps(inner_fn)
        async def _wrapped(state: Any, *args, **kwargs) -> dict:
            try:
                return await inner_fn(state, *args, **kwargs)
            except Exception as exc:
                user_id = (state.get("user_id") or "") if hasattr(state, "get") else ""
                logger.error(
                    "[safe_node] %s raised %s: %s",
                    name, type(exc).__name__, exc,
                    exc_info=True,
                )
                asyncio.create_task(_log_fault(name, exc, user_id))
                return fallback if fallback is not None else {}

        return _wrapped

    if fn is not None:
        return decorator(fn)
    return decorator
