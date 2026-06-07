import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.future import select

from app.core.celery import celery_app
from app.database import AsyncSessionLocal
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project
from app.models.report import Report

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_weekly_report")
def generate_weekly_report(project_id: int, generated_by: int):
    import asyncio

    asyncio.run(_generate_weekly_report(project_id, generated_by))


async def _generate_weekly_report(project_id: int, generated_by: int):
    async with AsyncSessionLocal() as db:
        week_end = date.today()
        week_start = week_end - timedelta(days=7)

        # Get project
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        if not project:
            logger.error(f"REPORT | project_id={project_id} | status=failed | reason=project not found")
            return

        # Aggregate data
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

        # Generate simple text report locally for now (S3 later)
        report_content = f"""
SITESYNC WEEKLY REPORT
Project: {project.name}
Period: {week_start} to {week_end}
------------------------------
Total Logs Submitted: {len(logs)}
Total Hours Worked: {float(total_hours)}
Total Material Cost: {float(total_material_cost)}
Total Incidents: {len(incidents)}
Open Incidents: {len([i for i in incidents if i.status == "Open"])}
        """

        # Save locally for now
        filename = f"reports/report_{project_id}_{week_start}.txt"
        import os

        os.makedirs("reports", exist_ok=True)
        with open(filename, "w") as f:
            f.write(report_content)

        # Save metadata to DB
        report = Report(
            project_id=project_id,
            generated_by=generated_by,
            week_start=week_start,
            week_end=week_end,
            s3_key=filename,
        )
        db.add(report)
        await db.commit()

        logger.info(f"REPORT | project_id={project_id} | week_start={week_start} | status=success")


@celery_app.task(name="trigger_all_weekly_reports")
def trigger_all_weekly_reports():
    import asyncio

    asyncio.run(_trigger_all_weekly_reports())


async def _trigger_all_weekly_reports():
    async with AsyncSessionLocal() as db:
        projects = (await db.execute(select(Project).where(Project.status == "Active"))).scalars().all()
        for project in projects:
            generate_weekly_report.delay(project.id, project.owner_id)
            logger.info(f"REPORT_TRIGGER | project_id={project.id} | status=queued")
