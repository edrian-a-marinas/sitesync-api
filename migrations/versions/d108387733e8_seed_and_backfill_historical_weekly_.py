"""seed and backfill historical weekly reports
Revision ID: d108387733e8
Revises: a7ffc34146a0
Create Date: 2026-06-30
"""
from datetime import date, timedelta
from typing import Sequence, Union
from alembic import op
from sqlalchemy.orm import Session
from app.models.daily_log import DailyLog
from app.models.report import Report

revision: str = 'd108387733e8'
down_revision: Union[str, Sequence[str], None] = 'a7ffc34146a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from sqlalchemy import func
from app.models.attendance import Attendance
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project
from app.services.s3 import upload_file
from app.utils.pdf_builder import build_report_pdf

def upgrade() -> None:
    """Backfill weekly reports from earliest daily log per project up to today."""
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        project_ids = [row[0] for row in session.query(DailyLog.project_id).distinct().all()]
        for project_id in project_ids:
            earliest_log = (
                session.query(DailyLog.log_date)
                .filter(DailyLog.project_id == project_id)
                .order_by(DailyLog.log_date.asc())
                .first()
            )
            if not earliest_log:
                continue
            current_week_start = earliest_log[0] - timedelta(days=earliest_log[0].weekday())  # Monday of that week
            today = date.today()
            count_created = 0
            while current_week_start <= today:
                existing = (
                    session.query(Report)
                    .filter(Report.project_id == project_id, Report.week_start == current_week_start)
                    .first()
                )
                if not existing:
                    fake_week_end_offset = current_week_start + timedelta(days=6)
                    # generate_report_sync computes its own week_start/week_end as (today-7, today),
                    # so we temporarily call it using a session-level date override via direct insert instead.
                    _backfill_one_week(session, project_id, current_week_start, fake_week_end_offset)
                    count_created += 1
                current_week_start += timedelta(days=7)
            print(f"REPORT_SEED | project_id={project_id} | weeks_created={count_created}")
        session.commit()
    finally:
        session.close()
def _backfill_one_week(session: Session, project_id: int, week_start: date, week_end: date) -> None:
    project = session.query(Project).filter(Project.id == project_id).first()
    if not project:
        return
    total_hours = (
        session.query(func.sum(Attendance.hours_worked))
        .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
        .filter(DailyLog.project_id == project_id, DailyLog.log_date >= week_start, DailyLog.log_date <= week_end)
        .scalar()
        or 0.0
    )
    total_material_cost = (
        session.query(func.sum(Material.total_cost))
        .join(DailyLog, DailyLog.id == Material.daily_log_id)
        .filter(DailyLog.project_id == project_id, DailyLog.log_date >= week_start, DailyLog.log_date <= week_end)
        .scalar()
        or 0.0
    )
    logs = (
        session.query(DailyLog)
        .filter(DailyLog.project_id == project_id, DailyLog.log_date >= week_start, DailyLog.log_date <= week_end)
        .all()
    )
    incidents = (
        session.query(Incident)
        .join(DailyLog, DailyLog.id == Incident.daily_log_id)
        .filter(DailyLog.project_id == project_id, DailyLog.log_date >= week_start, DailyLog.log_date <= week_end)
        .all()
    )
    if not logs:
        return  # skip weeks with no actual activity
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
        generated_by=project.owner_id,
        week_start=week_start,
        week_end=week_end,
        s3_key=filename,
        source="seeded",
        total_hours=float(total_hours),
        total_material_cost=float(total_material_cost),
        log_count=len(logs),
        incident_count=len(incidents),
        open_incident_count=len([i for i in incidents if i.status == "Open"]),
    )
    session.add(report)
def downgrade() -> None:
    """Remove all seeded historical reports."""
    bind = op.get_bind()
    session = Session(bind=bind)
    try:
        deleted = session.query(Report).filter(Report.source == "seeded").delete()
        session.commit()
        print(f"REPORT_SEED_ROLLBACK | deleted={deleted}")
    finally:
        session.close()