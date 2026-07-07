import logging

import requests

from app.core.celery import celery_app
from app.core.settings import settings

logger = logging.getLogger(__name__)


@celery_app.task(
    name="send_incident_webhook",
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=30,
    max_retries=3,
)
def send_incident_webhook(payload: dict):
    if not settings.WEBHOOK_URL:
        logger.warning("WEBHOOK | incident_id={} | status=skipped | reason=WEBHOOK_URL not configured".format(payload.get("incident_id")))
        return
    slack_message = {
        "text": (
            f":rotating_light: *High Severity Incident Logged*\n"
            f"Project ID: {payload.get('project_id')}\n"
            f"Daily Log ID: {payload.get('daily_log_id')}\n"
            f"Incident ID: {payload.get('incident_id')}\n"
            f"Description: {payload.get('description')}"
        )
    }
    try:
        response = requests.post(settings.WEBHOOK_URL, json=slack_message, timeout=5)
        response.raise_for_status()
        logger.info(f"WEBHOOK | incident_id={payload.get('incident_id')} | status=delivered")
    except requests.RequestException as e:
        logger.error(f"WEBHOOK | incident_id={payload.get('incident_id')} | status=failed | reason={str(e)}")
        raise
