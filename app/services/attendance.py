import logging

from kombu.exceptions import OperationalError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache, delete_pattern, get_cache, set_cache
from app.core.settings import settings
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.project import ProjectAssignment, WorkerAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.attendance import AttendanceCreate
from app.tasks.embedding import generate_daily_log_embedding

DEFAULT_CACHE_TTL = settings.DEFAULT_CACHE_TTL

logger = logging.getLogger(__name__)


async def create_attendance(project_id: int, log_id: int, data: AttendanceCreate, current_user: User, db: AsyncSession) -> Attendance | None:
    # If manager, verify they are assigned to this project
    if current_user.role.name == "project_manager":
        manager_assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not manager_assigned:
            logger.warning(
                f"ATTENDANCE | user_id={current_user.id} | project_id={project_id} | status=failed | reason=manager not assigned to project"
            )
            return None

    # Verify worker is assigned to project
    assigned = (
        await db.execute(select(WorkerAssignment).where(WorkerAssignment.project_id == project_id).where(WorkerAssignment.user_id == data.worker_id))
    ).scalar_one_or_none()
    if not assigned:
        logger.warning(
            f"ATTENDANCE | worker_id={data.worker_id} | project_id={project_id} | submitted_by={current_user.id} | status=failed | reason=worker not assigned to project"
        )
        return None

    # Verify log exists
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        logger.warning(f"ATTENDANCE | log_id={log_id} | project_id={project_id} | status=failed | reason=log not found")
        return None

    # Check for duplicate before insert — avoids rollback on dirty session
    existing = (
        await db.execute(select(Attendance).where(Attendance.daily_log_id == log_id).where(Attendance.worker_id == data.worker_id))
    ).scalar_one_or_none()
    if existing:
        logger.warning(
            f"ATTENDANCE | worker_id={data.worker_id} | log_id={log_id} | submitted_by={current_user.id} | status=failed | reason=already submitted"
        )
        return None

    attendance = Attendance(
        daily_log_id=log_id,
        worker_id=data.worker_id,
        hours_worked=data.hours_worked,
    )
    db.add(attendance)
    await db.commit()
    await db.refresh(attendance)
    await delete_pattern(f"attendance:{project_id}:{log_id}:*")
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_pattern("dashboard:owner:*")
    logger.info(f"ATTENDANCE | worker_id={data.worker_id} | log_id={log_id} | submitted_by={current_user.id} | status=success")
    try:
        generate_daily_log_embedding.delay(log_id)
    except OperationalError:
        logger.error(f"EMBEDDING | log_id={log_id} | status=failed | reason=queue unreachable")
    return attendance


async def get_attendance(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[Attendance]:
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        logger.warning(f"ATTENDANCE | get | log_id={log_id} | project_id={project_id} | status=failed | reason=log not found")
        return []

    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    is_worker = role and role.name == "site_worker"
    scope = str(current_user.id) if is_worker else "all"
    cache_key = f"attendance:{project_id}:{log_id}:{scope}"

    cached = await get_cache(cache_key)
    if cached is not None:
        logger.info(f"ATTENDANCE | get | log_id={log_id} | user_id={current_user.id} | scope={scope} | count={len(cached)} | source=cache")
        return cached

    if is_worker:
        result = await db.execute(select(Attendance).where(Attendance.daily_log_id == log_id).where(Attendance.worker_id == current_user.id))
        logger.info(f"ATTENDANCE | get | log_id={log_id} | worker_id={current_user.id} | scope=own | source=db")
    else:
        result = await db.execute(select(Attendance).where(Attendance.daily_log_id == log_id))
        logger.info(f"ATTENDANCE | get | log_id={log_id} | user_id={current_user.id} | scope=all | source=db")

    attendance = result.scalars().all()
    serialized = [{"id": a.id, "daily_log_id": a.daily_log_id, "worker_id": a.worker_id, "hours_worked": float(a.hours_worked)} for a in attendance]
    await set_cache(cache_key, serialized, ttl=DEFAULT_CACHE_TTL)
    return attendance


async def get_my_attendance_history(project_id: int, current_user: User, db: AsyncSession, page: int = 1, limit: int = 20) -> dict:
    offset = (page - 1) * limit

    cache_key = f"attendance:history:{current_user.id}:{project_id}:{page}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"ATTENDANCE_HISTORY | worker_id={current_user.id} | project_id={project_id} | page={page} | source=cache")
        return cached

    base_query = (
        select(Attendance, DailyLog.log_date)
        .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
        .where(DailyLog.project_id == project_id)
        .where(Attendance.worker_id == current_user.id)
    )
    count_query = (
        select(func.count())
        .select_from(Attendance)
        .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
        .where(DailyLog.project_id == project_id)
        .where(Attendance.worker_id == current_user.id)
    )

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(base_query.order_by(DailyLog.log_date.desc()).offset(offset).limit(limit))
    rows = result.all()

    items = [{"id": a.id, "daily_log_id": a.daily_log_id, "hours_worked": float(a.hours_worked), "log_date": str(log_date)} for a, log_date in rows]
    response = {"items": items, "total": total, "page": page, "limit": limit}
    await set_cache(cache_key, response, ttl=DEFAULT_CACHE_TTL)
    logger.info(
        f"ATTENDANCE_HISTORY | worker_id={current_user.id} | project_id={project_id} | page={page} | total={total} | count={len(rows)} | source=db"
    )
    return response
