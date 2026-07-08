# DEMO FEATURE: delete this entire file if demo mode is retired
import logging
import re

from fastapi import Depends, HTTPException, Request, status

from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Demo owner-only allowed write actions (AI Assistant, ML retrain, Report generation)
DEMO_ALLOWED_WRITE_PATTERNS = [
    (re.compile(r"^/api/v1/ai/query$"), "POST"),
    (re.compile(r"^/api/v1/ml/retrain$"), "POST"),
    (re.compile(r"^/api/v1/reports/\d+/generate$"), "POST"),
]

DEMO_OWNER_ROLE_ID = 1  # owner role


async def block_demo_writes(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.is_demo and request.method in WRITE_METHODS:
        is_allowed = current_user.role_id == DEMO_OWNER_ROLE_ID and any(
            pattern.match(request.url.path) and method == request.method for pattern, method in DEMO_ALLOWED_WRITE_PATTERNS
        )
        if is_allowed:
            return current_user
        logger.warning(f"DEMO | user_id={current_user.id} | method={request.method} | path={request.url.path} | status=blocked")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo accounts are read-only. Owner demo can use AI Assistant, Analytics, and generate reports only.",
        )
    return current_user
