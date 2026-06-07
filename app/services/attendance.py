import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.project import WorkerAssignment
from app.models.user import User
from app.schemas.attendance import AttendanceCreate

logger = logging.getLogger(__name__)


async def submit_attendance(project_id: int, log_id: int, data: AttendanceCreate, current_user: User, db: AsyncSession) -> Attendance | None:
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
        return None

    attendance = Attendance(
        daily_log_id=log_id,
        worker_id=data.worker_id,
        hours_worked=data.hours_worked,
    )
    db.add(attendance)
    try:
        await db.commit()
        await db.refresh(attendance)
        logger.info(f"ATTENDANCE | worker_id={data.worker_id} | log_id={log_id} | submitted_by={current_user.id} | status=success")
        return attendance
    except IntegrityError:
        await db.rollback()
        logger.warning(
            f"ATTENDANCE | worker_id={data.worker_id} | log_id={log_id} | submitted_by={current_user.id} | status=failed | reason=already submitted"
        )
        return None


async def get_attendance(project_id: int, log_id: int, current_user: User, db: AsyncSession) -> list[Attendance]:
    log = (await db.execute(select(DailyLog).where(DailyLog.id == log_id).where(DailyLog.project_id == project_id))).scalar_one_or_none()
    if not log:
        return []

    result = await db.execute(select(Attendance).where(Attendance.daily_log_id == log_id))
    return result.scalars().all()
