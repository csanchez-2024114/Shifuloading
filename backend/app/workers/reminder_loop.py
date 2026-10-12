"""Recordatorios: un aviso por cada compromiso con fecha que vence hoy (o ya vencio) y sigue pendiente.

Lo llama el ciclo del programador (SHIFU_SCHEDULER=1). Lee `user_daily_diary` (due_date lo guarda memory_learner) y
marca `reminded_at` para avisar una sola vez.

ponytail: "hoy" es la fecha UTC, no la del usuario (el diario no guarda zona); un compromiso puede avisarse unas horas
antes o despues de la medianoche local. Guardar la zona en el diario si eso molesta.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

_MAX_PER_TICK = 50
_MAX_DAYS_LATE = 7


async def tick(db: Any, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    oldest = (now - timedelta(days=_MAX_DAYS_LATE)).strftime("%Y-%m-%d")  # lo vencido hace mucho ya no se avisa
    rows = await db["user_daily_diary"].find(
        {"due_date": {"$lte": today, "$gte": oldest}, "done_at": None, "reminded_at": None}).limit(_MAX_PER_TICK).to_list(_MAX_PER_TICK)
    sent = 0
    for r in rows:
        # Se marca primero y solo avisa quien gano la marca: con dos procesos no sale el aviso doble.
        won = await db["user_daily_diary"].update_one({"_id": r["_id"], "reminded_at": None},
                                                      {"$set": {"reminded_at": datetime.now(timezone.utc)}})
        if not won.modified_count or not r.get("pending") or not r.get("user_id"):
            continue
        what = ", ".join(map(str, r.get("activities") or [])) or str(r["pending"])
        late = r["due_date"] < today
        await create_notification(db, str(r["user_id"]), "commitment_due",
                                  "Compromiso vencido" if late else "Vence hoy",
                                  f"{what} ({'vencía el ' + r['due_date'] if late else 'vence hoy'}). Pendiente: {r['pending']}")
        sent += 1
    return sent
