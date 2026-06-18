import logging

from sqlalchemy.future import select

from app.core.celery import celery_app
from app.core.celery_db import make_celery_sync_session
from app.models.project import Project
from app.services import report

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_weekly_report")
def generate_weekly_report(project_id: int, generated_by: int):
    logger.info(f"REPORT | project_id={project_id} | user_id={generated_by} | task=queued")
    _generate_weekly_report(project_id, generated_by)


def _generate_weekly_report(project_id: int, generated_by: int):
    with make_celery_sync_session()() as db:
        try:
            result = report.generate_report_sync(project_id, generated_by, db)
            if result:
                import redis

                from app.core.settings import settings

                r = redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)
                r.delete(f"report:list:{project_id}")
                logger.info(f"REPORT | project_id={project_id} | cache=invalidated")
            logger.info(f"REPORT | project_id={project_id} | user_id={generated_by} | status=done")
        except Exception as e:
            logger.error(f"REPORT | project_id={project_id} | user_id={generated_by} | status=failed | reason={str(e)}")


@celery_app.task(name="trigger_all_weekly_reports")
def trigger_all_weekly_reports():
    logger.info("REPORT_TRIGGER | task=started")
    _trigger_all_weekly_reports()


def _trigger_all_weekly_reports():
    with make_celery_sync_session()() as db:
        projects = db.execute(select(Project).where(Project.status == "Active")).scalars().all()
        count = len(projects)
        for project in projects:
            generate_weekly_report.delay(project.id, project.owner_id)
            logger.info(f"REPORT_TRIGGER | project_id={project.id} | status=queued")
        logger.info(f"REPORT_TRIGGER | total_queued={count} | status=done")
