"""Lanzador unico de corridas: lo usan el boton "ejecutar ahora", el programador y el webhook.

Un solo lugar para el limite de corridas simultaneas del plan, el run y la ejecucion en segundo plano,
asi los tres disparadores se comportan igual y no se desvian con el tiempo.
"""
import asyncio
import logging
from typing import Any, Optional

from app.services.workflow_run_service import (
    ConcurrentRunLimitExceededError,  # noqa: F401  (se re-exporta: quien llama lo captura desde aqui)
    claim_run_by_id,
    create_run,
    update_run_status,
)
from app.workers.workflow_executor import WorkflowExecutor

logger = logging.getLogger(__name__)

# asyncio solo guarda referencias debiles a las tareas: sin esto una corrida puede recolectarse a medias.
_TASKS: set[asyncio.Task] = set()


async def _execute(run: dict, db: Any) -> None:
    try:
        await WorkflowExecutor(run, db).execute()
    except Exception:
        # El ejecutor ya marca los pasos; esto solo evita dejar la corrida en "running" para siempre.
        logger.exception("[workflow_launcher] la corrida %s fallo fuera de un paso", run.get("_id"))
        await update_run_status(run["_id"], "failed", db, extra={"error": "Error interno del ejecutor"})


async def start_workflow_run(
    db: Any,
    workflow: dict,
    *,
    trigger: str,
    simulate: bool = False,
    payload: Optional[dict] = None,
) -> str:
    """Crea la corrida y la ejecuta en segundo plano; devuelve su id sin esperar a que termine.

    Lanza ConcurrentRunLimitExceededError si el plan del usuario no permite otra corrida a la vez.
    `workflow` es el documento de Mongo (con `_id`, `steps`, `user_id`).
    """
    workflow_id = str(workflow.get("_id") or workflow.get("id"))
    run_id = await create_run(
        workflow_id=workflow_id,
        workflow_name=workflow.get("name", ""),
        user_id=str(workflow.get("user_id", "")),
        user_email=workflow.get("user_email", ""),
        steps=workflow.get("steps") or [],
        db=db,
        simulate=simulate,
        trigger=trigger,
        trigger_payload=payload,
    )
    run = await claim_run_by_id(run_id, db)
    if run is None:  # un worker lo tomo antes: ya se esta ejecutando
        return run_id
    task = asyncio.create_task(_execute(run, db))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return run_id
