import logging
import os
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project
from app.models.report import Report

logger = logging.getLogger(__name__)


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

        filename = f"reports/report_{project_id}_{week_start}.txt"
        os.makedirs("reports", exist_ok=True)
        with open(filename, "w") as f:
            f.write(report_content)

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


async def get_reports(project_id: int, db: AsyncSession) -> list[Report]:
    try:
        result = await db.execute(select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc()))
        reports = result.scalars().all()
        logger.info(f"REPORT | get_reports | project_id={project_id} | count={len(reports)}")
        return reports
    except Exception as e:
        logger.error(f"REPORT | get_reports | project_id={project_id} | error={str(e)}")
        return []
