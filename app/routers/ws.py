import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.future import select

from app.core.security import decode_access_token
from app.core.ws_manager import manager
from app.database import AsyncSessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket, token: str = ""):
    payload = decode_access_token(token) if token else None
    if not payload:
        logger.warning("WS | status=rejected | reason=invalid or missing token")
        await websocket.close(code=4001)
        return

    user_id = payload.get("sub")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        logger.warning(f"WS | user_id={user_id} | status=rejected | reason=user not found or inactive")
        await websocket.close(code=4001)
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)
