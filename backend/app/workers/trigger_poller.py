"""
TriggerPoller — polls active event-trigger workflows and fires runs when the
trigger condition is met.

This worker handles workflows with trigger_type="event". It differs from
SchedulerWorker (which handles time-based "scheduled" triggers) in that it:
  1. Calls an integration tool (the trigger_tool) to check whether new data
     has arrived (e.g., new emails, new Slack messages, new form submissions).
  2. Fires a workflow run only if the tool indicates the condition was met.
  3. Respects per-workflow polling intervals stored in trigger_config.every_seconds.

trigger_config fields (stored in WorkflowModel.trigger_config):
  every_seconds  — how often to check (set by fijar_frecuencia_workflow)
  next_check     — datetime when this workflow should be polled next
  last_checked   — datetime of the most recent poll (informational)
  trigger_tool   — BigTool name that fetches trigger data (e.g. "listar_correos")
  trigger_filter — dict of kwargs passed to the trigger tool

Polling interval → use case mapping:
  180s  (every_3m)  — critical / near-real-time monitoring
  300s  (every_5m)  — fast monitoring
  900s  (every_15m) — inbox / feeds
  3600s (hourly)    — lead capture / processing
  14400s+           — handled by SchedulerWorker (scheduled trigger_type)
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from config import Config
from app.services.workflow_run_service import create_run
from app.workers.heartbeat import worker_heartbeat
from app.services.world_state import extract_trigger_signal, upsert_world_state

logger = logging.getLogger(__name__)

# Master polling interval: how often we scan for due event-trigger workflows.
# Each individual workflow is checked at its own every_seconds cadence.
_MASTER_POLL_INTERVAL = 60  # seconds

# Sentinel far-future datetime used during atomic claim to prevent double-execution
_FAR_FUTURE = datetime(9999, 12, 31, tzinfo=timezone.utc)


class TriggerPoller:
    def __init__(self, master_interval: int = _MASTER_POLL_INTERVAL):
        self.master_interval = master_interval
        self._running = False

    async def start(self, db: AsyncIOMotorDatabase) -> None:
        self._running = True
        logger.info(f"[TriggerPoller] Started (master tick every {self.master_interval}s)")
        if Config.REDIS_URL:
            asyncio.create_task(
                worker_heartbeat("trigger_poller", Config.REDIS_URL, lambda: self._running)
            )
        while self._running:
            try:
                await self._tick(db)
            except Exception as exc:
                logger.exception(f"[TriggerPoller] Unhandled error in tick: {exc}")
            await asyncio.sleep(self.master_interval)
        logger.info("[TriggerPoller] Stopped.")

    def stop(self) -> None:
        self._running = False

    async def _tick(self, db: AsyncIOMotorDatabase) -> None:
        """Scan all active event-trigger workflows that are due for a check."""
        now = datetime.now(timezone.utc)
        cursor = db["workflows"].find({
            "status": "active",
            "trigger_type": "event",
            "trigger_config.next_check": {"$lte": now},
        })

        async for wf in cursor:
            # Atomic claim: set next_check far into the future to prevent
            # another worker process from picking up the same workflow.
            claimed = await db["workflows"].find_one_and_update(
                {
                    "_id": wf["_id"],
                    "trigger_config.next_check": {"$lte": now},
                },
                {"$set": {"trigger_config.next_check": _FAR_FUTURE}},
                return_document=True,
            )
            if not claimed:
                # Another process claimed it first — skip
                continue

            every_seconds = int(
                claimed.get("trigger_config", {}).get("every_seconds", 900)
            )
            asyncio.create_task(self._check_and_fire(claimed, every_seconds, db))

    async def _check_and_fire(
        self, wf: dict, every_seconds: int, db: AsyncIOMotorDatabase
    ) -> None:
        """
        Load credentials, call the trigger tool, evaluate the result.
        If the trigger condition is met → create and execute a WorkflowRun.
        Always advances next_check regardless of outcome.
        """
        wf_id = str(wf["_id"])
        user_id = wf.get("user_id", "")
        user_email = wf.get("user_email", "")
        trigger_config = wf.get("trigger_config", {})
        trigger_tool_name: str = trigger_config.get("trigger_tool", "")
        trigger_filter: dict = trigger_config.get("trigger_filter", {})

        try:
            # Load credentials + build BigTools (same path used by context_loader_node)
            from app.services.chat_memory import load_user_integrations
            from app.services.bigtools_loader import get_all_bigtools
            from app.core.constants import Collections
            from app.billing.plans import filter_providers_by_plan

            connected = await load_user_integrations(user_id, db)
            provider_map = {
                c["provider"]: c.get("account_id", "") for c in (connected or [])
            }
            connected_providers = {c["provider"] for c in (connected or [])}
            try:
                user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)}, {"plan": 1})
            except Exception:
                user_doc = None
            plan = (user_doc or {}).get("plan") or "free"
            allowed_providers = filter_providers_by_plan(plan, connected_providers)

            bigtools = await asyncio.to_thread(
                get_all_bigtools,
                user_id,
                user_email,
                db,
                provider_map,
                allowed_providers,
            )
            tool_map = {bt.name: bt for bt in bigtools}
            trigger_tool = tool_map.get(trigger_tool_name)

            if not trigger_tool:
                logger.warning(
                    f"[TriggerPoller] trigger_tool '{trigger_tool_name}' not found "
                    f"for workflow {wf_id} — skipping this tick"
                )
                return

            # Invoke the trigger tool with the stored filter
            result_raw = await trigger_tool.func(**trigger_filter) if asyncio.iscoroutinefunction(trigger_tool.func) \
                else await asyncio.to_thread(trigger_tool.func, **trigger_filter)

            result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw

            # Evaluate: did new data arrive?
            should_fire = False
            if isinstance(result, list) and len(result) > 0:
                should_fire = True
            elif isinstance(result, dict) and result.get("triggered"):
                should_fire = True

            # Persist world state signal regardless of whether trigger fired
            ws_entries = extract_trigger_signal(trigger_tool_name, result, wf.get("name", ""))
            asyncio.create_task(upsert_world_state(db, user_id, ws_entries))

            if should_fire:
                logger.info(
                    f"[TriggerPoller] Trigger met — firing run for workflow {wf_id}"
                )
                # create_run() queues the run for workflow_worker (Redis stream +
                # polling fallback), which claims it atomically via
                # claim_queued_run() — executing it here too would double-run it.
                run_id = await create_run(
                    workflow_id=wf_id,
                    workflow_name=wf.get("name", ""),
                    user_id=user_id,
                    user_email=user_email,
                    steps=wf.get("steps", []),
                    db=db,
                )
                logger.info(
                    f"[TriggerPoller] Run {run_id} queued for workflow {wf_id}"
                )
            else:
                logger.debug(
                    f"[TriggerPoller] Trigger not met for workflow {wf_id}"
                )

        except Exception as exc:
            logger.exception(
                f"[TriggerPoller] Error checking workflow {wf_id}: {exc}"
            )
        finally:
            # Always advance next_check so the workflow continues to be polled
            now = datetime.now(timezone.utc)
            try:
                await db["workflows"].update_one(
                    {"_id": wf["_id"]},
                    {
                        "$set": {
                            "trigger_config.last_checked": now,
                            "trigger_config.next_check": now + timedelta(seconds=every_seconds),
                        }
                    },
                )
            except Exception as exc:
                logger.warning(
                    f"[TriggerPoller] Failed to advance next_check for {wf_id}: {exc}"
                )


# Module-level singleton — imported by main.py
trigger_poller = TriggerPoller()
