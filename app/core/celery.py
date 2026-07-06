import logging

from celery import Celery
from celery.schedules import crontab

from app.core.settings import settings

logger = logging.getLogger(__name__)

_use_sqs = bool(settings.AWS_REGION and settings.AWS_ACCOUNT_ID)
_broker_url = "sqs://" if _use_sqs else settings.REDIS_URL

celery_app = Celery(
    "sitesync",
    broker=_broker_url,
    backend=settings.REDIS_URL,
    include=["app.tasks.report", "app.tasks.ai_query", "app.tasks.ml", "app.tasks.embedding"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Manila",
    enable_utc=True,
    broker_transport_options={
        "region": settings.AWS_REGION,
        "predefined_queues": {
            "celery": {
                "url": f"https://sqs.{settings.AWS_REGION}.amazonaws.com/{settings.AWS_ACCOUNT_ID}/sitesync-celery",
            }
        },
        "polling_interval": 20,
        "wait_time_seconds": 20,
        "visibility_timeout": 600,
    }
    if _use_sqsc
    else {},
    task_default_queue="celery",
    beat_schedule={
        "weekly-report-every-monday": {
            "task": "trigger_all_weekly_reports",
            "schedule": crontab(hour=8, minute=0, day_of_week=1),
        },
        "cleanup-old-ai-queries-daily": {
            "task": "cleanup_old_ai_queries",
            "schedule": crontab(hour=3, minute=0),
        },
        "retrain-ml-models-weekly": {
            "task": "retrain_ml_models",
            "schedule": crontab(hour=9, minute=0, day_of_week=1),
        },
        "cleanup-old-reports-daily": {
            "task": "cleanup_old_reports",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)
