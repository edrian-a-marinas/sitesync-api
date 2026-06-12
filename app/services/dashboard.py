import logging

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.cache import get_cache, set_cache
from app.core.settings import settings
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment, ProjectPhase, WorkerAssignment
from app.models.user import User
from app.schemas.dashboard import OwnerDashboard, PhaseBudgetSummary, ProjectBudgetSummary, ProjectManagerDashboard, WorkerDashboard

logger = logging.getLogger(__name__)


OWNER_DASHBOARD_TTL = settings.OWNER_DASHBOARD_TTL
MANAGER_DASHBOARD_TTL = settings.MANAGER_DASHBOARD_TTL


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
    total_workers = (await db.execute(select(func.count(User.id)).where(User.role_id == 3).where(User.is_active))).scalar() or 0

    # Total material cost
    total_material_cost = (await db.execute(select(func.sum(Material.total_cost)))).scalar() or 0.0

    logger.info(f"OWNER_DASHBOARD | active_projects={len(active_projects)} | over_budget={len(over_budget)}")
    result = OwnerDashboard(
        total_active_projects=len(active_projects),
        total_budget=sum(float(p.total_budget) for p in active_projects),
        total_spending=total_spending,
        over_budget_projects=over_budget,
        total_workers_active=total_workers,
        total_material_cost=float(total_material_cost),
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
    if current_user.role_id != 1:
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

    # Incidents
    incidents = (
        (await db.execute(select(Incident).join(DailyLog, DailyLog.id == Incident.daily_log_id).where(DailyLog.project_id == project_id)))
        .scalars()
        .all()
    )

    open_incidents = [i for i in incidents if i.status == "Open"]

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

    logger.info(f"MANAGER_DASHBOARD | project_id={project_id} | user_id={current_user.id}")
    result = ProjectManagerDashboard(
        project_id=project.id,
        project_name=project.name,
        logs_submitted=logs_count,
        attendance_rate=round(float(avg_hours), 2),
        total_material_cost=float(material_cost),
        total_incidents=len(incidents),
        open_incidents=len(open_incidents),
        phases=phase_summaries,
    )
    cache_key = f"dashboard:manager:{project_id}"
    await set_cache(cache_key, result.model_dump(), MANAGER_DASHBOARD_TTL)
    return result


async def get_worker_dashboard(current_user: User, db: AsyncSession) -> WorkerDashboard:
    # Get assigned project
    assignment = (await db.execute(select(WorkerAssignment).where(WorkerAssignment.user_id == current_user.id))).scalar_one_or_none()

    project_name = None
    if assignment:
        project = (await db.execute(select(Project).where(Project.id == assignment.project_id))).scalar_one_or_none()
        project_name = project.name if project else None

    # Total logs they appear in
    total_logs = (await db.execute(select(func.count(Attendance.id)).where(Attendance.worker_id == current_user.id))).scalar() or 0

    # Total hours worked
    total_hours = (await db.execute(select(func.sum(Attendance.hours_worked)).where(Attendance.worker_id == current_user.id))).scalar() or 0.0

    logger.info(f"WORKER_DASHBOARD | worker_id={current_user.id}")

    return WorkerDashboard(
        worker_id=current_user.id,
        worker_name=f"{current_user.first_name} {current_user.last_name}",
        assigned_project=project_name,
        total_logs=total_logs,
        total_hours_worked=float(total_hours),
    )
