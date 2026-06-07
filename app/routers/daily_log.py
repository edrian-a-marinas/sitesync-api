import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.daily_log import DailyLogCreate, DailyLogResponse, DailyLogUpdate
from app.services.daily_log import create_log, get_log, get_logs, update_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/daily-logs", tags=["Daily Logs"])


@router.get("", response_model=list[DailyLogResponse])
@limiter.limit("30/minute")
async def list_logs(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await get_logs(project_id, current_user, db)


@router.get("/{log_id}", response_model=DailyLogResponse)
@limiter.limit("30/minute")
async def get_log_by_id(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    log = await get_log(project_id, log_id, current_user, db)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    return log


@router.post("", response_model=DailyLogResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_log_endpoint(
    project_id: int,
    data: DailyLogCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_log(project_id, data, current_user, db)
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Log already exists for this date")


@router.patch("/{log_id}", response_model=DailyLogResponse)
@limiter.limit("20/minute")
async def update_log_endpoint(
    project_id: int,
    log_id: int,
    data: DailyLogUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    log = await update_log(project_id, log_id, data, current_user, db)
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    return log
