"""
BigTools for managing scheduled workflow tasks (list / pause / resume / delete).

Scheduling (creating a new schedule) is handled by Shifu V3's workflow tools
(`programar_workflow`) since it needs conversation context to find the draft.
These BigTools are for *management* of existing schedules — usable from V2 too.
"""
import logging
from typing import Optional

from langchain_core.tools import StructuredTool
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.services.bigtools_loader import BigTool

logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class _ListSchedulesInput(BaseModel):
    pass


class _TaskIdInput(BaseModel):
    task_id: str = Field(..., description="Scheduled task ID to manage.")


# ── Provider ──────────────────────────────────────────────────────────────────

class SchedulerManagementProvider:
    def __init__(self, user_email: str, db: Optional[AsyncIOMotorDatabase] = None):
        self.user_email = user_email
        self.db = db

    async def _get_user_id(self) -> str:
        if not self.db:
            return ""
        user = await self.db["users"].find_one(
            {"$or": [{"correo_usuario": self.user_email}, {"email": self.user_email}]},
            {"_id": 1},
        )
        return str(user["_id"]) if user else ""

    def get_tool_list(self) -> StructuredTool:
        provider = self

        async def listar_programaciones() -> str:
            from app.services.scheduled_task_service import list_user_tasks
            import json

            user_id = await provider._get_user_id()
            if not user_id:
                return "Could not identify user."
            tasks = await list_user_tasks(user_id, provider.db)
            if not tasks:
                return "No scheduled tasks found."
            lines = ["Your scheduled workflows:\n"]
            for t in tasks:
                sc = t.get("schedule_config", {})
                stype = t.get("schedule_type", "interval")
                if stype == "once":
                    freq = f"once at {t.get('next_run_at') or sc.get('run_at', '?')}"
                else:
                    secs = sc.get("every_seconds", 3600)
                    freq = (
                        f"every {secs}s"
                        if secs < 3600
                        else f"every {secs // 3600}h"
                        if secs < 86400
                        else "daily"
                        if secs == 86400
                        else f"every {secs // 86400}d"
                    )
                lines.append(
                    f"• [{t['status']}] {t['name']} — {freq} "
                    f"(runs: {t.get('run_count', 0)}) ID: {t['id']}"
                )
            return "\n".join(lines)

        return StructuredTool.from_function(
            coroutine=listar_programaciones,
            name="listar_programaciones",
            description=(
                "Lists the user's active scheduled CRON jobs and timed workflow executions — "
                "recurring schedules with a specific time/frequency (e.g. 'every day at 8am'). "
                "NOT for listing saved processes or automation blueprints — use 'listar_procesos' for that."
            ),
            args_schema=_ListSchedulesInput,
        )

    def get_tool_pause(self) -> StructuredTool:
        provider = self

        async def pausar_programacion(task_id: str) -> str:
            from app.services.scheduled_task_service import pause_task
            ok = await pause_task(task_id, provider.db)
            return "Schedule paused." if ok else "Scheduled task not found."

        return StructuredTool.from_function(
            coroutine=pausar_programacion,
            name="pausar_programacion",
            description="Pauses a scheduled workflow execution so it stops running temporarily.",
            args_schema=_TaskIdInput,
        )

    def get_tool_resume(self) -> StructuredTool:
        provider = self

        async def reanudar_programacion(task_id: str) -> str:
            from app.services.scheduled_task_service import resume_task
            ok = await resume_task(task_id, provider.db)
            return "Schedule resumed." if ok else "Scheduled task not found."

        return StructuredTool.from_function(
            coroutine=reanudar_programacion,
            name="reanudar_programacion",
            description="Resumes a paused scheduled workflow.",
            args_schema=_TaskIdInput,
        )

    def get_tool_delete(self) -> StructuredTool:
        provider = self

        async def eliminar_programacion(task_id: str) -> str:
            from app.services.scheduled_task_service import delete_task
            ok = await delete_task(task_id, provider.db)
            return "Schedule deleted." if ok else "Scheduled task not found."

        return StructuredTool.from_function(
            coroutine=eliminar_programacion,
            name="eliminar_programacion_bt",
            description="Permanently deletes a scheduled workflow execution.",
            args_schema=_TaskIdInput,
        )


# ── Registry loader ───────────────────────────────────────────────────────────

def get_scheduler_bigtools(
    user_email: str, db: Optional[AsyncIOMotorDatabase] = None
) -> list:
    try:
        provider = SchedulerManagementProvider(user_email, db)
        return [
            BigTool(
                name="listar_programaciones",
                description="Lists active CRON schedules and timed workflow executions. NOT for listing saved processes — use 'listar_procesos' for that.",
                tool=provider.get_tool_list(),
                args_schema=_ListSchedulesInput,
            ),
            BigTool(
                name="pausar_programacion",
                description="Pauses a scheduled workflow execution.",
                tool=provider.get_tool_pause(),
                args_schema=_TaskIdInput,
            ),
            BigTool(
                name="reanudar_programacion",
                description="Resumes a paused scheduled workflow.",
                tool=provider.get_tool_resume(),
                args_schema=_TaskIdInput,
            ),
            BigTool(
                name="eliminar_programacion_bt",
                description="Permanently deletes a scheduled workflow execution.",
                tool=provider.get_tool_delete(),
                args_schema=_TaskIdInput,
            ),
        ]
    except Exception as exc:
        logger.exception(f"[Scheduler BigTools] Error building tools for {user_email}: {exc}")
        return []
