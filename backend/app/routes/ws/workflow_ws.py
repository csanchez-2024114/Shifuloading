"""
WebSocket endpoint for real-time workflow execution events.

Connect: ws[s]://<host>/api/v3/ws/runs?token=<JWT>

Events (JSON):
  run_started    — workflow run began
  step_started   — a step is now executing
  step_completed — step finished successfully (includes result)
  step_failed    — step encountered an error
  run_completed  — all steps done
  run_failed     — run ended with errors

Transport: Redis Pub/Sub when REDIS_URL is set (multi-process safe),
           fallback to in-memory ConnectionManager (single-process only).
"""
import asyncio
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import jwt, JWTError

from config import Config
from app.workers.connection_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()

_SECRET = Config.SECRET_KEY
_ALGO = "HS256"


@router.websocket("/ws/runs")
async def workflow_runs_ws(
    websocket: WebSocket,
    token: str = Query(..., description="JWT de autenticación"),
):
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO])
        user_id: str = payload.get("user_id", "")
        if not user_id:
            await websocket.close(code=4001, reason="Token missing user_id")
            return
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if Config.REDIS_URL:
        await _redis_mode(websocket, user_id)
    else:
        await _inmemory_mode(websocket, user_id)


async def _redis_mode(websocket: WebSocket, user_id: str):
    """Subscribe to Redis channel and forward events to the WebSocket client."""
    channel = f"wf:{user_id}"
    r = aioredis.from_url(Config.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    await websocket.accept()
    logger.info(f"[WS/Redis] User {user_id} subscribed to {channel}")

    async def redis_to_ws():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except (WebSocketDisconnect, Exception):
            pass

    async def ws_receiver():
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass  # normal close — client navigated away or closed tab

    redis_task = asyncio.create_task(redis_to_ws())
    ws_task = asyncio.create_task(ws_receiver())
    try:
        done, pending = await asyncio.wait(
            [redis_task, ws_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()
        logger.info(f"[WS/Redis] User {user_id} disconnected.")


async def _inmemory_mode(websocket: WebSocket, user_id: str):
    """Fallback: in-memory manager for single-process deployments."""
    await manager.connect(user_id, websocket)
    logger.info(f"[WS/InMem] User {user_id} connected.")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
        logger.info(f"[WS/InMem] User {user_id} disconnected.")
