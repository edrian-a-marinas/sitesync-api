import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.material import MaterialCreate, MaterialResponse, MaterialUpdate
from app.services.material import create_material, get_materials, update_material

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/daily-logs/{log_id}/materials", tags=["Materials"])


@router.get("", response_model=list[MaterialResponse])
@limiter.limit("30/minute")
async def list_materials(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await get_materials(log_id, db)


@router.post("", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_material_endpoint(
    project_id: int,
    log_id: int,
    data: MaterialCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    return await create_material(log_id, data, current_user, db)


@router.patch("/{material_id}", response_model=MaterialResponse)
@limiter.limit("20/minute")
async def update_material_endpoint(
    project_id: int,
    log_id: int,
    material_id: int,
    data: MaterialUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    material = await update_material(log_id, material_id, data, current_user, db)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    return material
