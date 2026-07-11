import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache, get_cache, set_cache
from app.core.settings import settings
from app.models.daily_log import DailyLog
from app.models.project import ProjectAssignment, WorkerAssignment
from app.models.role import Role
from app.models.site_photo import SitePhoto
from app.models.user import User
from app.services.s3 import delete_file, generate_presigned_url, upload_file

DEFAULT_CACHE_TTL = settings.DEFAULT_CACHE_TTL

logger = logging.getLogger(__name__)

# PDF included for PMs can also upload supporting documentation such Material delivery receipts, etc.
ALLOWED_CONTENT_TYPES = settings.ALLOWED_CONTENT_TYPES
MAX_FILE_SIZE_BYTES = settings.MAX_FILE_SIZE_BYTES  # 10MB


async def _check_role_access(project_id: int, current_user: User, db: AsyncSession) -> tuple[bool, str | None]:
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
    if role and role.name == "site_worker":
        assigned = (
            await db.execute(
                select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(
                f"SITE_PHOTO | user_id={current_user.id} | role={role_name} | project_id={project_id} | status=failed | reason=worker not assigned to project"
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
        "uploaded_at": photo.uploaded_at.isoformat() if photo.uploaded_at else None,
        "file_url": generate_presigned_url(photo.s3_key),
    }


async def upload_site_photo(project_id: int, log_id: int, file: UploadFile, current_user: User, db: AsyncSession) -> dict | None | bool:
    is_assigned, role_name = await _check_role_access(project_id, current_user, db)
    if not is_assigned:
        return False
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        logger.warning(f"SITE_PHOTO | log_id={log_id} | project_id={project_id} | role={role_name} | status=failed | reason=log not found")
        return None

    # Enforce max 10 attachments per daily log
    photo_count = (await db.execute(select(func.count(SitePhoto.id)).where(SitePhoto.daily_log_id == log_id))).scalar() or 0
    if photo_count >= 10:
        logger.warning(
            f"SITE_PHOTO | log_id={log_id} | uploaded_by={current_user.id} | role={role_name} | status=failed | reason=max 10 photos per log reached"
        )
        raise ValueError("Maximum of 10 attachments per daily log reached.")
    try:
        contents = await _validate_file(file)
    except ValueError as e:
        logger.warning(f"SITE_PHOTO | log_id={log_id} | uploaded_by={current_user.id} | role={role_name} | status=failed | reason={str(e)}")
        raise

    original_name = Path(file.filename or "upload").name  # strips any path traversal
    ext = Path(original_name).suffix.lower()
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    s3_key = f"site_photos/{log_id}/{safe_filename}"
    filename = safe_filename
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

    await delete_cache(f"site_photos:{log_id}")
    logger.info(f"SITE_PHOTO | log_id={log_id} | photo_id={photo.id} | uploaded_by={current_user.id} | role={role_name} | status=success")
    return _build_response(photo)


async def get_site_photo_for_download(project_id: int, log_id: int, photo_id: int, current_user: User, db: AsyncSession) -> SitePhoto | None | bool:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    role_name = role.name if role else None
    if role and role.name == "site_worker":
        assigned = (
            await db.execute(
                select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(
                f"SITE_PHOTO_DOWNLOAD | photo_id={photo_id} | user_id={current_user.id} | role={role_name} | status=failed | reason=worker not assigned to project"
            )
            return False
    photo = (await db.execute(select(SitePhoto).where(SitePhoto.id == photo_id).where(SitePhoto.daily_log_id == log_id))).scalar_one_or_none()
    if not photo:
        logger.warning(f"SITE_PHOTO_DOWNLOAD | photo_id={photo_id} | log_id={log_id} | user_id={current_user.id} | status=not_found")
        return None
    logger.info(f"SITE_PHOTO_DOWNLOAD | photo_id={photo_id} | log_id={log_id} | user_id={current_user.id} | role={role_name} | status=success")
    return photo


async def get_site_photos(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[dict]:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    role_name = role.name if role else None
    if role and role.name == "site_worker":
        assigned = (
            await db.execute(
                select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(
                f"SITE_PHOTO_GET | log_id={log_id} | user_id={current_user.id} | role={role_name} | status=failed | reason=worker not assigned to project"
            )
            return []
    cache_key = f"site_photos:{log_id}"
    cached = await get_cache(cache_key)
    if cached is not None:
        logger.info(f"SITE_PHOTO_GET | log_id={log_id} | user_id={current_user.id} | role={role_name} | source=cache | count={len(cached)}")
        return cached
    result = await db.execute(select(SitePhoto).where(SitePhoto.daily_log_id == log_id))
    photos = result.scalars().all()
    response = [_build_response(p) for p in photos]
    await set_cache(cache_key, response, ttl=DEFAULT_CACHE_TTL)
    logger.info(f"SITE_PHOTO_GET | log_id={log_id} | user_id={current_user.id} | role={role_name} | source=db | count={len(photos)}")
    return response


async def delete_site_photo(project_id: int, log_id: int, photo_id: int, current_user: User, db: AsyncSession) -> bool | None:
    is_assigned, role_name = await _check_role_access(project_id, current_user, db)
    if not is_assigned:
        return False
    photo = (await db.execute(select(SitePhoto).where(SitePhoto.id == photo_id).where(SitePhoto.daily_log_id == log_id))).scalar_one_or_none()

    if not photo:
        logger.warning(
            f"SITE_PHOTO_DELETE | photo_id={photo_id} | log_id={log_id} | user_id={current_user.id} | role={role_name} | status=failed | reason=photo not found"
        )
        return None

    delete_file(photo.s3_key)
    await db.delete(photo)
    await db.commit()

    await delete_cache(f"site_photos:{log_id}")
    logger.info(f"SITE_PHOTO_DELETE | photo_id={photo_id} | log_id={log_id} | user_id={current_user.id} | role={role_name} | status=success")
    return True
