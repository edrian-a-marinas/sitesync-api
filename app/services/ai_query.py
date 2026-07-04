import logging
import re
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.settings import settings
from app.models.ai_query import AIQuery
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.equipment import Equipment
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment, ProjectPhase, WorkerAssignment
from app.models.user import User
from app.schemas.ai_query import AIQueryRequest

logger = logging.getLogger(__name__)


def _format_currency(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}\u20b1{abs(value):,.2f}"


# ==================== RAG ====================
_ROW_LIMIT = settings.ROW_LIMIT

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "materials": [
        "material",
        "materials",
        "cement",
        "steel",
        "sand",
        "gravel",
        "lumber",
        "concrete",
        "rebar",
        "paint",
        "tiles",
        "pipes",
        "wire",
        "consumed",
        "consumption",
        "supply",
        "supplies",
        "cost",
        "spent",
        "spending",
        "expense",
        "expenses",
        "purchase",
        "purchased",
    ],
    "attendance": [
        "attendance",
        "worker",
        "workers",
        "workforce",
        "present",
        "absent",
        "hours",
        "labor",
        "labour",
        "manpower",
        "headcount",
        "staff",
        "worked",
    ],
    "incidents": [
        "incident",
        "incidents",
        "accident",
        "accidents",
        "injury",
        "injuries",
        "hazard",
        "hazards",
        "safety",
        "severity",
        "open",
        "resolved",
    ],
    "budget": [
        "budget",
        "overrun",
        "overbudget",
        "over budget",
        "underspent",
        "actual",
        "spending",
        "cost",
        "costs",
        "financial",
        "allocated",
        "allocation",
        "expense",
        "expenses",
    ],
    "phases": [
        "phase",
        "phases",
        "foundation",
        "structure",
        "finishing",
        "stage",
        "stages",
        "progress",
        "started",
        "completed",
        "not started",
        "in progress",
    ],
    "personnel": [
        "pm",
        "project manager",
        "project managers",
        "manager",
        "managers",
        "supervisor",
        "supervisors",
        "in charge",
        "assigned",
        "who is managing",
        "who manages",
    ],
    "equipment": [
        "equipment",
        "machine",
        "machines",
        "machinery",
        "tool",
        "tools",
        "excavator",
        "crane",
        "broken",
        "needs repair",
        "condition",
        "maintenance",
    ],
}


def classify_intent(question: str) -> list[str]:
    lowered = question.lower()

    def _matches(keyword: str) -> bool:
        if len(keyword) <= 3:
            # Short keywords (e.g. "pm") must match as a whole word to avoid
            # false positives like "pm" inside "equipment"
            return re.search(rf"\b{re.escape(keyword)}\b", lowered) is not None
        return keyword in lowered

    matched = [intent for intent, keywords in _INTENT_KEYWORDS.items() if any(_matches(kw) for kw in keywords)]
    if not matched:
        matched.append("general")
    else:
        matched.append("general")
    logger.info(f"AI_QUERY | classify_intent | intents={matched}")
    return matched


async def _retrieve_materials(db: AsyncSession, project_id: int | None) -> str:
    stmt = (
        select(
            Project.name.label("project_name"),
            DailyLog.log_date,
            Material.name.label("material_name"),
            Material.quantity,
            Material.unit,
            Material.unit_cost,
            Material.total_cost,
        )
        .join(DailyLog, DailyLog.id == Material.daily_log_id)
        .join(Project, Project.id == DailyLog.project_id)
        .order_by(DailyLog.log_date.desc())
        .limit(_ROW_LIMIT)
    )
    if project_id:
        stmt = stmt.where(DailyLog.project_id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    rows = (await db.execute(stmt)).all()
    if not rows:
        return "MATERIALS: No material records found.\n"
    lines = ["MATERIALS (recent entries):"]
    for r in rows:
        lines.append(
            f"  [{r.log_date}] {r.project_name} | {r.material_name} | "
            f"qty={float(r.quantity)} {r.unit} | unit_cost={_format_currency(float(r.unit_cost))} | total_cost={_format_currency(float(r.total_cost))}"
        )
    return "\n".join(lines) + "\n"


async def _retrieve_attendance(db: AsyncSession, project_id: int | None) -> str:
    stmt = (
        select(
            Project.name.label("project_name"),
            DailyLog.log_date,
            func.count(Attendance.id).label("worker_count"),
            func.sum(Attendance.hours_worked).label("total_hours"),
        )
        .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
        .join(Project, Project.id == DailyLog.project_id)
        .group_by(Project.name, DailyLog.log_date)
        .order_by(DailyLog.log_date.desc())
        .limit(_ROW_LIMIT)
    )
    if project_id:
        stmt = stmt.where(DailyLog.project_id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    rows = (await db.execute(stmt)).all()
    if not rows:
        return "ATTENDANCE: No attendance records found.\n"
    lines = ["ATTENDANCE (recent entries):"]
    for r in rows:
        lines.append(f"  [{r.log_date}] {r.project_name} | workers_present={r.worker_count} | total_hours={float(r.total_hours or 0)}")
    return "\n".join(lines) + "\n"


async def _retrieve_incidents(db: AsyncSession, project_id: int | None) -> str:
    stmt = (
        select(
            Project.name.label("project_name"),
            DailyLog.log_date,
            Incident.description,
            Incident.severity,
            Incident.status,
        )
        .join(DailyLog, DailyLog.id == Incident.daily_log_id)
        .join(Project, Project.id == DailyLog.project_id)
        .order_by(DailyLog.log_date.desc())
        .limit(_ROW_LIMIT)
    )
    if project_id:
        stmt = stmt.where(DailyLog.project_id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    rows = (await db.execute(stmt)).all()
    if not rows:
        return "INCIDENTS: No incident records found.\n"
    lines = ["INCIDENTS (recent entries):"]
    for r in rows:
        lines.append(f"  [{r.log_date}] {r.project_name} | severity={r.severity} | status={r.status} | description={r.description}")
    return "\n".join(lines) + "\n"


async def _retrieve_budget(db: AsyncSession, project_id: int | None) -> str:
    stmt = select(Project)
    if project_id:
        stmt = stmt.where(Project.id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    projects = (await db.execute(stmt)).scalars().all()
    if not projects:
        return "BUDGET: No project records found.\n"
    rows = []
    for project in projects:
        actual_spend = float(
            (
                await db.execute(
                    select(func.sum(Material.total_cost))
                    .join(DailyLog, DailyLog.id == Material.daily_log_id)
                    .where(DailyLog.project_id == project.id)
                )
            ).scalar()
            or 0.0
        )
        budget = float(project.total_budget)
        variance = budget - actual_spend
        over_under = "OVER BUDGET" if variance < 0 else "under budget"
        budget_used_percent = (actual_spend / budget * 100) if budget > 0 else 0.0
        rows.append((budget_used_percent, project, budget, actual_spend, variance, over_under))
    # Sort by budget_used_percent descending — highest % used = highest overrun risk, listed first
    rows.sort(key=lambda r: r[0], reverse=True)
    lines = ["BUDGET (sorted by overrun risk, highest first):"]
    for budget_used_percent, project, budget, actual_spend, variance, over_under in rows:
        lines.append(
            f"  {project.name} | budget={_format_currency(budget)} | actual_spend={_format_currency(actual_spend)} | "
            f"variance={_format_currency(variance)} | budget_used_percent={budget_used_percent:.1f}% | {over_under} | status={project.status}"
        )
    return "\n".join(lines) + "\n"


async def _retrieve_phases(db: AsyncSession, project_id: int | None) -> str:
    stmt = (
        select(
            Project.name.label("project_name"),
            ProjectPhase.name.label("phase_name"),
            ProjectPhase.allocated_budget,
            ProjectPhase.status,
        )
        .join(Project, Project.id == ProjectPhase.project_id)
        .order_by(Project.name, ProjectPhase.id)
    )
    if project_id:
        stmt = stmt.where(ProjectPhase.project_id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    rows = (await db.execute(stmt)).all()
    if not rows:
        return "PHASES: No phase records found.\n"
    lines = ["PHASES:"]
    for r in rows:
        lines.append(
            f"  {r.project_name} | phase={r.phase_name} | allocated_budget={_format_currency(float(r.allocated_budget))} | status={r.status}"
        )
    return "\n".join(lines) + "\n"


async def _retrieve_personnel(db: AsyncSession, project_id: int | None) -> str:
    manager_stmt = (
        select(
            Project.name.label("project_name"),
            User.first_name,
            User.last_name,
        )
        .join(ProjectAssignment, ProjectAssignment.project_id == Project.id)
        .join(User, User.id == ProjectAssignment.user_id)
        .order_by(Project.name)
    )
    worker_stmt = (
        select(
            Project.name.label("project_name"),
            func.count(WorkerAssignment.user_id).label("worker_count"),
        )
        .join(WorkerAssignment, WorkerAssignment.project_id == Project.id)
        .group_by(Project.name)
    )
    if project_id:
        manager_stmt = manager_stmt.where(Project.id == project_id)
        worker_stmt = worker_stmt.where(Project.id == project_id)
    else:
        manager_stmt = manager_stmt.where(Project.status == "Active")
        worker_stmt = worker_stmt.where(Project.status == "Active")
    manager_rows = (await db.execute(manager_stmt)).all()
    worker_rows = (await db.execute(worker_stmt)).all()
    if not manager_rows and not worker_rows:
        return "PERSONNEL: None assigned\n"
    managers_by_project: dict[str, list[str]] = {}
    for r in manager_rows:
        managers_by_project.setdefault(r.project_name, []).append(f"{r.first_name} {r.last_name}")
    workers_by_project = {r.project_name: r.worker_count for r in worker_rows}
    project_names = sorted(set(managers_by_project) | set(workers_by_project))
    lines = ["PERSONNEL (assigned project managers and worker counts):"]
    for name in project_names:
        managers = ", ".join(managers_by_project.get(name, [])) or "None assigned"
        worker_count = workers_by_project.get(name, 0)
        lines.append(f"  {name} | project_managers={managers} | worker_count={worker_count}")
    return "\n".join(lines) + "\n"


async def _retrieve_equipment(db: AsyncSession, project_id: int | None) -> str:
    stmt = (
        select(
            Project.name.label("project_name"),
            DailyLog.log_date,
            Equipment.name.label("equipment_name"),
            Equipment.quantity,
            Equipment.condition,
        )
        .join(DailyLog, DailyLog.id == Equipment.daily_log_id)
        .join(Project, Project.id == DailyLog.project_id)
        .order_by(DailyLog.log_date.desc())
        .limit(_ROW_LIMIT)
    )
    if project_id:
        stmt = stmt.where(DailyLog.project_id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    rows = (await db.execute(stmt)).all()
    if not rows:
        return "EQUIPMENT: No equipment records found.\n"
    lines = ["EQUIPMENT (recent entries):"]
    for r in rows:
        lines.append(f"  [{r.log_date}] {r.project_name} | {r.equipment_name} | qty={r.quantity} | condition={r.condition or 'Not specified'}")
    return "\n".join(lines) + "\n"


async def _retrieve_general(db: AsyncSession, project_id: int | None) -> str:
    stmt = select(Project)
    if project_id:
        stmt = stmt.where(Project.id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    projects = (await db.execute(stmt)).scalars().all()
    if not projects:
        return "PROJECTS: No projects found.\n"
    lines = ["PROJECTS (summary):"]
    for project in projects:
        total_material_cost = float(
            (
                await db.execute(
                    select(func.sum(Material.total_cost))
                    .join(DailyLog, DailyLog.id == Material.daily_log_id)
                    .where(DailyLog.project_id == project.id)
                )
            ).scalar()
            or 0.0
        )
        total_hours = float(
            (
                await db.execute(
                    select(func.sum(Attendance.hours_worked))
                    .join(DailyLog, DailyLog.id == Attendance.daily_log_id)
                    .where(DailyLog.project_id == project.id)
                )
            ).scalar()
            or 0.0
        )
        incident_count = (
            await db.execute(
                select(func.count(Incident.id)).join(DailyLog, DailyLog.id == Incident.daily_log_id).where(DailyLog.project_id == project.id)
            )
        ).scalar() or 0
        open_incidents = (
            await db.execute(
                select(func.count(Incident.id))
                .join(DailyLog, DailyLog.id == Incident.daily_log_id)
                .where(DailyLog.project_id == project.id)
                .where(Incident.status == "Open")
            )
        ).scalar() or 0
        lines.append(
            f"  {project.name} | location={project.location} | budget={_format_currency(float(project.total_budget))} | "
            f"status={project.status} | start={project.start_date} | target_end={project.target_end_date} | "
            f"total_material_cost={_format_currency(total_material_cost)} | total_hours_worked={total_hours} | "
            f"total_incidents={incident_count} | open_incidents={open_incidents}"
        )
    return "\n".join(lines) + "\n"


_INTENT_HANDLERS = {
    "materials": _retrieve_materials,
    "attendance": _retrieve_attendance,
    "incidents": _retrieve_incidents,
    "budget": _retrieve_budget,
    "phases": _retrieve_phases,
    "personnel": _retrieve_personnel,
    "equipment": _retrieve_equipment,
    "general": _retrieve_general,
}


async def retrieve_context(db: AsyncSession, question: str, project_id: int | None) -> str:
    intents = classify_intent(question)
    context_parts: list[str] = []
    for intent in intents:
        handler = _INTENT_HANDLERS.get(intent)
        if handler:
            try:
                block = await handler(db, project_id)
                context_parts.append(block)
            except Exception as e:
                logger.error(f"AI_QUERY | retrieve_context | intent={intent} | error={str(e)}")
                context_parts.append(f"{intent.upper()}: Retrieval failed.\n")
    return "\n".join(context_parts)


async def create_query(data: AIQueryRequest, current_user: User, db: AsyncSession) -> AIQuery:
    query = AIQuery(
        user_id=current_user.id,
        project_id=data.project_id,
        question=data.question,
        status="Pending",
    )
    db.add(query)
    await db.commit()
    await db.refresh(query)
    logger.info(f"AI_QUERY | query_id={query.id} | user_id={current_user.id} | status=pending")
    return query


def log_queue_failure(task_name: str, query_id: int, current_user: User) -> None:
    logger.error(
        f"AI_QUERY | task={task_name} | query_id={query_id} | user_id={current_user.id} | "
        f"role_id={current_user.role_id} | status=failed | reason=queue unreachable"
    )


async def get_query(query_id: int, current_user: User, db: AsyncSession) -> AIQuery | None:
    query = (await db.execute(select(AIQuery).where(AIQuery.id == query_id).where(AIQuery.user_id == current_user.id))).scalar_one_or_none()
    if not query:
        return None

    # Auto-expire stale pending queries
    if query.status == "Pending" and query.created_at:
        age_minutes = (datetime.now(timezone.utc) - query.created_at).total_seconds() / 60
        if age_minutes > settings.PENDING_TIMEOUT_MINUTES:
            query.status = "Failed"
            query.answer = "TIMEOUT"
            await db.commit()
            await db.refresh(query)
            logger.warning(
                f"AI_QUERY | GET | query_id={query_id} | user_id={current_user.id} | role={current_user.role_id} | status=auto_expired | age_minutes={age_minutes:.1f}"
            )

    logger.info(
        f"AI_QUERY | GET | query_id={query_id} | user_id={current_user.id} | role={current_user.role_id} | status={query.status} | has_answer={query.answer is not None}"
    )
    return query


async def get_queries(current_user: User, db: AsyncSession, skip: int = 0, limit: int = 10) -> list[AIQuery]:
    result = await db.execute(select(AIQuery).where(AIQuery.user_id == current_user.id).order_by(AIQuery.created_at.desc()).offset(skip).limit(limit))
    return result.scalars().all()


async def delete_query(query_id: int, current_user: User, db: AsyncSession) -> bool:
    query = (await db.execute(select(AIQuery).where(AIQuery.id == query_id).where(AIQuery.user_id == current_user.id))).scalar_one_or_none()
    if not query:
        logger.warning(f"AI_QUERY | DELETE | query_id={query_id} | user_id={current_user.id} | role=owner | status=not_found")
        return False
    await db.delete(query)
    await db.commit()
    logger.info(f"AI_QUERY | DELETE | query_id={query_id} | user_id={current_user.id} | role=owner | status=deleted")
    return True


async def delete_all_queries(current_user: User, db: AsyncSession) -> int:
    result = await db.execute(select(AIQuery).where(AIQuery.user_id == current_user.id))
    queries = result.scalars().all()
    count = len(queries)
    for query in queries:
        await db.delete(query)
    await db.commit()
    logger.info(f"AI_QUERY | DELETE_ALL | user_id={current_user.id} | role=owner | status=deleted | count={count}")
    return count
