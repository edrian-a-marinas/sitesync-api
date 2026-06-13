from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.equipment import EquipmentCreate, EquipmentResponse, EquipmentUpdate
from app.services.equipment import (
    create_equipment as _create_equipment,
)
from app.services.equipment import (
    get_equipment as _get_equipment,
)
from app.services.equipment import (
    update_equipment as _update_equipment,
)

router = APIRouter(prefix="/projects/{project_id}/daily-logs/{log_id}/equipment", tags=["Equipment"])


@router.get("", response_model=list[EquipmentResponse])
@limiter.limit("30/minute")
async def get_equipment(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_equipment(project_id, log_id, current_user, db)


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_equipment(
    project_id: int,
    log_id: int,
    data: EquipmentCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    equipment = await _create_equipment(project_id, log_id, data, current_user, db)
    if not equipment:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    return equipment


@router.patch("/{equipment_id}", response_model=EquipmentResponse)
@limiter.limit("20/minute")
async def update_equipment(
    project_id: int,
    log_id: int,
    equipment_id: int,
    data: EquipmentUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    equipment = await _update_equipment(project_id, log_id, equipment_id, data, current_user, db)
    if equipment is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    if equipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")
    return equipment
