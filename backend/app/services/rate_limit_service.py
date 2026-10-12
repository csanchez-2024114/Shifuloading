"""
Rate Limit Service — per-user, per-tool, per-hour limits for BigTools calls.

Uses Redis INCR+EXPIRE for atomic counting (fail-open if Redis unavailable).
Configurable via env vars:
  BIGTOOL_RATE_LIMIT_PER_HOUR   — max calls per user per tool per hour (default: 100, 0 = disabled)

Key pattern: rl:tool:{user_id}:{tool_name}:{YYYYMMDDHH}
TTL: 3600 seconds (1 hour bucket, auto-expires)
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_LIMIT_PER_HOUR = int(os.getenv("BIGTOOL_RATE_LIMIT_PER_HOUR", "100"))
_KEY_PREFIX = "rl:tool"


async def check_tool_rate_limit(
    user_id: str,
    tool_name: str,
    redis_url: str | None = None,
) -> tuple[bool, int]:
    """
    Increments the call counter for (user, tool, hour).
    Returns (allowed: bool, current_count: int).

    Fails open (returns True) if Redis is unavailable or limit is disabled.
    """
    if _LIMIT_PER_HOUR <= 0:
        return True, 0

    hour_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    key = f"{_KEY_PREFIX}:{user_id}:{tool_name}:{hour_bucket}"

    if not redis_url:
        return True, 0

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url, decode_responses=True, socket_timeout=1)
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3600)
        results = await pipe.execute()
        count = int(results[0])
        await r.aclose()
        allowed = count <= _LIMIT_PER_HOUR
        if not allowed:
            logger.warning(
                "[rate_limit] EXCEEDED user=%s tool=%s count=%d limit=%d",
                user_id, tool_name, count, _LIMIT_PER_HOUR,
            )
        return allowed, count
    except Exception as exc:
        logger.debug("[rate_limit] Redis unavailable — fail open: %s", exc)
        return True, 0
