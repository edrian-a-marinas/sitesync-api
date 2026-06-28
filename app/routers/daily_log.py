from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.daily_log import DailyLogCreate, DailyLogListResponse, DailyLogResponse, DailyLogUpdate
from app.services.daily_log import (
    create_daily_log as _create_daily_log,
)
from app.services.daily_log import (
    get_daily_log_by_id as _get_daily_log_by_id,
)
from app.services.daily_log import (
    get_daily_logs as _get_daily_logs,
)
from app.services.daily_log import (
    update_daily_log as _update_daily_log,
)

router = APIRouter(prefix="/projects/{project_id}/daily-logs", tags=["Daily Logs"])


@router.get("", response_model=DailyLogListResponse)
@limiter.limit("30/minute")
async def get_daily_logs(
    project_id: int,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=100),
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await _get_daily_logs(project_id, current_user, db, page, page_size, search)


@router.get("/{log_id}", response_model=DailyLogResponse)
@limiter.limit("30/minute")
async def get_log_by_id(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    log = await _get_daily_log_by_id(project_id, log_id, current_user, db)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    return log


@router.post("", response_model=DailyLogResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_daily_log(
    project_id: int,
    data: DailyLogCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    try:
        log = await _create_daily_log(project_id, data, current_user, db)
        if not log:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found or access denied")
        return log
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Log already exists for this date")


@router.patch("/{log_id}", response_model=DailyLogResponse)
@limiter.limit("20/minute")
async def update_daily_log(
    project_id: int,
    log_id: int,
    data: DailyLogUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    log = await _update_daily_log(project_id, log_id, data, current_user, db)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    return log
