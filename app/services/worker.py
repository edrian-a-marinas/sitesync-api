import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import get_cache, set_cache
from app.core.settings import settings
from app.models.daily_log import DailyLog
from app.models.project import Project, WorkerAssignment
from app.models.user import User
from app.schemas.daily_log import DailyLogResponse
from app.schemas.worker import WorkerProjectResponse

DEFAULT_CACHE_TTL = settings.DEFAULT_CACHE_TTL
WORKER_TODAY_LOG_TTL = settings.WORKER_TODAY_LOG_TTL

logger = logging.getLogger(__name__)


async def get_my_projects(current_user: User, db: AsyncSession) -> list[WorkerProjectResponse]:
    cache_key = f"worker:projects:{current_user.id}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"WORKER | get_my_projects | user_id={current_user.id} | source=cache")
        return cached

    result = await db.execute(
        select(Project).join(WorkerAssignment, WorkerAssignment.project_id == Project.id).where(WorkerAssignment.user_id == current_user.id)
    )
    projects = result.scalars().all()

    response = [
        WorkerProjectResponse(
            id=p.id,
            name=p.name,
            location=p.location,
            status=p.status,
            start_date=p.start_date,
            target_end_date=p.target_end_date,
            total_budget=float(p.total_budget),
        )
        for p in projects
    ]

    await set_cache(cache_key, [r.model_dump(mode="json") for r in response], ttl=DEFAULT_CACHE_TTL)
    logger.info(f"WORKER | get_my_projects | user_id={current_user.id} | count={len(response)} | source=db")
    return response


async def get_today_log(project_id: int, current_user: User, db: AsyncSession) -> DailyLogResponse | None:
    assigned = (
        await db.execute(select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == current_user.id))
    ).scalar_one_or_none()
    if not assigned:
        logger.warning(
            f"WORKER | get_today_log | user_id={current_user.id} | project_id={project_id} | status=failed | reason=worker not assigned to project"
        )
        return None

    today = date.today()
    cache_key = f"worker:today_log:{project_id}:{current_user.id}:{today}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"WORKER | get_today_log | user_id={current_user.id} | project_id={project_id} | source=cache")
        return DailyLogResponse(**cached)

    # Try today first, fallback to most recent
    log = (await db.execute(select(DailyLog).where(DailyLog.project_id == project_id).where(DailyLog.log_date == today))).scalar_one_or_none()

    if not log:
        log = (
            await db.execute(select(DailyLog).where(DailyLog.project_id == project_id).order_by(DailyLog.log_date.desc()).limit(1))
        ).scalar_one_or_none()

    if not log:
        logger.info(f"WORKER | get_today_log | user_id={current_user.id} | project_id={project_id} | status=no log found")
        return None

    submitter = (await db.execute(select(User).where(User.id == log.submitted_by))).scalar_one_or_none()
    full_name = f"{submitter.first_name} {submitter.last_name}" if submitter else "Unknown"

    response = DailyLogResponse(
        id=log.id,
        project_id=log.project_id,
        submitted_by=log.submitted_by,
        submitted_by_name=full_name,
        log_date=log.log_date,
        weather_condition=log.weather_condition,
        work_accomplished=log.work_accomplished,
        notes=log.notes,
    )

    await set_cache(cache_key, response.model_dump(mode="json"), ttl=WORKER_TODAY_LOG_TTL)
    logger.info(f"WORKER | get_today_log | user_id={current_user.id} | project_id={project_id} | log_id={log.id} | source=db")
    return response
