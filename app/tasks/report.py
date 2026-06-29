import logging

import redis
from sqlalchemy.future import select

from app.core.celery import celery_app
from app.core.celery_db import make_celery_sync_session
from app.core.settings import settings
from app.models.project import Project
from app.services import report

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_weekly_report")
def generate_weekly_report(project_id: int, generated_by: int | None, source: str = "scheduled"):
    logger.info(f"REPORT | project_id={project_id} | user_id={generated_by} | source={source} | task=queued")
    _generate_weekly_report(project_id, generated_by, source)


def _generate_weekly_report(project_id: int, generated_by: int | None, source: str = "scheduled"):
    with make_celery_sync_session()() as db:
        try:
            result = report.generate_report_sync(project_id, generated_by, db, source=source)
            if result:
                r = redis.from_url(settings.REDIS_CACHE_URL, decode_responses=True)
                keys = r.keys(f"report:list:{project_id}:*") + r.keys(f"report:exists:{project_id}:*")
                if keys:
                    r.delete(*keys)
                logger.info(f"REPORT | project_id={project_id} | cache=invalidated | keys={len(keys)}")
            logger.info(f"REPORT | project_id={project_id} | user_id={generated_by} | status=done")
        except Exception as e:
            logger.error(f"REPORT | project_id={project_id} | user_id={generated_by} | status=failed | reason={str(e)}")


@celery_app.task(name="trigger_all_weekly_reports")
def trigger_all_weekly_reports():
    logger.info("REPORT_TRIGGER | task=started")
    _trigger_all_weekly_reports()


@celery_app.task(name="cleanup_old_reports")
def cleanup_old_reports():
    logger.info("REPORT_CLEANUP | task=started")
    _cleanup_old_reports()


def _cleanup_old_reports():
    with make_celery_sync_session()() as db:
        try:
            report.cleanup_old_reports_sync(db)
        except Exception as e:
            logger.error(f"REPORT_CLEANUP | status=failed | reason={str(e)}")


def _trigger_all_weekly_reports():
    with make_celery_sync_session()() as db:
        projects = db.execute(select(Project).where(Project.status == "Active")).scalars().all()
        count = len(projects)
        for project in projects:
            generate_weekly_report.delay(project.id, None)
            logger.info(f"REPORT_TRIGGER | project_id={project.id} | status=queued")
        logger.info(f"REPORT_TRIGGER | total_queued={count} | status=done")
