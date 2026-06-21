from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_owner, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.dashboard import OwnerDashboard, ProjectManagerAggregateDashboard, ProjectManagerDashboard, WorkerDashboard
from app.services.dashboard import get_manager_aggregate_dashboard as _get_manager_aggregate_dashboard
from app.services.dashboard import get_manager_dashboard as _get_manager_dashboard
from app.services.dashboard import get_owner_dashboard as _get_owner_dashboard
from app.services.dashboard import get_worker_dashboard as _get_worker_dashboard

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/owner", response_model=OwnerDashboard)
@limiter.limit("30/minute")
async def get_owner_dashboard(
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owner_dashboard(db)


@router.get("/manager/aggregate", response_model=ProjectManagerAggregateDashboard)
@limiter.limit("30/minute")
async def get_manager_aggregate_dashboard(
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await _get_manager_aggregate_dashboard(current_user, db)


@router.get("/manager/{project_id}", response_model=ProjectManagerDashboard)
@limiter.limit("30/minute")
async def get_manager_dashboard(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    dashboard = await _get_manager_dashboard(project_id, current_user, db)
    if not dashboard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found or access denied")
    return dashboard


@router.get("/worker", response_model=WorkerDashboard)
@limiter.limit("30/minute")
async def get_worker_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_worker_dashboard(current_user, db)
