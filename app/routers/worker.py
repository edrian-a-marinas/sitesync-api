from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_worker
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.daily_log import DailyLogResponse
from app.schemas.worker import WorkerProjectResponse
from app.services.worker import get_my_projects as _get_my_projects
from app.services.worker import get_today_log as _get_today_log

router = APIRouter(prefix="/workers", tags=["Worker"])


@router.get("/me/projects", response_model=list[WorkerProjectResponse])
@limiter.limit("30/minute")
async def get_worker_projects(
    request: Request,
    current_user: User = Depends(require_worker),
    db: AsyncSession = Depends(get_db),
):
    return await _get_my_projects(current_user, db)


@router.get("/me/projects/{project_id}/daily-logs/today", response_model=DailyLogResponse)
@limiter.limit("30/minute")
async def get_worker_today_log(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_worker),
    db: AsyncSession = Depends(get_db),
):
    log = await _get_today_log(project_id, current_user, db)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No log found for this project")
    return log
