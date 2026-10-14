"""Avisos por correo: lo que el usuario deberia saber aunque no abra la app (workflow fallido, disparador detenido,
compromiso que vence), enviado con el SMTP de la plataforma (app/utils/mail.py, el mismo de "recuperar contrasena").

Lo llama el ciclo del programador y solo actua con SHIFU_NOTICE_EMAILS=1: sin esa variable no sale ningun correo (en
local los usuarios de evaluacion tienen direcciones inventadas). Junta los avisos pendientes de cada usuario en UN correo.

ponytail: SMTP sincrono en un hilo y tope diario por usuario contado en Mongo. Pasar a un proveedor con cola y webhooks
de rebote cuando haya volumen.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.core.constants import Collections
from app.utils.mail import send_smtp_email, validate_smtp_config

logger = logging.getLogger(__name__)

DEFAULT_TYPES = ("run_failed", "trigger_disabled", "commitment_due", "crm_recordatorio", "crm_resumen")  # los dos últimos: automatizaciones del CRM
_MAX_AGE = timedelta(hours=24)   # un aviso viejo ya no se manda (p. ej. al encender la variable por primera vez)
_MAX_PER_TICK = 200
DEFAULT_DAILY_CAP = 5            # correos por usuario en 24 h: un workflow que falla cada minuto no inunda la bandeja


def _types() -> list[str]:
    raw = os.getenv("SHIFU_NOTICE_EMAIL_TYPES", "")
    return [t.strip() for t in raw.split(",") if t.strip()] or list(DEFAULT_TYPES)


def _daily_cap() -> int:
    try:
        return max(1, int(os.getenv("SHIFU_NOTICE_EMAIL_DAILY_CAP", DEFAULT_DAILY_CAP)))
    except ValueError:
        return DEFAULT_DAILY_CAP


def _body(name: str, rows: list[dict]) -> str:
    lines = "\n".join(f"- {r.get('title')}: {r.get('message')}" for r in rows)
    return (f"Hola{', ' + name if name else ''}:\n\n{lines}\n\n"
            "Puedes ver el detalle en la app o escribirle a Shifu para resolverlo.\n\n"
            "Para dejar de recibir estos correos, desactiva los avisos por correo en tus preferencias.")


async def tick(db: Any, now: datetime | None = None) -> int:
    """Manda los avisos pendientes. Devuelve cuantos correos salieron."""
    if os.getenv("SHIFU_NOTICE_EMAILS", "") != "1":
        return 0
    try:
        validate_smtp_config()
    except ValueError:
        return 0  # sin SMTP configurado no se marca nada: saldran cuando se configure (si aun son recientes)
    now = now or datetime.now(timezone.utc)
    col = db[Collections.USER_NOTIFICATIONS]
    pending = await col.find({"type": {"$in": _types()}, "read": False, "emailed_at": None,
                              "created_at": {"$gte": now - _MAX_AGE}}).sort("created_at", 1).to_list(_MAX_PER_TICK)
    by_user: dict[str, list[dict]] = {}
    for row in pending:
        by_user.setdefault(str(row.get("user_id") or ""), []).append(row)

    sent = 0
    for user_id, rows in by_user.items():
        # Se marcan primero y solo manda quien gano la marca: con dos procesos no sale el correo doble.
        mine = [r for r in rows if (await col.update_one({"_id": r["_id"], "emailed_at": None},
                                                         {"$set": {"emailed_at": now}})).modified_count]
        if not mine:
            continue
        try:
            user = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)})
        except (InvalidId, TypeError):
            user = None
        if not user or not user.get("email") or user.get("email_notices") is False:
            continue  # sin correo o el usuario los apago: quedan en su lista de la app
        recent = await db["notice_emails"].count_documents({"user_id": user_id, "sent_at": {"$gte": now - _MAX_AGE}})
        if recent >= _daily_cap():
            logger.info("[notice_mailer] usuario %s: tope diario, %s aviso(s) quedan solo en la app", user_id, len(mine))
            continue
        subject = mine[0].get("title") if len(mine) == 1 else f"Tienes {len(mine)} avisos de Shifu"
        ok = await asyncio.to_thread(send_smtp_email, user["email"], f"Shifu: {subject}", _body(str(user.get("name") or ""), mine))
        if ok:
            await db["notice_emails"].insert_one({"user_id": user_id, "sent_at": now, "count": len(mine)})
            sent += 1
        else:
            # No se reintenta (un SMTP caido reintentaria en cada tick); queda registrado y el aviso sigue en la app.
            await col.update_many({"_id": {"$in": [r["_id"] for r in mine]}}, {"$set": {"email_error": True}})
    return sent
