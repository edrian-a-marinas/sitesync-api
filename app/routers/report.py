from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.report import ReportResponse
from app.services.report import get_reports as _get_reports
from app.services.report import report_exists_this_week, validate_project_exists, verify_project_access
from app.tasks.report import generate_weekly_report

router = APIRouter(prefix="/reports", tags=["Reports"])


# ==================== Tasks ====================
@router.post("/{project_id}/generate")
@limiter.limit("5/minute")
async def trigger_report(
    project_id: int,
    request: Request,
    response: Response,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    if not await validate_project_exists(project_id, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not await verify_project_access(project_id, current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if await report_exists_this_week(project_id, db):
        return {"status": "exists", "detail": "Report already exists for this week"}
    if not generate_weekly_report.app.control.ping(timeout=1.0):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report generation service is currently unavailable. Please try again later.",
        )
    generate_weekly_report.delay(project_id, current_user.id)
    response.status_code = status.HTTP_202_ACCEPTED
    return {"status": "queued", "detail": "Report generation started"}


# ==================== Services ====================
@router.get("/{project_id}", response_model=list[ReportResponse])
@limiter.limit("30/minute")
async def get_reports(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    if not await verify_project_access(project_id, current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return await _get_reports(project_id, db)
