import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.report import ReportListResponse
from app.services.report import get_report_for_download, report_exists_today, validate_project_exists, verify_project_access
from app.services.report import get_reports as _get_reports
from app.services.s3 import get_file_bytes
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
    if await report_exists_today(project_id, current_user.id, db):
        return {"status": "exists", "detail": "You have already generated a report today"}
    if not generate_weekly_report.app.control.ping(timeout=1.0):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report generation service is currently unavailable. Please try again later.",
        )
    generate_weekly_report.delay(project_id, current_user.id, "manual")
    response.status_code = status.HTTP_202_ACCEPTED
    return {"status": "queued", "detail": "Report generation started"}


# ==================== Services ====================
@router.get("/{project_id}/{report_id}/download")
@limiter.limit("20/minute")
async def download_report(
    project_id: int,
    report_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    if not await verify_project_access(project_id, current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    report = await get_report_for_download(project_id, report_id, db)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    file_bytes = get_file_bytes(report.s3_key)
    filename = report.s3_key.split("/")[-1]
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )


@router.get("/{project_id}", response_model=ReportListResponse)
@limiter.limit("30/minute")
async def get_reports(
    project_id: int,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    if not await verify_project_access(project_id, current_user, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return await _get_reports(project_id, db, page=page, page_size=page_size, current_user=current_user)
