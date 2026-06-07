import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_owner, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.dashboard import OwnerDashboard, ProjectManagerDashboard, WorkerDashboard
from app.services.dashboard import get_manager_dashboard, get_owner_dashboard, get_worker_dashboard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/owner", response_model=OwnerDashboard)
@limiter.limit("30/minute")
async def owner_dashboard(
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await get_owner_dashboard(db)


@router.get("/manager/{project_id}", response_model=ProjectManagerDashboard)
@limiter.limit("30/minute")
async def manager_dashboard(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    dashboard = await get_manager_dashboard(project_id, current_user, db)
    if not dashboard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found or access denied")
    return dashboard


@router.get("/worker", response_model=WorkerDashboard)
@limiter.limit("30/minute")
async def worker_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_worker_dashboard(current_user, db)
