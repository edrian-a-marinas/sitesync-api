import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import delete_pattern, get_cache, set_cache
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment
from app.models.report import Report
from app.models.role import Role
from app.models.user import User
from app.services.s3 import delete_file, generate_presigned_url, upload_file
from app.utils.pdf_builder import build_report_pdf

logger = logging.getLogger(__name__)


async def verify_project_access(project_id: int, current_user: User, db: AsyncSession) -> bool:

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


async def report_exists_today(project_id: int, user_id: int, db: AsyncSession) -> bool:
    today = date.today()
    cache_key = f"report:exists:{project_id}:{user_id}:{today}"
    if await get_cache(cache_key):
        return True
    existing = (
        await db.execute(
            select(Report).where(Report.project_id == project_id).where(Report.generated_by == user_id).where(func.date(Report.created_at) == today)
        )
    ).scalar_one_or_none()
    if existing:
        await set_cache(cache_key, True, ttl=86400)
        return True
    return False


async def generate_report(project_id: int, generated_by: int, db: AsyncSession, source: str = "manual") -> Report | None:
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

        filename = f"reports/report_{project_id}_{week_start}.pdf"
        upload_file(pdf_bytes, filename, "application/pdf")

        report = Report(
            project_id=project_id,
            generated_by=generated_by,
            week_start=week_start,
            week_end=week_end,
            s3_key=filename,
            source=source,
            total_hours=float(total_hours),
            total_material_cost=float(total_material_cost),
            log_count=len(logs),
            incident_count=len(incidents),
            open_incident_count=len([i for i in incidents if i.status == "Open"]),
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | source={source} | status=success")
        await delete_pattern(f"report:list:{project_id}:*")
        await delete_pattern(f"report:exists:{project_id}:*")
        return report
    except Exception as e:
        logger.error(f"REPORT | project_id={project_id} | status=failed | reason={str(e)}")
        return None


def generate_report_sync(project_id: int, generated_by: int | None, db, source: str = "manual") -> Report | None:
    week_end = date.today()
    week_start = week_end - timedelta(days=7)
    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if not project:
        logger.error(f"REPORT | project_id={project_id} | status=failed | reason=project not found")
        return None
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

        filename = f"reports/report_{project_id}_{week_start}.pdf"
        upload_file(pdf_bytes, filename, "application/pdf")

        report = Report(
            project_id=project_id,
            generated_by=generated_by,  # None for scheduled/auto
            week_start=week_start,
            week_end=week_end,
            s3_key=filename,
            source=source,
            total_hours=float(total_hours),
            total_material_cost=float(total_material_cost),
            log_count=len(logs),
            incident_count=len(incidents),
            open_incident_count=len([i for i in incidents if i.status == "Open"]),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | source={source} | generated_by={generated_by} | status=success")
        return report
    except Exception as e:
        if "uq_report_project_week" in str(e):
            logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | status=skipped | reason=already exists")
        else:
            logger.error(f"REPORT | project_id={project_id} | status=failed | reason={str(e)}")
        return None


def _get_file_url(s3_key: str) -> str:

    return generate_presigned_url(s3_key)


def cleanup_old_reports_sync(db) -> int:

    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    old_reports = db.execute(select(Report).where(Report.created_at < cutoff)).scalars().all()

    deleted_count = 0
    for r in old_reports:
        try:
            delete_file(r.s3_key)
            db.delete(r)
            db.commit()
            deleted_count += 1
            logger.info(f"REPORT_CLEANUP | report_id={r.id} | project_id={r.project_id} | s3_key={r.s3_key} | status=deleted")
        except Exception as e:
            db.rollback()
            logger.error(f"REPORT_CLEANUP | report_id={r.id} | project_id={r.project_id} | status=failed | reason={str(e)}")

    logger.info(f"REPORT_CLEANUP | total_checked={len(old_reports)} | total_deleted={deleted_count} | cutoff={cutoff.date()}")
    return deleted_count


async def get_reports(project_id: int, db: AsyncSession, page: int = 1, page_size: int = 20, current_user: User | None = None) -> dict:
    role = (await db.execute(select(Role).where(Role.id == current_user.role_id))).scalar_one_or_none() if current_user else None
    is_owner = role.name == "owner" if role else True
    current_user_id = current_user.id if current_user else None
    cache_key = f"report:list:{project_id}:{current_user_id}:{page}:{page_size}"
    cached = await get_cache(cache_key)
    if cached:
        logger.info(f"REPORT | get_reports | project_id={project_id} | page={page} | source=cache")
        return cached
    try:
        # Base filter: owner sees all, PM sees own + scheduled
        if is_owner:
            base_filter = Report.project_id == project_id
        else:
            base_filter = (Report.project_id == project_id) & (
                (Report.generated_by == current_user_id) | (Report.generated_by == None)  # scheduled/auto  # noqa: E711
            )

        total = (await db.execute(select(func.count()).select_from(Report).where(base_filter))).scalar() or 0
        result = await db.execute(
            select(Report, User.first_name, User.last_name)
            .outerjoin(User, User.id == Report.generated_by)
            .where(base_filter)
            .order_by(Report.week_start.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = result.all()
        logger.info(f"REPORT | get_reports | project_id={project_id} | page={page} | count={len(rows)} | source=db")
        items = [
            {
                "id": r.id,
                "project_id": r.project_id,
                "generated_by": r.generated_by,
                "generated_by_name": f"{first_name} {last_name}" if first_name else None,
                "week_start": str(r.week_start),
                "week_end": str(r.week_end),
                "s3_key": r.s3_key,
                "source": r.source,
                "file_url": _get_file_url(r.s3_key),
                "total_hours": float(r.total_hours),
                "total_material_cost": float(r.total_material_cost),
                "log_count": r.log_count,
                "incident_count": r.incident_count,
                "open_incident_count": r.open_incident_count,
                "created_at": str(r.created_at),
            }
            for r, first_name, last_name in rows
        ]
        data = {"items": items, "total": total, "page": page, "page_size": page_size}
        await set_cache(cache_key, data, ttl=3600)
        return data
    except Exception as e:
        logger.error(f"REPORT | get_reports | project_id={project_id} | error={str(e)}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
