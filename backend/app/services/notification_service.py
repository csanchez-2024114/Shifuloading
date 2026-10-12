"""
Persistence for `user_notifications` — the REST-backed history/read-state layer that
complements the live WS events already broadcast on Redis channel `wf:{user_id}`
(see app/utils/events.py::publish_user_event, app/core/quota.py, app/workers/workflow_executor.py).

This module does not invent new notification types: it persists the same events the system
already fires over the socket, so `GET /api/v1/me/notifications` has a real history to serve
and "mark as read" has something durable to mutate. Best-effort — a failed insert never breaks
the caller's real flow (chat response, workflow run, etc).
"""
import logging
from datetime import datetime, timezone

from app.core.constants import Collections

logger = logging.getLogger(__name__)


async def create_notification(db, user_id: str, type: str, title: str, message: str) -> None:
    """Inserts one row into `user_notifications`. Silently no-ops if db/user_id are missing."""
    if db is None or not user_id:
        return
    try:
        await db[Collections.USER_NOTIFICATIONS].insert_one({
            "user_id": user_id,
            "type": type,
            "title": title,
            "message": message,
            "read": False,
            "created_at": datetime.now(timezone.utc),
        })
        # Aviso en vivo (v0.8.1): mismo canal `wf:{user_id}` que los eventos de corridas; quien tenga la app abierta lo ve
        # sin recargar. Import tardio: events importa el gestor de conexiones.
        from app.utils.events import publish_user_event
        await publish_user_event(user_id, {"type": "notification", "notification_type": type, "title": title, "message": message})
    except Exception as exc:
        logger.warning(f"create_notification failed user_id={user_id} type={type}: {exc}")


async def take_untold(db, user_id: str, types: list[str], limit: int = 3) -> list[dict]:
    """Avisos sin leer que el agente todavia no menciono, del mas nuevo al mas viejo, y los marca `told_at` para decirlos
    una sola vez (siguen sin leer en la lista del usuario). Lo usa memory_retriever al abrir una conversacion."""
    if db is None or not user_id or not types:
        return []
    try:
        col = db[Collections.USER_NOTIFICATIONS]
        rows = await col.find({"user_id": user_id, "read": False, "told_at": None, "type": {"$in": types}}
                              ).sort("created_at", -1).limit(limit).to_list(length=limit)
        if rows:
            await col.update_many({"_id": {"$in": [r["_id"] for r in rows]}}, {"$set": {"told_at": datetime.now(timezone.utc)}})
        # Solo texto: el resultado viaja en el estado del grafo y un ObjectId o una fecha rompen el checkpoint (msgpack).
        return [{"type": r.get("type"), "title": r.get("title"), "message": r.get("message"),
                 "date": f"{r['created_at']:%Y-%m-%d}" if hasattr(r.get("created_at"), "strftime") else ""} for r in rows]
    except Exception as exc:
        logger.warning(f"take_untold failed user_id={user_id}: {exc}")
        return []
