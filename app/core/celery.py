from celery import Celery

from app.core.settings import settings

celery_app = Celery(
    "sitesync",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.report"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Manila",
    enable_utc=True,
)
