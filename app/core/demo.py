# DEMO FEATURE: delete this entire file if demo mode is retired
import logging

from fastapi import Depends, HTTPException, Request, status

from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def block_demo_writes(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.is_demo and request.method in WRITE_METHODS:
        logger.warning(f"DEMO | user_id={current_user.id} | method={request.method} | path={request.url.path} | status=blocked")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo accounts are read-only")
    return current_user
