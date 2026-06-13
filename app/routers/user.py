from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.auth import UserResponse, UserUpdateRequest
from app.services.user import (
    get_user_by_id as _get_user_by_id,
)
from app.services.user import (
    get_users as _get_users,
)
from app.services.user import (
    set_user_status as _set_user_status,
)
from app.services.user import (
    update_user_by_id as _update_user_by_id,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserResponse])
@limiter.limit("30/minute")
async def get_users(
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await _get_users(current_user, db)


@router.get("/{user_id}", response_model=UserResponse)
@limiter.limit("30/minute")
async def get_user_by_id(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user_by_id(user_id, current_user, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
@limiter.limit("20/minute")
async def update_user_by_id(
    user_id: int,
    data: UserUpdateRequest,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    user = await _update_user_by_id(user_id, data, current_user, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or access denied")
    return user


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
@limiter.limit("10/minute")
async def deactivate_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    user = await _set_user_status(user_id, False, current_user, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied or user not found")
    return user


@router.patch("/{user_id}/activate", response_model=UserResponse)
@limiter.limit("10/minute")
async def activate_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    user = await _set_user_status(user_id, True, current_user, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied or user not found")
    return user
