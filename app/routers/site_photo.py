import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_owner_or_manager
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.site_photo import SitePhotoResponse
from app.services.site_photo import delete_site_photo as _delete_site_photo
from app.services.site_photo import get_site_photos as _get_site_photos
from app.services.site_photo import upload_site_photo as _upload_site_photo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/daily-logs/{log_id}/site-photos", tags=["Site Photos"])


@router.get("", response_model=list[SitePhotoResponse])
@limiter.limit("30/minute")
async def get_site_photos(
    project_id: int,
    log_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_site_photos(project_id, log_id, current_user, db)


@router.post("", response_model=SitePhotoResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def upload_site_photo(
    project_id: int,
    log_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        photo = await _upload_site_photo(project_id, log_id, file, current_user, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if photo is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily log not found")
    return photo


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_site_photo(
    project_id: int,
    log_id: int,
    photo_id: int,
    request: Request,
    current_user: User = Depends(require_owner_or_manager),
    db: AsyncSession = Depends(get_db),
):
    result = await _delete_site_photo(project_id, log_id, photo_id, current_user, db)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    if result is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not assigned to this project")
