from celery import Celery
from celery.schedules import crontab

from app.core.settings import settings

celery_app = Celery(
    "sitesync",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.report", "app.tasks.ai_query"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Manila",
    enable_utc=True,
    beat_schedule={
        "weekly-report-every-monday": {
            "task": "trigger_all_weekly_reports",
            "schedule": crontab(hour=8, minute=0, day_of_week=1),
        }
    },
)
