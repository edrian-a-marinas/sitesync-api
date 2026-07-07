import logging
from datetime import datetime, timezone

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.settings import settings
from app.models.ai_query import AIQuery
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.embedding import DailyLogEmbedding
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project
from app.models.user import User
from app.schemas.ai_query import AIQueryRequest
from app.services.embedding import generate_embedding

logger = logging.getLogger(__name__)


# ==================== RAG ====================
class DailyLogEmbeddingRetriever(BaseRetriever):
    """Custom LangChain retriever backed by the existing daily_log_embeddings table (pgvector cosine similarity)."""

    db: AsyncSession
    project_id: int | None = None
    k: int = 5

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        vector = generate_embedding(query)
        stmt = select(DailyLogEmbedding).order_by(DailyLogEmbedding.embedding.cosine_distance(vector)).limit(self.k)
        if self.project_id:
            stmt = stmt.where(DailyLogEmbedding.project_id == self.project_id)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [Document(page_content=r.content_text, metadata={"daily_log_id": r.daily_log_id, "project_id": r.project_id}) for r in rows]

    def _get_relevant_documents(self, query: str) -> list[Document]:
        raise NotImplementedError("Use async retrieval via ainvoke/aget_relevant_documents")


async def _retrieve_project_summary(db: AsyncSession, project_id: int | None) -> str:
    stmt = select(Project)
    if project_id:
        stmt = stmt.where(Project.id == project_id)
    else:
        stmt = stmt.where(Project.status == "Active")
    projects = (await db.execute(stmt)).scalars().all()
    if not projects:
        return "PROJECT_SUMMARY: No project records found.\n"
    lines = ["PROJECT_SUMMARY (overview stats per project):"]
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
        budget = float(project.total_budget)
        variance = budget - total_material_cost
        budget_used_percent = (total_material_cost / budget * 100) if budget > 0 else 0.0
        lines.append(
            f"  {project.name} | location={project.location} | status={project.status} | "
            f"budget=\u20b1{budget:,.2f} | spent=\u20b1{total_material_cost:,.2f} | "
            f"variance=\u20b1{variance:,.2f} | budget_used_percent={budget_used_percent:.1f}% | "
            f"total_hours_worked={total_hours} | total_incidents={incident_count} | open_incidents={open_incidents} | "
            f"start={project.start_date} | target_end={project.target_end_date}"
        )
    return "\n".join(lines) + "\n"


async def retrieve_context(db: AsyncSession, question: str, project_id: int | None) -> str:
    context_parts: list[str] = []
    retriever = DailyLogEmbeddingRetriever(db=db, project_id=project_id, k=5)
    try:
        docs = await retriever.ainvoke(question)
        if docs:
            lines = ["SEMANTIC_MATCHES (related daily logs by meaning):"]
            for doc in docs:
                lines.append(f"  [daily_log_id={doc.metadata['daily_log_id']}] {doc.page_content}")
            context_parts.append("\n".join(lines) + "\n")
        else:
            context_parts.append("SEMANTIC_MATCHES: No related daily logs found.\n")
    except Exception as e:
        logger.error(f"AI_QUERY | retrieve_context | semantic | error={str(e)}")
        context_parts.append("SEMANTIC_MATCHES: Retrieval failed.\n")
    try:
        context_parts.append(await _retrieve_project_summary(db, project_id))
    except Exception as e:
        logger.error(f"AI_QUERY | retrieve_context | project_summary | error={str(e)}")
        context_parts.append("PROJECT_SUMMARY: Retrieval failed.\n")
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
