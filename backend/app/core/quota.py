"""
Quota check — sliding window RPM per user, plan-aware.
Fails open: if Redis is unavailable the request goes through.
"""
import json
import time
from datetime import datetime, timezone
from typing import Optional

from app.billing.plans import get_plan_rules

_WINDOW_SECS = 60
_DAY_SECS = 25 * 3600  # colchón sobre 24h para no cortar el contador justo a medianoche


def _rpm_limit(plan: str) -> int:
    return get_plan_rules(plan).get("rpm_limit", 20)


async def check_message_quota(redis_client, user_id: str, plan: str = "free") -> bool:
    # ponytail: sliding window via Redis INCR per minute bucket; fails open if Redis down
    if redis_client is None:
        return True
    limit = _rpm_limit(plan)
    if limit == -1:
        return True  # Enterprise — sin límite
    key = f"quota:rpm:{user_id}:{int(time.time()) // _WINDOW_SECS}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, _WINDOW_SECS * 2)
        return count <= limit
    except Exception:
        return True


def _daily_token_key(user_id: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"tokens:daily:{user_id}:{day}"


def _daily_token_warned_key(user_id: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"tokens:warned:{user_id}:{day}"


async def track_daily_tokens(redis_client, user_id: str, tokens: int) -> int:
    """Suma tokens al contador diario del usuario. Solo informa — nunca bloquea el chat."""
    if redis_client is None or tokens <= 0:
        return 0
    try:
        key = _daily_token_key(user_id)
        total = await redis_client.incrby(key, tokens)
        if total == tokens:
            await redis_client.expire(key, _DAY_SECS)
        return int(total)
    except Exception:
        return 0


async def get_daily_tokens_used(redis_client, user_id: str) -> int:
    """Reads today's token count without incrementing it. Fails open to 0 if Redis is unavailable."""
    if redis_client is None:
        return 0
    try:
        value = await redis_client.get(_daily_token_key(user_id))
        return int(value) if value else 0
    except Exception:
        return 0


async def maybe_get_token_warning(
    redis_client, user_id: str, plan: str, daily_total: int, db=None
) -> Optional[str]:
    """Devuelve un aviso de upgrade una sola vez por día al cruzar el 80% del cupo diario.
    Nunca bloquea — es un CTA, no un límite duro. None si no aplica o ya se avisó hoy.
    Si se pasa `db`, también persiste el aviso en `user_notifications` (best-effort) para que
    quede en el historial REST, no solo en el socket en vivo."""
    if redis_client is None:
        return None
    limit = get_plan_rules(plan).get("daily_token_limit", -1)
    if limit == -1 or daily_total < limit * 0.8:
        return None
    warned_key = _daily_token_warned_key(user_id)
    try:
        if await redis_client.get(warned_key):
            return None
        await redis_client.set(warned_key, "1", ex=_DAY_SECS)
    except Exception:
        return None
    message = (
        "Estás cerca de tu cupo diario de mensajes de chat para tu plan. "
        "Mejora tu plan si quieres más margen — nunca bloqueamos tu chat por esto, solo te avisamos."
    )
    # Broadcast on the same "wf:{user_id}" Redis channel that workflow_ws.py (WS /api/v1/ws/runs)
    # and proactive_notifier.py already use. This is the only socket the production frontend
    # can consume — the caller's own socket (e.g. debug_ws.py's /ws/chat-debug) is ephemeral and
    # not reachable outside the debug console. Fire-and-forget: never let a broadcast failure
    # break the CTA return value.
    try:
        await redis_client.publish(
            f"wf:{user_id}",
            json.dumps({"type": "usage_warning", "message": message}),
        )
    except Exception:
        pass

    if db is not None:
        try:
            from app.services.notification_service import create_notification
            await create_notification(
                db, user_id, "usage_warning", "Cerca de tu cupo diario", message,
            )
        except Exception:
            pass

    return message
