"""Programador en el mismo proceso: cada tick lanza los workflows cuya tarea en `scheduled_tasks` ya vencio.

Solo corre con SHIFU_SCHEDULER=1 (lo arranca el lifespan de main.py). Cada SHIFU_SCHEDULER_TICK_SECONDS
(30 por defecto) reclama las tareas vencidas una por una y lanza su workflow con el lanzador unico.
Despues de cada tick tambien corre el de correo (`email_trigger_loop`): workflows que arrancan al llegar un correo nuevo.

ponytail: con varios procesos de uvicorn no hay doble ejecucion, porque `claim_due_task` es atomico (find_one_and_update).
Pasar a un worker aparte cuando haya volumen.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from app.services.scheduled_task_service import (
    COLLECTION,
    advance_or_complete,
    claim_due_task,
    pause_task,
)
from app.services.workflow_launcher import start_workflow_run
from app.services.workflow_run_service import ConcurrentRunLimitExceededError
from app.workers.email_trigger_loop import tick as email_tick
from app.workers.notice_mailer import tick as mailer_tick
from app.workers.reminder_loop import tick as reminder_tick

logger = logging.getLogger(__name__)

DEFAULT_TICK_SECONDS = 30
_MAX_PER_TICK = 100  # tope de seguridad: un tick nunca se queda en un ciclo largo
_RETRY_AFTER_LIMIT = timedelta(seconds=60)


async def _load_workflow(db: Any, workflow_id: str) -> dict | None:
    try:
        return await db["workflows"].find_one({"_id": ObjectId(workflow_id)})
    except (InvalidId, TypeError):
        return None


async def _defer(db: Any, task: dict) -> None:
    """El plan no deja otra corrida ahora: se reintenta en un minuto en vez de perder esta ocurrencia."""
    await db[COLLECTION].update_one(
        {"_id": ObjectId(task["_id"])},
        {"$set": {"next_run_at": datetime.now(timezone.utc) + _RETRY_AFTER_LIMIT}, "$inc": {"run_count": -1}},
    )


async def _run_task(db: Any, task: dict) -> None:
    wf = await _load_workflow(db, str(task.get("workflow_id", "")))
    if not wf or wf.get("status") != "active" or not wf.get("steps"):
        # Borrado, pausado o vacio: la tarea se pausa para no reclamarla en cada tick.
        logger.warning("[scheduler] tarea %s: workflow no disponible, se pausa", task["_id"])
        await pause_task(task["_id"], db)
        return
    try:
        run_id = await start_workflow_run(
            db, wf, trigger="schedule", simulate=os.getenv("SHIFU_FUNCTIONS_SIMULATE", "") == "1"
        )
    except ConcurrentRunLimitExceededError:
        logger.info("[scheduler] tarea %s: limite de corridas del plan, se reintenta en 1 min", task["_id"])
        await _defer(db, task)
        return
    logger.info("[scheduler] tarea %s lanzo la corrida %s", task["_id"], run_id)
    await advance_or_complete(task, db)


async def tick(db: Any) -> int:
    """Lanza todas las tareas vencidas. Devuelve cuantas reclamo. Un error en una tarea no frena a las demas."""
    claimed = 0
    while claimed < _MAX_PER_TICK:
        task = await claim_due_task(db)
        if not task:
            break
        claimed += 1
        try:
            await _run_task(db, task)
        except Exception:
            logger.exception("[scheduler] fallo la tarea %s", task.get("_id"))
            # claim_due_task la dejo con next_run_at en el futuro lejano: sin avanzarla no volveria a correr nunca.
            try:
                await advance_or_complete(task, db)
            except Exception:
                logger.exception("[scheduler] no se pudo avanzar la tarea %s", task.get("_id"))
    return claimed


async def run_forever(db: Any, tick_seconds: float = DEFAULT_TICK_SECONDS) -> None:
    logger.info("[scheduler] activo, tick cada %ss", tick_seconds)
    while True:
        try:
            await tick(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[scheduler] fallo el tick; el ciclo sigue")
        try:
            await reminder_tick(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[scheduler] fallo el tick de recordatorios; el ciclo sigue")
        try:
            await mailer_tick(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[scheduler] fallo el tick de avisos por correo; el ciclo sigue")
        try:
            await email_tick(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[scheduler] fallo el tick de correo; el ciclo sigue")
        await asyncio.sleep(tick_seconds)


def tick_seconds_from_env() -> float:
    try:
        return max(1.0, float(os.getenv("SHIFU_SCHEDULER_TICK_SECONDS", DEFAULT_TICK_SECONDS)))
    except ValueError:
        return float(DEFAULT_TICK_SECONDS)


async def _main() -> None:
    """Proceso aparte: `python -m app.workers.scheduler_loop`. Asi reiniciar el servidor web no detiene los workflows
    programados, el vigilante de correo ni los recordatorios. El servidor debe correr SIN SHIFU_SCHEDULER=1 (con los dos
    no hay doble disparo, porque cada reclamo es atomico, pero sobra). Sin Redis, los avisos en vivo de este proceso no
    llegan a los navegadores conectados al servidor; quedan en la lista de avisos."""
    from app.core.mongo import mongo_manager
    await mongo_manager.connect()
    try:
        await run_forever(mongo_manager.db, tick_seconds_from_env())
    finally:
        await mongo_manager.disconnect()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
