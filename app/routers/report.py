from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.report import ReportResponse
from app.services.report import _verify_project_access
from app.services.report import get_reports as _get_reports
from app.tasks.report import generate_weekly_report

router = APIRouter(prefix="/reports", tags=["Reports"])


# ==================== Tasks ====================
@router.post("/{project_id}/generate", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def trigger_report(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    if not await _verify_project_access(project_id, current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    generate_weekly_report.delay(project_id, current_user.id)
    raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Report generation started")


# ==================== Services ====================
@router.get("/{project_id}", response_model=list[ReportResponse])
@limiter.limit("30/minute")
async def get_reports(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    if not await _verify_project_access(project_id, current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return await _get_reports(project_id, db)
