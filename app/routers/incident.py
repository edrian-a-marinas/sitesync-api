from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate
from app.services.incident import (
    create_incident as _create_incident,
)
from app.services.incident import (
    get_incidents as _get_incidents,
)
from app.services.incident import (
    update_incident as _update_incident,
)

router = APIRouter(prefix="/projects/{project_id}/daily-logs/{log_id}/incidents", tags=["Incidents"])


@router.get("", response_model=list[IncidentResponse])
@limiter.limit("30/minute")
async def get_incidents(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_incidents(project_id, log_id, current_user, db)


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_incident(
    project_id: int,
    log_id: int,
    data: IncidentCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    incident = await _create_incident(project_id, log_id, data, current_user, db)
    if not incident:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
@limiter.limit("10/minute")
async def update_incident(
    project_id: int,
    log_id: int,
    incident_id: int,
    data: IncidentUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    incident = await _update_incident(project_id, log_id, incident_id, data, current_user, db)
    if incident is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident
