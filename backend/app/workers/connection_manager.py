"""
WebSocket ConnectionManager — singleton that manages live connections per user.
The worker broadcasts step events here; the WebSocket route exposes them to clients.
"""
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)
        logger.debug(f"[WS] +1 connection for user={user_id} (total={len(self._connections[user_id])})")

    def disconnect(self, user_id: str, websocket: WebSocket):
        conns = self._connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.debug(f"[WS] -1 connection for user={user_id}")

    async def broadcast(self, user_id: str, event: dict):
        """Sends an event to every WebSocket connected for this user."""
        conns = self._connections.get(user_id, [])
        if not conns:
            return
        dead: List[WebSocket] = []
        for ws in list(conns):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


# Module-level singleton shared between the worker and WebSocket route.
manager = ConnectionManager()
