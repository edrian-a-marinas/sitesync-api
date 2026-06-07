import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.attendance import AttendanceCreate, AttendanceResponse
from app.services.attendance import get_attendance, submit_attendance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/daily-logs/{log_id}/attendance", tags=["Attendance"])


@router.post("", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def submit_attendance_endpoint(
    project_id: int,
    log_id: int,
    data: AttendanceCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    attendance = await submit_attendance(project_id, log_id, data, current_user, db)
    if not attendance:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already submitted or worker not assigned to project")
    return attendance


@router.get("", response_model=list[AttendanceResponse])
@limiter.limit("30/minute")
async def get_attendance_endpoint(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await get_attendance(project_id, log_id, current_user, db)
