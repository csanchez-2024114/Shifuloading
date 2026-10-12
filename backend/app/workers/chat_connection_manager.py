"""
ChatConnectionManager — WebSocket connection registry keyed by conversation_id.

Unlike the workflow ConnectionManager (keyed by user_id and used for broadcast),
this manager is keyed by conversation_id because a user may have multiple browser
tabs open on different conversations simultaneously. Each active connection gets its
own asyncio.Queue that the graph streaming task writes events into.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ChatConnectionManager:
    def __init__(self) -> None:
        # conversation_id → list of active WebSockets
        self._connections: Dict[str, List[WebSocket]] = {}
        # conversation_id → asyncio.Queue used as the graph→WS bridge
        self._queues: Dict[str, asyncio.Queue] = {}

    async def connect(self, conversation_id: str, websocket: WebSocket) -> asyncio.Queue:
        """Accept the WebSocket and register it. Returns the per-conversation queue."""
        await websocket.accept()
        q: asyncio.Queue = asyncio.Queue()
        self._connections.setdefault(conversation_id, []).append(websocket)
        self._queues[conversation_id] = q
        logger.info(f"[ChatWS] connected conversation_id={conversation_id}")
        return q

    def disconnect(self, conversation_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(conversation_id, [])
        if websocket in sockets:
            sockets.remove(websocket)
        if not sockets:
            self._connections.pop(conversation_id, None)
            self._queues.pop(conversation_id, None)
        logger.info(f"[ChatWS] disconnected conversation_id={conversation_id}")

    async def send_event(self, conversation_id: str, event: dict) -> None:
        """Send a JSON event to all WebSockets registered for this conversation."""
        sockets = self._connections.get(conversation_id, [])
        dead: list[WebSocket] = []
        for ws in list(sockets):
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(conversation_id, ws)

    def get_queue(self, conversation_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(conversation_id)


# Module-level singleton — imported by chat_ws.py
chat_manager = ChatConnectionManager()
