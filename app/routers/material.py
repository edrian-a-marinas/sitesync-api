from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.material import MaterialCreate, MaterialResponse, MaterialUpdate
from app.services.material import (
    create_material as _create_material,
)
from app.services.material import (
    delete_material as _delete_material,
)
from app.services.material import (
    get_materials as _get_materials,
)
from app.services.material import (
    update_material as _update_material,
)

router = APIRouter(prefix="/projects/{project_id}/daily-logs/{log_id}/materials", tags=["Materials"])


@router.get("", response_model=list[MaterialResponse])
@limiter.limit("30/minute")
async def get_materials(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_materials(project_id, log_id, current_user, db)


@router.post("", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_material(
    project_id: int,
    log_id: int,
    data: MaterialCreate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    material = await _create_material(project_id, log_id, data, current_user, db)
    if not material:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    return material


@router.patch("/{material_id}", response_model=MaterialResponse)
@limiter.limit("20/minute")
async def update_material(
    project_id: int,
    log_id: int,
    material_id: int,
    data: MaterialUpdate,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    material = await _update_material(project_id, log_id, material_id, data, current_user, db)
    if material is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    return material


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_material(
    project_id: int,
    log_id: int,
    material_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    result = await _delete_material(project_id, log_id, material_id, current_user, db)
    if result is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
