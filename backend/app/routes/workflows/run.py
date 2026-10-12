"""Ejecutar un workflow ahora, en el mismo proceso (sin worker ni scheduler), y consultar la corrida.

POST /workflows/{id}/run?simulate=1  -> crea la corrida y la ejecuta en segundo plano; responde {run_id, status}.
GET  /workflows/runs/{run_id}        -> estado y resultado por paso (solo del dueno).
Con simulate=1 los pasos con function_id devuelven el ejemplo de su ficha y no tocan ninguna app externa.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_current_user, get_db
from app.services.workflow_launcher import _TASKS, start_workflow_run  # noqa: F401  (_TASKS: las pruebas esperan las corridas)
from app.services.workflow_run_service import ConcurrentRunLimitExceededError, get_run
from app.services.workflow_service import get_workflow_by_id

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/workflows/{workflow_id}/run")
async def run_workflow(
    workflow_id: str,
    simulate: bool = Query(False, description="1 = no llamar a las apps externas; usar los ejemplos de las fichas"),
    user: dict = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    user_id = str(user.get("id") or user.get("_id"))
    wf = await get_workflow_by_id(user_id, workflow_id, db)
    if not wf:  # ajeno o inexistente: misma respuesta para no revelar que existe
        raise HTTPException(status_code=404, detail="Workflow no encontrado.")
    if not wf.get("steps"):
        raise HTTPException(status_code=400, detail="El workflow no tiene pasos.")

    wf["user_email"] = wf.get("user_email") or user.get("email", "")
    try:
        run_id = await start_workflow_run(db, wf, trigger="manual", simulate=simulate)
    except ConcurrentRunLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return {"run_id": run_id, "status": "running"}


@router.get("/workflows/runs/{run_id}")
async def get_workflow_run(run_id: str, user: dict = Depends(get_current_user), db: Any = Depends(get_db)):
    user_id = str(user.get("id") or user.get("_id"))
    run = await get_run(run_id, db)
    if not run or run.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Corrida no encontrada.")

    def iso(v: Any) -> Any:
        return v.isoformat() if hasattr(v, "isoformat") else v

    return {
        "run_id": run["_id"],
        "workflow_id": run.get("workflow_id"),
        "status": run.get("status"),
        "simulate": bool(run.get("simulate")),
        "error": run.get("error"),
        "started_at": iso(run.get("started_at")),
        "finished_at": iso(run.get("finished_at")),
        "steps": [
            {
                "order": s.get("order"),
                "name": s.get("name"),
                "app": s.get("app"),
                "action": s.get("action"),
                "function_id": s.get("function_id"),
                "status": s.get("status", "pending"),
                "result": s.get("result"),
                "error": s.get("error"),
                "started_at": iso(s.get("started_at")),
                "finished_at": iso(s.get("finished_at")),
            }
            for s in sorted(run.get("steps", []), key=lambda x: x.get("order", 0))
        ],
    }
