import json
import logging
from typing import Any

import redis.asyncio as aioredis

from config import Config
from app.workers.connection_manager import manager

logger = logging.getLogger(__name__)


async def publish_user_event(user_id: str, event: dict[str, Any]) -> None:
    """Publica un evento para un usuario.

    Usa Redis (pub/sub) si `Config.REDIS_URL` está configurada, de lo contrario
    envía el evento vía WebSocket a través del `connection_manager.manager`.
    """
    try:
        channel = f"wf:{user_id}"
        if Config.REDIS_URL:
            r = aioredis.from_url(Config.REDIS_URL, decode_responses=True)
            try:
                await r.publish(channel, json.dumps(event, ensure_ascii=False))
            finally:
                await r.aclose()
        else:
            await manager.broadcast(user_id, event)
    except Exception as exc:
        logger.warning(f"publish_user_event error user_id={user_id}: {exc}")
