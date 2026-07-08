from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.models.user import User
from app.services.notification import delete_notification as _delete_notification
from app.services.notification import get_notifications as _get_notifications
from app.services.notification import get_unread_count as _get_unread_count
from app.services.notification import mark_all_as_read as _mark_all_as_read
from app.services.notification import mark_as_read as _mark_as_read

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
@limiter.limit("30/minute")
async def get_notifications(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=6, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    return await _get_notifications(current_user.id, page, page_size)


@router.get("/unread-count")
@limiter.limit("30/minute")
async def get_unread_count(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    count = await _get_unread_count(current_user.id)
    return {"unread_count": count}


@router.patch("/{notification_id}/read")
@limiter.limit("30/minute")
async def mark_as_read(
    notification_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    success = await _mark_as_read(notification_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"status": "read"}


@router.patch("/read-all")
@limiter.limit("30/minute")
async def mark_all_as_read(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    count = await _mark_all_as_read(current_user.id)
    return {"status": "read", "modified_count": count}


@router.delete("/{notification_id}")
@limiter.limit("30/minute")
async def delete_notification(
    notification_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    success = await _delete_notification(notification_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {"status": "deleted"}
