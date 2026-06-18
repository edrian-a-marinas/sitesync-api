import logging

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.daily_log import DailyLog
from app.models.project import ProjectAssignment, WorkerAssignment
from app.models.role import Role
from app.models.site_photo import SitePhoto
from app.models.user import User
from app.services.s3 import generate_presigned_url, upload_file

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


async def _check_manager_assigned(project_id: int, current_user: User, db: AsyncSession) -> tuple[bool, str | None]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    role_name = role.name if role else None
    if role and role.name == "project_manager":
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(
                f"SITE_PHOTO | user_id={current_user.id} | role={role_name} | project_id={project_id} | status=failed | reason=manager not assigned to project"
            )
            return False, role_name
    return True, role_name


async def _validate_file(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(f"SITE_PHOTO | filename={file.filename} | status=failed | reason=invalid content type {file.content_type}")
        raise ValueError(f"File type {file.content_type} not allowed. Allowed types: jpg, png, webp, pdf")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        logger.warning(f"SITE_PHOTO | filename={file.filename} | status=failed | reason=file too large ({len(contents)} bytes)")
        raise ValueError("File exceeds maximum size of 10MB")

    return contents


def _build_response(photo: SitePhoto) -> dict:
    return {
        "id": photo.id,
        "daily_log_id": photo.daily_log_id,
        "uploaded_by": photo.uploaded_by,
        "filename": photo.filename,
        "content_type": photo.content_type,
        "s3_key": photo.s3_key,
        "uploaded_at": photo.uploaded_at,
        "file_url": generate_presigned_url(photo.s3_key),
    }


async def upload_site_photo(project_id: int, log_id: int, file: UploadFile, current_user: User, db: AsyncSession) -> dict | None | bool:
    is_assigned, role_name = await _check_manager_assigned(project_id, current_user, db)
    if not is_assigned:
        return False
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        logger.warning(f"SITE_PHOTO | log_id={log_id} | project_id={project_id} | role={role_name} | status=failed | reason=log not found")
        return None
    try:
        contents = await _validate_file(file)
    except ValueError as e:
        logger.warning(f"SITE_PHOTO | log_id={log_id} | uploaded_by={current_user.id} | role={role_name} | status=failed | reason={str(e)}")
        raise

    filename = file.filename or "upload"
    s3_key = f"site_photos/{log_id}/{filename}"
    upload_file(contents, s3_key, file.content_type)

    photo = SitePhoto(
        daily_log_id=log_id,
        uploaded_by=current_user.id,
        filename=filename,
        content_type=file.content_type,
        s3_key=s3_key,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    logger.info(f"SITE_PHOTO | log_id={log_id} | photo_id={photo.id} | uploaded_by={current_user.id} | role={role_name} | status=success")
    return _build_response(photo)


async def get_site_photos(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[dict]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()

    if role and role.name == "site_worker":
        assigned = (
            await db.execute(
                select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(
                f"SITE_PHOTO_GET | log_id={log_id} | user_id={current_user.id} | role={role.name if role else None} | status=failed | reason=worker not assigned to project"
            )
            return []
    result = await db.execute(select(SitePhoto).where(SitePhoto.daily_log_id == log_id))
    photos = result.scalars().all()
    logger.info(f"SITE_PHOTO_GET | log_id={log_id} | user_id={current_user.id} | role={role.name if role else None} | count={len(photos)}")
    return [_build_response(p) for p in photos]
