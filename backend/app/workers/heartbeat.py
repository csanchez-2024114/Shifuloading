"""
Shared worker heartbeat utility.

Each worker calls worker_heartbeat() at startup. The coroutine writes
  worker:heartbeat:{name}  → "1"  (TTL 120s)
to Redis every 60 seconds. The WorkerMonitor in main.py checks these keys
and restarts workers whose heartbeat has expired (dead process detection).

Fails open if Redis is unavailable — heartbeat is informational only and
must never block or crash the worker.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 60   # seconds between heartbeat writes
_HEARTBEAT_TTL      = 120  # Redis key TTL — 2× interval so one missed beat is OK


async def worker_heartbeat(name: str, redis_url: str, is_running) -> None:
    """
    Sends a heartbeat to Redis every 60s while the worker is running.

    Args:
        name        — worker name used as part of the Redis key
        redis_url   — Redis connection string
        is_running  — callable returning bool; stops heartbeat when False
    """
    import redis.asyncio as aioredis
    key = f"worker:heartbeat:{name}"
    r = None
    try:
        r = aioredis.from_url(redis_url, decode_responses=True)
        logger.debug("[heartbeat] %s started", name)
        while is_running():
            try:
                await r.set(key, "1", ex=_HEARTBEAT_TTL)
                logger.debug("[heartbeat] %s alive", name)
            except Exception as exc:
                logger.debug("[heartbeat] %s Redis write failed (fail-open): %s", name, exc)
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("[heartbeat] %s failed to start (fail-open): %s", name, exc)
    finally:
        if r:
            try:
                await r.aclose()
            except Exception:
                pass
        logger.debug("[heartbeat] %s stopped", name)
