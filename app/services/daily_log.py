import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.daily_log import DailyLog
from app.models.project import ProjectAssignment
from app.models.user import User
from app.core.cache import delete_cache
from app.schemas.daily_log import DailyLogCreate, DailyLogUpdate

logger = logging.getLogger(__name__)


async def get_logs(project_id: int, current_user: User, db: AsyncSession) -> list[DailyLog]:
    # PM — verify assigned to project
    if current_user.role_id != 1:
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            return []

    result = await db.execute(select(DailyLog).where(DailyLog.project_id == project_id))
    return result.scalars().all()


async def get_log(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> DailyLog | None:
    if current_user.role_id != 1:
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            return None

    return (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()


async def create_log(project_id: int, data: DailyLogCreate, current_user: User, db: AsyncSession) -> DailyLog:
    log = DailyLog(**data.model_dump(), project_id=project_id, submitted_by=current_user.id)
    db.add(log)
    await db.commit()
    await db.refresh(log)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache("dashboard:owner")
    logger.info(f"LOG_CREATE | project_id={project_id} | log_id={log.id} | submitted_by={current_user.id} | status=success")
    return log


async def update_log(project_id: int, log_id: int, data: DailyLogUpdate, current_user: User, db: AsyncSession) -> DailyLog | None:
    log = await get_log(project_id, log_id, current_user, db)
    if not log:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(log, field, value)
    await db.commit()
    await db.refresh(log)
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache("dashboard:owner")
    logger.info(f"LOG_UPDATE | project_id={project_id} | log_id={log_id} | updated_by={current_user.id} | status=success")
    return log
