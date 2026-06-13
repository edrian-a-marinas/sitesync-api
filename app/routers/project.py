from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.project import (
    AssignUserRequest,
    PhaseCreate,
    PhaseResponse,
    PhaseUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.project import (
    assign_manager as _assign_manager,
)
from app.services.project import (
    assign_worker as _assign_worker,
)
from app.services.project import (
    create_phase as _create_phase,
)
from app.services.project import (
    create_project as _create_project,
)
from app.services.project import (
    get_project_by_id as _get_project_by_id,
)
from app.services.project import (
    get_projects as _get_projects,
)
from app.services.project import (
    update_phase as _update_phase,
)
from app.services.project import (
    update_project as _update_project,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectResponse])
@limiter.limit("30/minute")
async def get_projects(
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await _get_projects(current_user, db)


@router.get("/{project_id}", response_model=ProjectResponse)
@limiter.limit("30/minute")
async def get_project_by_id(
    project_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_by_id(project_id, current_user, db)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_project(
    data: ProjectCreate,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await _create_project(data, current_user, db)


@router.patch("/{project_id}", response_model=ProjectResponse)
@limiter.limit("20/minute")
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    project = await _update_project(project_id, data, current_user, db)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/{project_id}/assign-manager", response_model=dict)
@limiter.limit("10/minute")
async def assign_manager(
    project_id: int,
    data: AssignUserRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    assignment = await _assign_manager(project_id, data, current_user, db)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not found or user is not a project manager")
    return {"message": "Manager assigned successfully"}


@router.post("/{project_id}/assign-worker", response_model=dict)
@limiter.limit("10/minute")
async def assign_worker(
    project_id: int,
    data: AssignUserRequest,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    assignment = await _assign_worker(project_id, data, current_user, db)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not found, access denied, or user is not a site worker")
    return {"message": "Worker assigned successfully"}


@router.post("/{project_id}/phases", response_model=PhaseResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_phase(
    project_id: int,
    data: PhaseCreate,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    phase = await _create_phase(project_id, data, current_user, db)
    if not phase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return phase


@router.patch("/{project_id}/phases/{phase_id}", response_model=PhaseResponse)
@limiter.limit("20/minute")
async def update_phase(
    project_id: int,
    phase_id: int,
    data: PhaseUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    phase = await _update_phase(project_id, phase_id, data, current_user, db)
    if not phase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phase not found")
    return phase
