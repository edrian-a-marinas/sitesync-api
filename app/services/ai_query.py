import logging
import re

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.ai_query import AIQuery
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project
from app.models.user import User
from app.schemas.ai_query import AIQueryRequest

logger = logging.getLogger(__name__)


def extract_keywords(message: str) -> list[str]:
    stopwords = {
        "how",
        "much",
        "have",
        "i",
        "spent",
        "on",
        "in",
        "the",
        "my",
        "a",
        "an",
        "is",
        "are",
        "was",
        "what",
        "when",
        "which",
        "who",
        "where",
        "show",
        "me",
        "all",
        "for",
        "from",
        "to",
        "of",
        "and",
        "or",
        "do",
        "did",
        "does",
        "can",
        "could",
        "would",
        "total",
        "amount",
        "project",
        "projects",
        "report",
        "last",
        "this",
        "month",
        "year",
        "week",
        "day",
    }
    words = re.findall(r"[a-zA-Z0-9]+", message.lower())
    return [w for w in words if w not in stopwords and len(w) >= 3]


async def build_context(db: AsyncSession, project_id: int | None) -> str:
    context_parts = []

    if project_id:
        projects = (await db.execute(select(Project).where(Project.id == project_id))).scalars().all()
    else:
        projects = (await db.execute(select(Project))).scalars().all()

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
        incidents = (
            (await db.execute(select(Incident).join(DailyLog, DailyLog.id == Incident.daily_log_id).where(DailyLog.project_id == project.id)))
            .scalars()
            .all()
        )

        context_parts.append(
            f"Project: {project.name} | Location: {project.location} | "
            f"Budget: {float(project.total_budget)} | Status: {project.status} | "
            f"Material Cost: {total_material_cost} | Hours Worked: {total_hours} | "
            f"Total Incidents: {len(incidents)} | Open Incidents: {len([i for i in incidents if i.status == 'Open'])}"
        )

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


async def get_query(query_id: int, current_user: User, db: AsyncSession) -> AIQuery | None:
    query = (await db.execute(select(AIQuery).where(AIQuery.id == query_id).where(AIQuery.user_id == current_user.id))).scalar_one_or_none()
    return query


async def get_queries(current_user: User, db: AsyncSession) -> list[AIQuery]:
    result = await db.execute(select(AIQuery).where(AIQuery.user_id == current_user.id))
    return result.scalars().all()
