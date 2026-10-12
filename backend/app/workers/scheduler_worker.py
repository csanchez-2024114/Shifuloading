"""
SchedulerWorker — polls scheduled_tasks and executes due workflow runs.

Supports schedule_type:
  "once"     – runs once, then marks the task completed.
  "interval" – runs every every_seconds; optional max_runs.

The worker loads the full workflow (with all steps) from the workflows
collection and hands it to WorkflowExecutor — exactly like a manual run.
"""
import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import Config
from app.services.scheduled_task_service import advance_or_complete, claim_due_task
from app.services.workflow_run_service import create_run
from app.workers.heartbeat import worker_heartbeat

logger = logging.getLogger(__name__)


class SchedulerWorker:
    def __init__(self, poll_interval: int = 30):
        self.poll_interval = poll_interval
        self._running = False

    async def start(self, db: AsyncIOMotorDatabase):
        self._running = True
        logger.info(f"[Scheduler] Started (poll every {self.poll_interval}s)")
        if Config.REDIS_URL:
            asyncio.create_task(
                worker_heartbeat("scheduler_worker", Config.REDIS_URL, lambda: self._running)
            )
        while self._running:
            try:
                await self._tick(db)
            except Exception as exc:
                logger.exception(f"[Scheduler] Unhandled error in tick: {exc}")
            await asyncio.sleep(self.poll_interval)
        logger.info("[Scheduler] Stopped.")

    def stop(self):
        self._running = False

    async def _tick(self, db: AsyncIOMotorDatabase):
        while True:
            task = await claim_due_task(db)
            if not task:
                break
            logger.info(
                f"[Scheduler] Claimed task={task['_id']} name='{task['name']}' "
                f"type={task.get('schedule_type')} workflow={task.get('workflow_id')}"
            )
            asyncio.create_task(self._execute_task(task, db))

    async def _execute_task(self, task: dict, db: AsyncIOMotorDatabase):
        task_id = task["_id"]
        workflow_id = task.get("workflow_id", "")
        try:
            from app.services.workflow_service import get_workflow_by_id

            wf = await get_workflow_by_id(task["user_id"], workflow_id, db)
            if not wf:
                logger.warning(
                    f"[Scheduler] Workflow '{workflow_id}' not found for task {task_id}; skipping."
                )
                return

            # create_run() queues the run for workflow_worker (Redis stream +
            # polling fallback), which claims it atomically via claim_queued_run() —
            # executing it here too would be a double-execution race.
            run_id = await create_run(
                workflow_id=workflow_id,
                workflow_name=wf.get("name", task["name"]),
                user_id=task["user_id"],
                user_email=task["user_email"],
                steps=wf.get("steps", []),
                db=db,
            )
            logger.info(f"[Scheduler] Task {task_id} queued (run={run_id}).")
        except Exception as exc:
            logger.exception(f"[Scheduler] Task {task_id} execution failed: {exc}")
        finally:
            await advance_or_complete(task, db)


# Module-level singleton — imported by main.py
scheduler = SchedulerWorker()
