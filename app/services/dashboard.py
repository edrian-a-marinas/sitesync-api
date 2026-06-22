import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.cache import get_cache, set_cache
from app.core.settings import settings
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment, ProjectPhase, WorkerAssignment
from app.models.role import Role
from app.models.user import User
from app.schemas.dashboard import (
    CurrentShiftLog,
    MaterialWeeklyTrend,
    OwnerDashboard,
    PhaseBudgetSummary,
    ProjectBudgetSummary,
    ProjectManagerAggregateDashboard,
    ProjectManagerDashboard,
    WorkerDashboard,
)

logger = logging.getLogger(__name__)


OWNER_DASHBOARD_TTL = settings.OWNER_DASHBOARD_TTL
MANAGER_DASHBOARD_TTL = settings.MANAGER_DASHBOARD_TTL


async def _get_dashboard_deltas(
    db: AsyncSession,
    project_ids: list[int],
) -> dict:
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_last_week = start_of_week - timedelta(weeks=1)
    end_of_last_week = start_of_week - timedelta(days=1)

    # Incidents
    incidents_this_week = (
        await db.execute(
            select(func.count(Incident.id))
            .join(DailyLog, DailyLog.id == Incident.daily_log_id)
            .where(DailyLog.project_id.in_(project_ids))
            .where(DailyLog.log_date >= start_of_week)
        )
    ).scalar() or 0

    incidents_last_week = (
        await db.execute(
            select(func.count(Incident.id))
            .join(DailyLog, DailyLog.id == Incident.daily_log_id)
            .where(DailyLog.project_id.in_(project_ids))
            .where(DailyLog.log_date >= start_of_last_week)
            .where(DailyLog.log_date <= end_of_last_week)
        )
    ).scalar() or 0

    # Spending
    spending_this_week = float(
        (
            await db.execute(
                select(func.sum(Material.total_cost))
                .join(DailyLog, DailyLog.id == Material.daily_log_id)
                .where(DailyLog.project_id.in_(project_ids))
                .where(DailyLog.log_date >= start_of_week)
            )
        ).scalar()
        or 0.0
    )

    spending_last_week = float(
        (
            await db.execute(
                select(func.sum(Material.total_cost))
                .join(DailyLog, DailyLog.id == Material.daily_log_id)
                .where(DailyLog.project_id.in_(project_ids))
                .where(DailyLog.log_date >= start_of_last_week)
                .where(DailyLog.log_date <= end_of_last_week)
            )
        ).scalar()
        or 0.0
    )

    spending_delta_percent = round(((spending_this_week - spending_last_week) / spending_last_week) * 100, 1) if spending_last_week > 0 else None

    # Logs submitted
    logs_this_week = (
        await db.execute(select(func.count(DailyLog.id)).where(DailyLog.project_id.in_(project_ids)).where(DailyLog.log_date >= start_of_week))
    ).scalar() or 0

    logs_last_week = (
        await db.execute(
            select(func.count(DailyLog.id))
            .where(DailyLog.project_id.in_(project_ids))
            .where(DailyLog.log_date >= start_of_last_week)
            .where(DailyLog.log_date <= end_of_last_week)
        )
    ).scalar() or 0

    # Attendance rate
    avg_hours_this_week = float(
        (
            await db.execute(
                select(func.avg(Attendance.hours_worked))
                .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
                .where(DailyLog.project_id.in_(project_ids))
                .where(DailyLog.log_date >= start_of_week)
            )
        ).scalar()
        or 0.0
    )

    avg_hours_last_week = float(
        (
            await db.execute(
                select(func.avg(Attendance.hours_worked))
                .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
                .where(DailyLog.project_id.in_(project_ids))
                .where(DailyLog.log_date >= start_of_last_week)
                .where(DailyLog.log_date <= end_of_last_week)
            )
        ).scalar()
        or 0.0
    )

    logger.debug(
        f"DASHBOARD_DELTAS | project_ids={project_ids} | incidents_delta={incidents_this_week - incidents_last_week} | spending_delta_pct={spending_delta_percent} | logs_delta={logs_this_week - logs_last_week} | attendance_delta={round(avg_hours_this_week - avg_hours_last_week, 2)}"
    )

    return {
        "incidents_this_week_delta": incidents_this_week - incidents_last_week,
        "total_spending_delta_percent": spending_delta_percent,
        "logs_submitted_delta": logs_this_week - logs_last_week,
        "attendance_rate_delta": round(avg_hours_this_week - avg_hours_last_week, 2),
    }


async def _get_material_trends(db: AsyncSession, project_ids: list[int], limit_weeks: int | None = 8) -> list[MaterialWeeklyTrend]:
    if not project_ids:
        return []

    if limit_weeks is not None:
        # Aggregate mode: group by week, scoped to last N weeks
        today = date.today()
        current_week_start = today - timedelta(days=today.weekday())
        cutoff_date = current_week_start - timedelta(weeks=limit_weeks - 1)
        week_start = func.date_trunc("week", DailyLog.log_date).label("week_start")
        rows = (
            await db.execute(
                select(
                    week_start,
                    Material.name,
                    func.sum(Material.total_cost).label("total_cost"),
                )
                .join(DailyLog, DailyLog.id == Material.daily_log_id)
                .where(DailyLog.project_id.in_(project_ids))
                .where(DailyLog.log_date >= cutoff_date)
                .where(DailyLog.log_date <= today)
                .group_by(week_start, Material.name)
                .order_by(week_start)
            )
        ).all()
        logger.debug(f"MATERIAL_TRENDS | project_ids={project_ids} | limit_weeks={limit_weeks} | rows={len(rows)}")
        return [
            MaterialWeeklyTrend(
                week=week_start.strftime("%Y-%m-%d"),
                material_name=name,
                total_cost=float(cost),
            )
            for week_start, name, cost in rows
        ]

    # All-time mode: one aggregated total per material, no time grouping
    rows = (
        await db.execute(
            select(
                Material.name,
                func.sum(Material.total_cost).label("total_cost"),
            )
            .join(DailyLog, DailyLog.id == Material.daily_log_id)
            .where(DailyLog.project_id.in_(project_ids))
            .group_by(Material.name)
            .order_by(func.sum(Material.total_cost).desc())
        )
    ).all()
    logger.debug(f"MATERIAL_TRENDS | project_ids={project_ids} | limit_weeks=None (all-time) | rows={len(rows)}")
    return [
        MaterialWeeklyTrend(
            week=None,
            material_name=name,
            total_cost=float(cost),
        )
        for name, cost in rows
    ]


async def get_owner_dashboard(db: AsyncSession) -> OwnerDashboard:
    cache_key = "dashboard:owner"
    cached = await get_cache(cache_key)
    if cached:
        return OwnerDashboard.model_validate(cached)
    # Total active projects
    active_projects = (await db.execute(select(Project).where(Project.status == "Active"))).scalars().all()

    # Budget vs actual spending per project
    project_summaries = []
    total_spending = 0.0

    for project in active_projects:
        actual = float(
            (
                await db.execute(
                    select(func.sum(Material.total_cost))
                    .join(DailyLog, DailyLog.id == Material.daily_log_id)
                    .where(DailyLog.project_id == project.id)
                )
            ).scalar()
            or 0.0
        )

        total_spending += actual
        is_over = actual > float(project.total_budget)

        project_summaries.append(
            ProjectBudgetSummary(
                project_id=project.id,
                project_name=project.name,
                total_budget=float(project.total_budget),
                actual_spending=actual,
                is_over_budget=is_over,
            )
        )

    over_budget = [p for p in project_summaries if p.is_over_budget]

    # Total active workers
    total_workers = (
        await db.execute(select(func.count(User.id)).join(User.role).where(Role.name == "site_worker").where(User.is_active))
    ).scalar() or 0

    # Total material cost
    total_material_cost = (await db.execute(select(func.sum(Material.total_cost)))).scalar() or 0.0
    # Incidents this week (active projects only)
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    active_project_ids = [p.id for p in active_projects]
    incidents_this_week = (
        await db.execute(
            select(func.count(Incident.id))
            .join(DailyLog, DailyLog.id == Incident.daily_log_id)
            .where(DailyLog.project_id.in_(active_project_ids))
            .where(DailyLog.log_date >= start_of_week)
        )
    ).scalar() or 0

    # Active projects last month delta
    end_of_last_month = today.replace(day=1) - timedelta(days=1)
    active_projects_last_month = (
        await db.execute(select(func.count(Project.id)).where(Project.status == "Active").where(Project.start_date <= end_of_last_month))
    ).scalar() or 0

    # Workers last week delta
    total_workers_last_week = (
        await db.execute(select(func.count(User.id)).join(User.role).where(Role.name == "site_worker").where(User.is_active))
    ).scalar() or 0

    deltas = await _get_dashboard_deltas(db=db, project_ids=active_project_ids)
    material_trends = await _get_material_trends(db=db, project_ids=active_project_ids)
    logger.info(
        f"OWNER_DASHBOARD | GET | role=owner | active_projects={len(active_projects)} | over_budget={len(over_budget)} | incidents_this_week={incidents_this_week}"
    )
    result = OwnerDashboard(
        total_active_projects=len(active_projects),
        total_budget=sum(float(p.total_budget) for p in active_projects),
        total_spending=total_spending,
        over_budget_projects=over_budget,
        all_projects_budget=project_summaries,
        material_trends=material_trends,
        total_workers_active=total_workers,
        total_material_cost=float(total_material_cost),
        incidents_this_week=incidents_this_week,
        total_active_projects_delta=len(active_projects) - active_projects_last_month,
        total_workers_active_delta=total_workers - total_workers_last_week,
        **deltas,
    )
    await set_cache(cache_key, result.model_dump(), OWNER_DASHBOARD_TTL)
    return result


async def get_manager_dashboard(project_id: int, current_user: User, db: AsyncSession) -> ProjectManagerDashboard | None:
    cache_key = f"dashboard:manager:{project_id}"
    cached = await get_cache(cache_key)
    if cached:
        return ProjectManagerDashboard.model_validate(cached)

    # Verify PM is assigned to project
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        logger.warning(f"MANAGER_DASHBOARD | project_id={project_id} | user_id={current_user.id} | status=not_found")
        return None

    current_user = (await db.execute(select(User).options(selectinload(User.role)).where(User.id == current_user.id))).scalar_one()

    if current_user.role.name != "owner":
        assigned = (
            await db.execute(
                select(ProjectAssignment).where(ProjectAssignment.project_id == project_id).where(ProjectAssignment.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        if not assigned:
            logger.warning(f"MANAGER_DASHBOARD | project_id={project_id} | user_id={current_user.id} | status=access_denied")
            return None

    # Logs submitted
    logs_count = (await db.execute(select(func.count(DailyLog.id)).where(DailyLog.project_id == project_id))).scalar() or 0

    # Attendance rate — avg hours worked per log
    avg_hours = (
        await db.execute(
            select(func.avg(Attendance.hours_worked)).join(DailyLog, DailyLog.id == Attendance.daily_log_id).where(DailyLog.project_id == project_id)
        )
    ).scalar() or 0.0

    # Material cost
    material_cost = (
        await db.execute(
            select(func.sum(Material.total_cost)).join(DailyLog, DailyLog.id == Material.daily_log_id).where(DailyLog.project_id == project_id)
        )
    ).scalar() or 0.0

    # Incidents — total is all-time (for aggregation), this-week is date-scoped (for the KPI card)
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    incidents = (
        (await db.execute(select(Incident).join(DailyLog, DailyLog.id == Incident.daily_log_id).where(DailyLog.project_id == project_id)))
        .scalars()
        .all()
    )
    open_incidents = [i for i in incidents if i.status == "Open"]
    incidents_this_week = (
        await db.execute(
            select(func.count(Incident.id))
            .join(DailyLog, DailyLog.id == Incident.daily_log_id)
            .where(DailyLog.project_id == project_id)
            .where(DailyLog.log_date >= start_of_week)
        )
    ).scalar() or 0

    # Phases
    phases = (await db.execute(select(ProjectPhase).where(ProjectPhase.project_id == project_id))).scalars().all()

    phase_summaries = []
    for phase in phases:
        phase_spending = (
            await db.execute(
                select(func.sum(Material.total_cost)).join(DailyLog, DailyLog.id == Material.daily_log_id).where(DailyLog.project_id == project_id)
            )
        ).scalar() or 0.0

        phase_summaries.append(
            PhaseBudgetSummary(
                phase_id=phase.id,
                phase_name=phase.name,
                allocated_budget=float(phase.allocated_budget),
                actual_spending=float(phase_spending),
                is_over_budget=float(phase_spending) > float(phase.allocated_budget),
            )
        )

    deltas = await _get_dashboard_deltas(db=db, project_ids=[project_id])
    material_trends = await _get_material_trends(db=db, project_ids=[project_id], limit_weeks=None)
    logger.info(f"MANAGER_DASHBOARD | GET | role=project_manager | user_id={current_user.id} | project_id={project_id}")
    result = ProjectManagerDashboard(
        project_id=project.id,
        project_name=project.name,
        logs_submitted=logs_count,
        attendance_rate=round(float(avg_hours), 2),
        total_material_cost=float(material_cost),
        total_incidents=len(incidents),
        incidents_this_week=incidents_this_week,
        open_incidents=len(open_incidents),
        phases=phase_summaries,
        material_trends=material_trends,
        **deltas,
    )
    cache_key = f"dashboard:manager:{project_id}"
    await set_cache(cache_key, result.model_dump(), MANAGER_DASHBOARD_TTL)
    return result


async def get_manager_aggregate_dashboard(current_user: User, db: AsyncSession) -> ProjectManagerAggregateDashboard:
    cache_key = f"dashboard:manager:aggregate:{current_user.id}"
    cached = await get_cache(cache_key)
    if cached:
        return ProjectManagerAggregateDashboard.model_validate(cached)

    # Aggregate KPIs are scoped to active projects only (mirrors get_owner_dashboard)
    assignments = (
        (
            await db.execute(
                select(ProjectAssignment)
                .join(Project, Project.id == ProjectAssignment.project_id)
                .where(ProjectAssignment.user_id == current_user.id)
                .where(Project.status == "Active")
            )
        )
        .scalars()
        .all()
    )
    active_project_ids = [a.project_id for a in assignments]
    project_ids = active_project_ids  # kept for compatibility with downstream queries in this function

    if not project_ids:
        return ProjectManagerAggregateDashboard(
            total_logs_submitted=0,
            total_budget=0.0,
            total_spending=0.0,
            average_attendance_rate=0.0,
            incidents_this_week=0,
            over_budget_projects=[],
            all_projects_budget=[],
            material_trends=[],
        )

    # Total logs submitted across all assigned projects
    total_logs = (await db.execute(select(func.count(DailyLog.id)).where(DailyLog.project_id.in_(project_ids)))).scalar() or 0

    # Budget and spending per project
    projects = (await db.execute(select(Project).where(Project.id.in_(project_ids)))).scalars().all()

    total_budget = sum(float(p.total_budget) for p in projects)

    project_summaries = []
    total_spending = 0.0
    for project in projects:
        actual = float(
            (
                await db.execute(
                    select(func.sum(Material.total_cost))
                    .join(DailyLog, DailyLog.id == Material.daily_log_id)
                    .where(DailyLog.project_id == project.id)
                )
            ).scalar()
            or 0.0
        )
        total_spending += actual
        is_over = actual > float(project.total_budget)
        project_summaries.append(
            ProjectBudgetSummary(
                project_id=project.id,
                project_name=project.name,
                total_budget=float(project.total_budget),
                actual_spending=actual,
                is_over_budget=is_over,
            )
        )
    over_budget = [p for p in project_summaries if p.is_over_budget]

    # Average attendance rate across all assigned projects
    avg_hours = (
        await db.execute(
            select(func.avg(Attendance.hours_worked))
            .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
            .where(DailyLog.project_id.in_(project_ids))
        )
    ).scalar() or 0.0

    # Incidents this week
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    incidents_this_week = (
        await db.execute(
            select(func.count(Incident.id))
            .join(DailyLog, DailyLog.id == Incident.daily_log_id)
            .where(DailyLog.project_id.in_(project_ids))
            .where(DailyLog.log_date >= start_of_week)
        )
    ).scalar() or 0

    deltas = await _get_dashboard_deltas(db=db, project_ids=project_ids)
    material_trends = await _get_material_trends(db=db, project_ids=project_ids)
    logger.info(f"MANAGER_AGGREGATE_DASHBOARD | GET | role=project_manager | user_id={current_user.id} | assigned_projects={len(project_ids)}")
    result = ProjectManagerAggregateDashboard(
        total_logs_submitted=total_logs,
        total_budget=total_budget,
        total_spending=total_spending,
        average_attendance_rate=round(float(avg_hours), 2),
        incidents_this_week=incidents_this_week,
        over_budget_projects=over_budget,
        all_projects_budget=project_summaries,
        material_trends=material_trends,
        total_logs_submitted_delta=deltas["logs_submitted_delta"],
        average_attendance_rate_delta=deltas["attendance_rate_delta"],
        total_spending_delta_percent=deltas["total_spending_delta_percent"],
        incidents_this_week_delta=deltas["incidents_this_week_delta"],
    )
    await set_cache(cache_key, result.model_dump(), MANAGER_DASHBOARD_TTL)
    return result


async def get_worker_dashboard(current_user: User, db: AsyncSession) -> WorkerDashboard:
    # Get assigned project
    assignment = (
        (await db.execute(select(WorkerAssignment).where(WorkerAssignment.user_id == current_user.id).order_by(WorkerAssignment.id.desc())))
        .scalars()
        .first()
    )
    project_name = None
    project_id = None
    if assignment:
        project = (await db.execute(select(Project).where(Project.id == assignment.project_id))).scalar_one_or_none()
        project_name = project.name if project else None
        project_id = assignment.project_id

    # Total logs they appear in
    total_logs = (await db.execute(select(func.count(Attendance.id)).where(Attendance.worker_id == current_user.id))).scalar() or 0

    # Total hours worked
    total_hours = (await db.execute(select(func.sum(Attendance.hours_worked)).where(Attendance.worker_id == current_user.id))).scalar() or 0.0

    # Current shift log — today's log for assigned project
    current_shift_log = None
    if project_id:
        log = (
            await db.execute(select(DailyLog).where(DailyLog.project_id == project_id).where(DailyLog.log_date == date.today()))
        ).scalar_one_or_none()
        if log:
            current_shift_log = CurrentShiftLog(
                log_id=log.id,
                log_date=str(log.log_date),
                work_accomplished=log.work_accomplished,
                weather_condition=log.weather_condition,
            )
            logger.info(f"WORKER_DASHBOARD | worker_id={current_user.id} | current_shift_log={log.id}")
        else:
            logger.info(f"WORKER_DASHBOARD | worker_id={current_user.id} | current_shift_log=none")

    logger.info(f"WORKER_DASHBOARD | worker_id={current_user.id} | total_logs={total_logs} | total_hours={total_hours}")
    return WorkerDashboard(
        worker_id=current_user.id,
        worker_name=f"{current_user.first_name} {current_user.last_name}",
        assigned_project=project_name,
        total_logs=total_logs,
        total_hours_worked=float(total_hours),
        current_shift_log=current_shift_log,
    )
