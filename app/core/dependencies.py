import logging
from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import get_cache, set_cache
from app.core.security import decode_access_token
from app.core.settings import settings
from app.database import get_db
from app.models.role import Role
from app.models.user import User

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if not payload:
        logger.warning("AUTH | status=failed | reason=invalid or expired token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user_id = payload.get("sub")
    cache_key = f"auth:user:{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        if not cached.get("is_active"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        return User(**cached)

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        logger.warning(f"AUTH | user_id={user_id} | status=failed | reason=user not found or inactive")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    user_dict = {
        c.name: (value.isoformat() if isinstance(value, datetime) else value) for c in user.__table__.columns for value in [getattr(user, c.name)]
    }
    await set_cache(cache_key, user_dict, ttl=settings.AUTH_USER_CACHE_TTL)
    return user


async def require_owner(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(Role).where(Role.id == current_user.role_id))
    role = result.scalar_one_or_none()
    if not role or role.name != "owner":
        logger.warning(f"AUTHZ | user_id={current_user.id} | role={role.name if role else None} | status=forbidden | required=owner")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    return current_user


async def require_owner_or_manager(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(Role).where(Role.id == current_user.role_id))
    role = result.scalar_one_or_none()
    if not role or role.name not in ("owner", "project_manager"):
        logger.warning(f"AUTHZ | user_id={current_user.id} | role={role.name if role else None} | status=forbidden | required=owner_or_manager")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner or Project Manager access required")
    return current_user


async def require_worker(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(Role).where(Role.id == current_user.role_id))
    role = result.scalar_one_or_none()
    if not role or role.name != "site_worker":
        logger.warning(f"AUTHZ | user_id={current_user.id} | role={role.name if role else None} | status=forbidden | required=site_worker")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Site Worker access required")
    return current_user
