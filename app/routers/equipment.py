from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.equipment import EquipmentCreate, EquipmentResponse, EquipmentUpdate
from app.services.equipment import create_equipment, get_equipment, update_equipment

router = APIRouter(prefix="/projects/{project_id}/daily-logs/{log_id}/equipment", tags=["Equipment"])


@router.get("", response_model=list[EquipmentResponse])
@limiter.limit("30/minute")
async def list_equipment(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await get_equipment(log_id, db)


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_equipment_endpoint(
    project_id: int,
    log_id: int,
    data: EquipmentCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await create_equipment(log_id, data, current_user, db)


@router.patch("/{equipment_id}", response_model=EquipmentResponse)
@limiter.limit("20/minute")
async def update_equipment_endpoint(
    project_id: int,
    log_id: int,
    equipment_id: int,
    data: EquipmentUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    equipment = await update_equipment(log_id, equipment_id, data, current_user, db)
    if not equipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found")
    return equipment
