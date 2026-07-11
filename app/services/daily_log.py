import logging

from kombu.exceptions import OperationalError
from sqlalchemy import String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache, delete_pattern, get_cache, set_cache
from app.core.settings import settings
from app.models.daily_log import DailyLog
from app.models.project import ProjectAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.daily_log import DailyLogCreate, DailyLogListResponse, DailyLogResponse, DailyLogUpdate
from app.tasks.embedding import generate_daily_log_embedding

DEFAULT_CACHE_TTL = settings.DEFAULT_CACHE_TTL

logger = logging.getLogger(__name__)


async def _is_owner(current_user: User, db: AsyncSession) -> bool:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    return role is not None and role.name == "owner"


async def _to_response(log: DailyLog, db: AsyncSession) -> DailyLogResponse:
    user = (await db.execute(select(User).where(User.id == log.submitted_by))).scalar_one_or_none()
    full_name = f"{user.first_name} {user.last_name}" if user else "Unknown"
    return DailyLogResponse(
        id=log.id,
        project_id=log.project_id,
        submitted_by=log.submitted_by,
        submitted_by_name=full_name,
        log_date=log.log_date,
        weather_condition=log.weather_condition,
        work_accomplished=log.work_accomplished,
        notes=log.notes,
    )


async def get_daily_logs(
    project_id: int,
    current_user: User,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> DailyLogListResponse:
    if not await _is_owner(current_user, db):
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            return DailyLogListResponse(items=[], total=0, page=page, page_size=page_size)
    search_term = search.strip() if search else None
    cache_key = f"daily_logs:{project_id}:{page}:{page_size}:{search_term or ''}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"DAILY_LOG | get_daily_logs | project_id={project_id} | page={page} | search={search_term} | source=cache")
        return DailyLogListResponse(**cached)
    base_query = select(DailyLog).where(DailyLog.project_id == project_id)
    count_query = select(func.count()).select_from(DailyLog).where(DailyLog.project_id == project_id)
    if search_term:
        pattern = f"%{search_term}%"
        search_filter = (
            DailyLog.log_date.cast(String).ilike(pattern)
            | DailyLog.weather_condition.ilike(pattern)
            | DailyLog.work_accomplished.ilike(pattern)
            | DailyLog.notes.ilike(pattern)
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(base_query.order_by(DailyLog.log_date.desc()).limit(page_size).offset((page - 1) * page_size))
    logs = result.scalars().all()
    items = [await _to_response(log, db) for log in logs]
    response = DailyLogListResponse(items=items, total=total, page=page, page_size=page_size)
    logger.info(f"DAILY_LOG | get_daily_logs | project_id={project_id} | page={page} | search={search_term} | count={len(items)} | source=db")
    await set_cache(cache_key, response.model_dump(mode="json"), ttl=DEFAULT_CACHE_TTL)
    return response


async def get_daily_log_by_id(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> DailyLogResponse | None:
    if not await _is_owner(current_user, db):
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            return None
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        return None
    return await _to_response(log, db)


async def create_daily_log(project_id: int, data: DailyLogCreate, current_user: User, db: AsyncSession) -> DailyLog | None:
    if not await _is_owner(current_user, db):
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            return None
    log = DailyLog(**data.model_dump(), project_id=project_id, submitted_by=current_user.id)
    db.add(log)
    await db.commit()
    await db.refresh(log)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    await delete_pattern(f"daily_logs:{project_id}:*")
    logger.info(f"LOG_CREATE | project_id={project_id} | log_id={log.id} | submitted_by={current_user.id} | status=success")
    try:
        generate_daily_log_embedding.delay(log.id)
    except OperationalError:
        logger.error(f"EMBEDDING | log_id={log.id} | status=failed | reason=queue unreachable")
    return await _to_response(log, db)


async def update_daily_log(project_id: int, log_id: int, data: DailyLogUpdate, current_user: User, db: AsyncSession) -> DailyLogResponse | None:
    if not await _is_owner(current_user, db):
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            return None
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(log, field, value)
    await db.commit()
    await db.refresh(log)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    await delete_pattern(f"daily_logs:{project_id}:*")
    logger.info(f"LOG_UPDATE | project_id={project_id} | log_id={log_id} | updated_by={current_user.id} | status=success")
    try:
        generate_daily_log_embedding.delay(log.id)
    except OperationalError:
        logger.error(f"EMBEDDING | log_id={log_id} | status=failed | reason=queue unreachable")
    return await _to_response(log, db)
