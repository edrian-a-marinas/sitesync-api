import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.future import select

from app.core.celery import celery_app
from app.database import AsyncSessionLocal
from app.models.ai_query import AIQuery
from app.models.project import Project
from app.services import report

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_weekly_report")
def generate_weekly_report(project_id: int, generated_by: int):
    logger.info(f"REPORT | project_id={project_id} | user_id={generated_by} | task=queued")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_generate_weekly_report(project_id, generated_by))
    finally:
        loop.close()


async def _generate_weekly_report(project_id: int, generated_by: int):
    async with AsyncSessionLocal() as db:
        await report.generate_report(project_id, generated_by, db)


@celery_app.task(name="trigger_all_weekly_reports")
def trigger_all_weekly_reports():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_trigger_all_weekly_reports())
    finally:
        loop.close()


async def _trigger_all_weekly_reports():
    async with AsyncSessionLocal() as db:
        projects = (await db.execute(select(Project).where(Project.status == "Active"))).scalars().all()
        for project in projects:
            generate_weekly_report.delay(project.id, project.owner_id)
            logger.info(f"REPORT_TRIGGER | project_id={project.id} | status=queued")


@celery_app.task(name="cleanup_old_ai_queries")
def cleanup_old_ai_queries():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_cleanup_old_ai_queries())
    finally:
        loop.close()


async def _cleanup_old_ai_queries():
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(AIQuery).where(AIQuery.created_at < cutoff))
            old_queries = result.scalars().all()
            count = len(old_queries)
            for query in old_queries:
                await db.delete(query)
            await db.commit()
            logger.info(f"AI_QUERY_CLEANUP | deleted={count} | cutoff={cutoff.date()}")
        except Exception as e:
            logger.error(f"AI_QUERY_CLEANUP | status=failed | reason={str(e)}")
