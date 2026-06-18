import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import get_cache, set_cache
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment
from app.models.report import Report
from app.models.user import User
from app.utils.pdf_builder import build_report_pdf

logger = logging.getLogger(__name__)


async def verify_project_access(project_id: int, current_user: User, db: AsyncSession) -> bool:
    from app.models.role import Role

    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none()
    if role and role.name == "owner":
        return True
    assigned = (
        await db.execute(
            select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    return assigned is not None


async def validate_project_exists(project_id: int, db: AsyncSession) -> bool:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    return project is not None


async def report_exists_this_week(project_id: int, db: AsyncSession) -> bool:
    week_start = date.today() - timedelta(days=7)
    cache_key = f"report:exists:{project_id}:{week_start}"
    if await get_cache(cache_key):
        return True
    existing = (await db.execute(select(Report).where(Report.project_id == project_id).where(Report.week_start == week_start))).scalar_one_or_none()
    if existing:
        await set_cache(cache_key, True, ttl=86400)
        return True
    return False


async def generate_report(project_id: int, generated_by: int, db: AsyncSession) -> Report | None:
    week_end = date.today()
    week_start = week_end - timedelta(days=7)

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        logger.error(f"REPORT | project_id={project_id} | status=failed | reason=project not found")
        return None

    try:
        total_hours = (
            await db.execute(
                select(func.sum(Attendance.hours_worked))
                .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
                .where(DailyLog.project_id == project_id)
                .where(DailyLog.log_date >= week_start)
                .where(DailyLog.log_date <= week_end)
            )
        ).scalar() or 0.0

        total_material_cost = (
            await db.execute(
                select(func.sum(Material.total_cost))
                .join(DailyLog, DailyLog.id == Material.daily_log_id)
                .where(DailyLog.project_id == project_id)
                .where(DailyLog.log_date >= week_start)
                .where(DailyLog.log_date <= week_end)
            )
        ).scalar() or 0.0

        logs = (
            (
                await db.execute(
                    select(DailyLog)
                    .where(DailyLog.project_id == project_id)
                    .where(DailyLog.log_date >= week_start)
                    .where(DailyLog.log_date <= week_end)
                )
            )
            .scalars()
            .all()
        )

        incidents = (
            (
                await db.execute(
                    select(Incident)
                    .join(DailyLog, DailyLog.id == Incident.daily_log_id)
                    .where(DailyLog.project_id == project_id)
                    .where(DailyLog.log_date >= week_start)
                    .where(DailyLog.log_date <= week_end)
                )
            )
            .scalars()
            .all()
        )

        pdf_bytes = build_report_pdf(
            project_name=project.name,
            week_start=week_start,
            week_end=week_end,
            total_hours=float(total_hours),
            total_material_cost=float(total_material_cost),
            log_count=len(logs),
            incident_count=len(incidents),
            open_incident_count=len([i for i in incidents if i.status == "Open"]),
        )

        from app.services.s3 import upload_file

        filename = f"reports/report_{project_id}_{week_start}.pdf"
        upload_file(pdf_bytes, filename, "application/pdf")

        report = Report(
            project_id=project_id,
            generated_by=generated_by,
            week_start=week_start,
            week_end=week_end,
            s3_key=filename,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | status=success")
        return report

    except Exception as e:
        logger.error(f"REPORT | project_id={project_id} | status=failed | reason={str(e)}")
        return None


def generate_report_sync(project_id: int, generated_by: int, db) -> Report | None:
    week_end = date.today()
    week_start = week_end - timedelta(days=7)
    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if not project:
        logger.error(f"REPORT | project_id={project_id} | status=failed | reason=project not found")
        return None
    existing = db.execute(select(Report).where(Report.project_id == project_id).where(Report.week_start == week_start)).scalar_one_or_none()
    if existing:
        logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | status=skipped | reason=already exists")
        return existing
    try:
        total_hours = (
            db.execute(
                select(func.sum(Attendance.hours_worked))
                .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
                .where(DailyLog.project_id == project_id)
                .where(DailyLog.log_date >= week_start)
                .where(DailyLog.log_date <= week_end)
            ).scalar()
            or 0.0
        )

        total_material_cost = (
            db.execute(
                select(func.sum(Material.total_cost))
                .join(DailyLog, DailyLog.id == Material.daily_log_id)
                .where(DailyLog.project_id == project_id)
                .where(DailyLog.log_date >= week_start)
                .where(DailyLog.log_date <= week_end)
            ).scalar()
            or 0.0
        )

        logs = (
            db.execute(
                select(DailyLog).where(DailyLog.project_id == project_id).where(DailyLog.log_date >= week_start).where(DailyLog.log_date <= week_end)
            )
            .scalars()
            .all()
        )

        incidents = (
            db.execute(
                select(Incident)
                .join(DailyLog, DailyLog.id == Incident.daily_log_id)
                .where(DailyLog.project_id == project_id)
                .where(DailyLog.log_date >= week_start)
                .where(DailyLog.log_date <= week_end)
            )
            .scalars()
            .all()
        )

        pdf_bytes = build_report_pdf(
            project_name=project.name,
            week_start=week_start,
            week_end=week_end,
            total_hours=float(total_hours),
            total_material_cost=float(total_material_cost),
            log_count=len(logs),
            incident_count=len(incidents),
            open_incident_count=len([i for i in incidents if i.status == "Open"]),
        )

        from app.services.s3 import upload_file

        filename = f"reports/report_{project_id}_{week_start}.pdf"
        upload_file(pdf_bytes, filename, "application/pdf")

        report = Report(
            project_id=project_id,
            generated_by=generated_by,
            week_start=week_start,
            week_end=week_end,
            s3_key=filename,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | status=success")
        return report

    except Exception as e:
        if "uq_report_project_week" in str(e):
            logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | status=skipped | reason=already exists")
        else:
            logger.error(f"REPORT | project_id={project_id} | status=failed | reason={str(e)}")
        return None


def _get_file_url(s3_key: str) -> str:
    from app.services.s3 import generate_presigned_url

    return generate_presigned_url(s3_key)


async def get_reports(project_id: int, db: AsyncSession) -> list[dict]:
    cache_key = f"report:list:{project_id}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"REPORT | get_reports | project_id={project_id} | source=cache")
        return cached
    try:
        result = await db.execute(select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc(), Report.week_start.desc()))
        reports = result.scalars().all()
        logger.info(f"REPORT | get_reports | project_id={project_id} | count={len(reports)} | source=db")
        data = [
            {
                "id": r.id,
                "project_id": r.project_id,
                "generated_by": r.generated_by,
                "week_start": str(r.week_start),
                "week_end": str(r.week_end),
                "s3_key": r.s3_key,
                "file_url": _get_file_url(r.s3_key),
                "created_at": str(r.created_at),
            }
            for r in reports
        ]
        await set_cache(cache_key, data, ttl=3600)
        return data
    except Exception as e:
        logger.error(f"REPORT | get_reports | project_id={project_id} | error={str(e)}")
        return []
