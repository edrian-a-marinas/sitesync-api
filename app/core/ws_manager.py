import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)
        logger.info(f"WS | user_id={user_id} | status=connected | active_count={len(self.active_connections[user_id])}")

    def disconnect(self, user_id: int, websocket: WebSocket):
        connections = self.active_connections.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            del self.active_connections[user_id]
        logger.info(f"WS | user_id={user_id} | status=disconnected")

    async def send_to_user(self, user_id: int, message: dict):
        connections = self.active_connections.get(user_id, [])
        dead = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error(f"WS | user_id={user_id} | status=send_failed | reason={str(e)}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


manager = ConnectionManager()
