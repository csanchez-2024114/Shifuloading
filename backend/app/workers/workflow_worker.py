"""
WorkflowWorker — background loop that dispatches queued workflow runs.

Fast path (Redis Streams, when redis_client is passed from lifespan):
  Consumes from "workflow:runs" via XREADGROUP — sub-second latency.
  workflow_run_service.create_run() publishes to the stream automatically.

Fallback path (MongoDB polling every poll_interval):
  Catches runs missed by the stream: scheduled triggers, startup drain,
  Redis unavailability. Default 60s — these runs are already time-insensitive.

Both paths use claim_queued_run() for atomic MongoDB-level claim to prevent
double-execution in multi-process environments.
"""
import asyncio
import logging
import socket

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import Config
from app.services.workflow_run_service import claim_queued_run
from app.workers.workflow_executor import WorkflowExecutor
from app.workers.heartbeat import worker_heartbeat

logger = logging.getLogger(__name__)

_STREAM_KEY     = "workflow:runs"
_CONSUMER_GROUP = "shifu-workers"
_CONSUMER_NAME  = f"worker-{socket.gethostname()}"
_BLOCK_MS       = 5_000  # 5s XREADGROUP block — releases to check _running flag


class WorkflowWorker:
    def __init__(self, poll_interval: int = 60):
        # ponytail: 60s poll — only for runs missed by stream (scheduled/trigger workers)
        self.poll_interval = poll_interval
        self._running = False

    async def start(self, db: AsyncIOMotorDatabase, redis_client=None):
        """Infinite loop — call once from lifespan startup."""
        self._running = True
        if Config.REDIS_URL:
            asyncio.create_task(
                worker_heartbeat("workflow_worker", Config.REDIS_URL, lambda: self._running)
            )

        if redis_client:
            logger.info("[Worker] Redis Streams mode (sub-second dispatch)")
            await self._start_streams(db, redis_client)
        else:
            logger.info("[Worker] Polling mode (every %ds)", self.poll_interval)
            await self._start_polling(db)

        logger.info("[Worker] Stopped.")

    def stop(self):
        self._running = False

    # ── Redis Streams ──────────────────────────────────────────────────────────

    async def _start_streams(self, db: AsyncIOMotorDatabase, redis) -> None:
        await self._ensure_group(redis)
        last_poll = 0.0

        while self._running:
            try:
                messages = await redis.xreadgroup(
                    _CONSUMER_GROUP,
                    _CONSUMER_NAME,
                    {_STREAM_KEY: ">"},
                    count=10,
                    block=_BLOCK_MS,
                )
                for _stream, msgs in (messages or []):
                    for msg_id, fields in msgs:
                        run = await claim_queued_run(db)
                        if run:
                            logger.info("[Worker] Stream run=%s workflow=%s", run["_id"], run.get("workflow_id"))
                            asyncio.create_task(WorkflowExecutor(run, db).execute())
                        try:
                            await redis.xack(_STREAM_KEY, _CONSUMER_GROUP, msg_id)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("[Worker] Streams error: %s", exc)
                await asyncio.sleep(5)

            # Fallback poll — drains runs missed by stream (scheduled/trigger workers)
            now = asyncio.get_event_loop().time()
            if now - last_poll >= self.poll_interval:
                await self._tick(db)
                last_poll = now

    async def _ensure_group(self, redis) -> None:
        try:
            await redis.xgroup_create(_STREAM_KEY, _CONSUMER_GROUP, "$", mkstream=True)
            logger.info("[Worker] Consumer group '%s' created on stream '%s'", _CONSUMER_GROUP, _STREAM_KEY)
        except Exception:
            pass  # group already exists — normal on restart

    # ── MongoDB polling fallback ───────────────────────────────────────────────

    async def _start_polling(self, db: AsyncIOMotorDatabase) -> None:
        while self._running:
            try:
                await self._tick(db)
            except Exception as exc:
                logger.exception("[Worker] Unhandled error in tick: %s", exc)
            await asyncio.sleep(self.poll_interval)

    async def _tick(self, db: AsyncIOMotorDatabase) -> None:
        """Drain all queued runs atomically (FIFO within priority tier)."""
        while True:
            run = await claim_queued_run(db)
            if not run:
                break
            logger.info("[Worker] Poll claimed run=%s workflow=%s", run["_id"], run.get("workflow_id"))
            asyncio.create_task(WorkflowExecutor(run, db).execute())


worker = WorkflowWorker()
