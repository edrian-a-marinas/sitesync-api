from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.report import ReportResponse
from app.services.report import get_reports
from app.tasks.report import generate_weekly_report

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/{project_id}/generate", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def trigger_report(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    generate_weekly_report.delay(project_id, current_user.id)
    raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Report generation started")


@router.get("/{project_id}", response_model=list[ReportResponse])
@limiter.limit("30/minute")
async def list_reports(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await get_reports(project_id, db)
