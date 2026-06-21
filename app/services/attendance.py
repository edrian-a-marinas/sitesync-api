import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_cache
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.project import ProjectAssignment, WorkerAssignment
from app.models.user import User
from app.schemas.attendance import AttendanceCreate

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
    await delete_cache(f"dashboard:manager:{project_id}")
    await delete_cache(f"dashboard:manager:aggregate:{current_user.id}")
    await delete_cache("dashboard:owner")
    logger.info(f"ATTENDANCE | worker_id={data.worker_id} | log_id={log_id} | submitted_by={current_user.id} | status=success")
    return attendance


async def get_attendance(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[Attendance]:
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        logger.warning(f"ATTENDANCE | get | log_id={log_id} | project_id={project_id} | status=failed | reason=log not found")
        return []
    from app.models.role import Role

    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if role and role.name == "site_worker":
        result = await db.execute(select(Attendance).where(Attendance.daily_log_id == log_id).where(Attendance.worker_id == current_user.id))
        logger.info(f"ATTENDANCE | get | log_id={log_id} | worker_id={current_user.id} | scope=own")
    else:
        result = await db.execute(select(Attendance).where(Attendance.daily_log_id == log_id))
        logger.info(f"ATTENDANCE | get | log_id={log_id} | user_id={current_user.id} | scope=all")

    return result.scalars().all()


async def get_my_attendance_history(project_id: int, current_user: User, db: AsyncSession, page: int = 1, limit: int = 20) -> list[dict]:
    offset = (page - 1) * limit
    result = await db.execute(
        select(Attendance, DailyLog.log_date)
        .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
        .where(DailyLog.project_id == project_id)
        .where(Attendance.worker_id == current_user.id)
        .order_by(DailyLog.log_date.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()
    logger.info(f"ATTENDANCE_HISTORY | worker_id={current_user.id} | project_id={project_id} | page={page} | limit={limit} | count={len(rows)}")
    return [{"id": a.id, "daily_log_id": a.daily_log_id, "hours_worked": float(a.hours_worked), "log_date": str(log_date)} for a, log_date in rows]
