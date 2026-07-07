from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
import requests
from celery.exceptions import Retry
from httpx import AsyncClient
from kombu.exceptions import OperationalError
from sqlalchemy import delete

from app.core.settings import settings
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.project import Project
from app.tasks.webhook import send_incident_webhook


# ---------------------------------------------------------------------------
# Session-scoped seed — project + daily log used to create real incidents against
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_webhook_data(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="Webhook Test Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(project)
            await session.flush()
            log = DailyLog(
                project_id=project.id,
                submitted_by=seed_users["owner"].id,
                log_date=date(2026, 3, 1),
                work_accomplished="Webhook test daily log",
            )
            session.add(log)
            await session.flush()
    yield {"project": project, "log": log}
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Incident).where(Incident.daily_log_id == log.id))
            await session.execute(delete(DailyLog).where(DailyLog.id == log.id))
            await session.execute(delete(Project).where(Project.id == project.id))


def incidents_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/incidents"


# ---------------------------------------------------------------------------
# send_incident_webhook (Celery task — builds Slack payload, dispatches HTTP POST)
# ---------------------------------------------------------------------------
class TestSendIncidentWebhookTask:
    async def test_skips_when_webhook_url_not_configured(self):
        payload = {"incident_id": 1, "project_id": 8, "daily_log_id": 100, "description": "test"}
        with patch.object(settings, "WEBHOOK_URL", None), patch("app.tasks.webhook.requests.post") as mock_post:
            send_incident_webhook(payload)
        mock_post.assert_not_called()

    async def test_sends_formatted_slack_payload_on_success(self):
        payload = {
            "incident_id": 477,
            "project_id": 8,
            "daily_log_id": 2811,
            "description": "Crane malfunction",
        }
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with (
            patch.object(settings, "WEBHOOK_URL", "https://hooks.slack.com/services/fake/url"),
            patch("app.tasks.webhook.requests.post", return_value=mock_response) as mock_post,
        ):
            send_incident_webhook(payload)
        mock_post.assert_called_once()
        called_url, called_kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        assert called_url == "https://hooks.slack.com/services/fake/url"
        sent_json = called_kwargs["json"]
        assert "text" in sent_json
        assert "477" in sent_json["text"]
        assert "8" in sent_json["text"]
        assert "2811" in sent_json["text"]
        assert "Crane malfunction" in sent_json["text"]
        assert called_kwargs["timeout"] == 5

    async def test_raises_and_retries_on_request_exception(self):
        payload = {"incident_id": 999, "project_id": 8, "daily_log_id": 100, "description": "test"}
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("400 Client Error")
        with (
            patch.object(settings, "WEBHOOK_URL", "https://hooks.slack.com/services/fake/url"),
            patch("app.tasks.webhook.requests.post", return_value=mock_response),
        ):
            with pytest.raises(Retry):
                send_incident_webhook.apply(args=(payload,), throw=True)


# ---------------------------------------------------------------------------
# create_incident → send_incident_webhook wiring (only High severity dispatches)
# ---------------------------------------------------------------------------
class TestIncidentWebhookTrigger:
    async def test_high_severity_triggers_webhook_dispatch(self, owner_client: AsyncClient, seed_webhook_data):
        project = seed_webhook_data["project"]
        log = seed_webhook_data["log"]
        with patch("app.services.incident.send_incident_webhook") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(
                incidents_url(project.id, log.id),
                json={"description": "Generator failure", "severity": "High", "status": "Open"},
            )
        assert res.status_code == 201
        mock_task.delay.assert_called_once()
        sent_payload = mock_task.delay.call_args[0][0]
        assert sent_payload["event"] == "incident.logged"
        assert sent_payload["project_id"] == project.id
        assert sent_payload["daily_log_id"] == log.id
        assert sent_payload["severity"] == "High"
        assert sent_payload["description"] == "Generator failure"

    async def test_low_severity_does_not_trigger_webhook(self, owner_client: AsyncClient, seed_webhook_data):
        project = seed_webhook_data["project"]
        log = seed_webhook_data["log"]
        with patch("app.services.incident.send_incident_webhook") as mock_task:
            res = await owner_client.post(
                incidents_url(project.id, log.id),
                json={"description": "Minor equipment issue", "severity": "Low", "status": "Open"},
            )
        assert res.status_code == 201
        mock_task.delay.assert_not_called()

    async def test_medium_severity_does_not_trigger_webhook(self, owner_client: AsyncClient, seed_webhook_data):
        project = seed_webhook_data["project"]
        log = seed_webhook_data["log"]
        with patch("app.services.incident.send_incident_webhook") as mock_task:
            res = await owner_client.post(
                incidents_url(project.id, log.id),
                json={"description": "Worker reported minor injury", "severity": "Medium", "status": "Open"},
            )
        assert res.status_code == 201
        mock_task.delay.assert_not_called()

    async def test_webhook_queue_failure_does_not_break_incident_creation(self, owner_client: AsyncClient, seed_webhook_data):
        project = seed_webhook_data["project"]
        log = seed_webhook_data["log"]
        with patch("app.services.incident.send_incident_webhook") as mock_task:
            mock_task.delay.side_effect = OperationalError("broker unreachable")
            res = await owner_client.post(
                incidents_url(project.id, log.id),
                json={"description": "Broker down test", "severity": "High", "status": "Open"},
            )
        # Incident is still created successfully even if webhook dispatch queue is unreachable
        assert res.status_code == 201
        assert res.json()["severity"] == "High"
