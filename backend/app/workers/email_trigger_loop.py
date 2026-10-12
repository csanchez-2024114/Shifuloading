"""Disparador "llega un correo nuevo" en el mismo proceso: cada tick consulta Gmail para los workflows vencidos.

Un workflow con trigger_type "email" guarda en `email_trigger` la busqueda (`q`), la cuenta, la marca `since` y los
ids ya vistos (`seen_ids`). Cada SHIFU_EMAIL_POLL_SECONDS (120, minimo 5) se reclama de forma atomica, se corre
gmail.messages.search y cada correo nuevo lanza una corrida con el correo como `{{trigger}}`.

ponytail: es polling dentro del proceso, 50 workflows por tick. Pasar a Gmail push (watch + Pub/Sub) o a un worker
aparte cuando el volumen o la latencia lo pidan.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument

from app.functions.registry import RegistryError, get_function, load_all
from app.functions.runner import execute
from app.functions.spec import ErrorCode
from app.services.notification_service import create_notification
from app.services.workflow_launcher import start_workflow_run
from app.services.workflow_run_service import ConcurrentRunLimitExceededError

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 120
_MIN_POLL_SECONDS = 5
_MAX_PER_TICK = 50
_SEEN_KEEP = 100  # ids recordados por workflow: basta para cubrir el solape de `since`
_OVERLAP = timedelta(seconds=60)  # `since` retrocede 1 min: un correo que Gmail indexa tarde no se pierde
_DISABLE_CODES = (ErrorCode.auth_expired, ErrorCode.missing_connection)
_FUNCTION_ID = "gmail.messages.search"


def poll_seconds_from_env() -> int:
    try:
        return max(_MIN_POLL_SECONDS, int(os.getenv("SHIFU_EMAIL_POLL_SECONDS", DEFAULT_POLL_SECONDS)))
    except ValueError:
        return DEFAULT_POLL_SECONDS


def _utc(dt: datetime) -> datetime:
    """Mongo puede devolver la fecha sin zona: es UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _search_function():
    try:
        return get_function(_FUNCTION_ID)
    except RegistryError:
        load_all()  # el registro aun no se cargo en este proceso
        return get_function(_FUNCTION_ID)


async def _poll(db: Any, wf: dict, now: datetime) -> None:
    trig = wf.get("email_trigger") or {}
    since = _utc(trig["since"])
    simulate = os.getenv("SHIFU_FUNCTIONS_SIMULATE", "") == "1"
    query = f"{trig.get('q') or ''} in:inbox after:{int(since.timestamp())}".strip()
    result = await execute(
        _search_function(), {"q": query, "max_results": 10},
        db=db, user_id=str(wf.get("user_id", "")), account_id=trig.get("account_id"), simulate=simulate,
    )
    if not result.ok:
        code = result.error.code
        if code in _DISABLE_CODES:
            # Sin conexion util no tiene sentido seguir consultando: se apaga hasta que el usuario reconecte.
            logger.warning("[email_trigger] workflow %s: %s, se desactiva el disparador", wf["_id"], code.value)
            await db["workflows"].update_one(
                {"_id": wf["_id"]}, {"$set": {"email_trigger.disabled": True, "email_trigger.last_error": code.value}})
            await create_notification(
                db, str(wf.get("user_id", "")), "trigger_disabled", "Workflow detenido",
                f'"{wf.get("name") or "tu workflow"}" dejó de revisar tu correo porque la cuenta de Gmail ya no está '
                "conectada. Vuelve a conectarla y actívalo de nuevo.")
        else:
            logger.warning("[email_trigger] workflow %s: %s, se reintenta en el proximo poll", wf["_id"], code.value)
            await db["workflows"].update_one({"_id": wf["_id"]}, {"$set": {"email_trigger.last_error": code.value}})
        return

    seen = list(trig.get("seen_ids") or [])
    launched: list[str] = []
    limited = False
    # La busqueda devuelve lo mas nuevo primero: se lanza de lo mas viejo a lo mas nuevo.
    for msg in reversed((result.data or {}).get("messages") or []):
        if msg.get("id") in seen:
            continue
        try:
            await start_workflow_run(db, wf, trigger="email", simulate=simulate, payload=msg)
        except ConcurrentRunLimitExceededError:
            logger.info("[email_trigger] workflow %s: limite de corridas del plan, el resto se reintenta", wf["_id"])
            limited = True
            break
        launched.append(msg["id"])

    update: dict = {"$set": {"email_trigger.seen_ids": (seen + launched)[-_SEEN_KEEP:]}, "$unset": {"email_trigger.last_error": ""}}
    if not limited:
        update["$set"]["email_trigger.since"] = now - _OVERLAP
    await db["workflows"].update_one({"_id": wf["_id"]}, update)


async def tick(db: Any) -> int:
    """Consulta los workflows con disparador de correo vencido. Devuelve cuantos reclamo. Un error no frena a los demas."""
    polled = 0
    while polled < _MAX_PER_TICK:
        now = datetime.now(timezone.utc)
        wf = await db["workflows"].find_one_and_update(
            {"status": "active", "trigger_type": "email", "email_trigger.next_poll_at": {"$lte": now},
             "email_trigger.disabled": {"$ne": True}},
            {"$set": {"email_trigger.next_poll_at": now + timedelta(seconds=poll_seconds_from_env())}},
            return_document=ReturnDocument.AFTER,
        )
        if not wf:
            break
        polled += 1
        try:
            await _poll(db, wf, now)
        except Exception:
            logger.exception("[email_trigger] fallo el workflow %s", wf.get("_id"))
    return polled
