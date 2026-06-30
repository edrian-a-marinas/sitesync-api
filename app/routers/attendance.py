from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.attendance import AttendanceCreate, AttendanceHistoryResponse, AttendanceResponse
from app.services.attendance import (
    create_attendance as _create_attendance,
)
from app.services.attendance import (
    get_attendance as _get_attendance,
)
from app.services.attendance import (
    get_my_attendance_history as _get_my_attendance_history,
)

router = APIRouter(prefix="/projects/{project_id}/daily-logs", tags=["Attendance"])


@router.post("/{log_id}/attendance", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_attendance(
    project_id: int,
    log_id: int,
    data: AttendanceCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    attendance = await _create_attendance(project_id, log_id, data, current_user, db)
    if not attendance:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already submitted or worker not assigned to project")
    return attendance


@router.get("/{log_id}/attendance", response_model=list[AttendanceResponse])
@limiter.limit("30/minute")
async def get_attendance(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_attendance(project_id, log_id, current_user, db)


@router.get("/attendance/me", response_model=list[AttendanceHistoryResponse])
@limiter.limit("30/minute")
async def get_my_attendance_history(
    project_id: int,
    request: Request,
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_my_attendance_history(project_id, current_user, db, page, limit)
