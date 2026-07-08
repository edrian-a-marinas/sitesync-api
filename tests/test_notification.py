from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.project import Project, ProjectAssignment
from app.services.notification import (
    create_notification,
    delete_notification,
    get_notifications,
    get_unread_count,
    mark_as_read,
    notify_project_stakeholders,
    notify_project_stakeholders_sync,
)


# ---------------------------------------------------------------------------
# Session-scoped seed — project + PM assignment used for stakeholder dispatch
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_notification_data(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="Notification Test Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(project)
            await session.flush()
            assignment = ProjectAssignment(project_id=project.id, user_id=seed_users["manager"].id)
            session.add(assignment)
            await session.flush()
    yield {"project": project, "manager": seed_users["manager"]}
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id == project.id))
            await session.execute(delete(Project).where(Project.id == project.id))


# ---------------------------------------------------------------------------
# create_notification / get_notifications / mark_as_read / get_unread_count
# ---------------------------------------------------------------------------
class TestNotificationService:
    async def test_create_notification_inserts_and_returns_doc(self):
        mock_result = MagicMock(inserted_id="abc123")
        with patch("app.services.notification.notifications_collection.insert_one", new=AsyncMock(return_value=mock_result)):
            doc = await create_notification(user_id=1, type="incident", title="Test", message="msg", data={"key": "value"})
        assert doc["user_id"] == 1
        assert doc["type"] == "incident"
        assert doc["is_read"] is False
        assert doc["_id"] == "abc123"

    async def test_get_notifications_returns_paginated_list(self):
        docs = [
            {
                "_id": "id1",
                "user_id": 1,
                "type": "incident",
                "title": "A",
                "message": "a",
                "data": {},
                "is_read": False,
                "created_at": datetime.now(timezone.utc),
            },
        ]

        class MockCursor:
            def __init__(self, items):
                self.items = items

            def sort(self, *a, **kw):
                return self

            def skip(self, *a, **kw):
                return self

            def limit(self, *a, **kw):
                return self

            def __aiter__(self):
                return self._gen()

            async def _gen(self):
                for item in self.items:
                    yield item

        with patch("app.services.notification.notifications_collection.find", return_value=MockCursor(docs)):
            results = await get_notifications(user_id=1, page=1, page_size=20)
        assert len(results) == 1
        assert results[0]["_id"] == "id1"

    async def test_mark_as_read_success(self):
        mock_result = MagicMock(modified_count=1)
        with patch("app.services.notification.notifications_collection.update_one", new=AsyncMock(return_value=mock_result)):
            success = await mark_as_read("64b7f9f9f9f9f9f9f9f9f9f9", user_id=1)
        assert success is True

    async def test_mark_as_read_not_found_returns_false(self):
        mock_result = MagicMock(modified_count=0)
        with patch("app.services.notification.notifications_collection.update_one", new=AsyncMock(return_value=mock_result)):
            success = await mark_as_read("64b7f9f9f9f9f9f9f9f9f9f9", user_id=1)
        assert success is False

    async def test_get_unread_count_returns_count(self):
        with patch("app.services.notification.notifications_collection.count_documents", new=AsyncMock(return_value=3)):
            count = await get_unread_count(user_id=1)
        assert count == 3

    async def test_delete_notification_success(self):
        mock_result = MagicMock(deleted_count=1)
        with patch("app.services.notification.notifications_collection.delete_one", new=AsyncMock(return_value=mock_result)):
            success = await delete_notification("64b7f9f9f9f9f9f9f9f9f9f9", user_id=1)
        assert success is True

    async def test_delete_notification_not_found_returns_false(self):
        mock_result = MagicMock(deleted_count=0)
        with patch("app.services.notification.notifications_collection.delete_one", new=AsyncMock(return_value=mock_result)):
            success = await delete_notification("64b7f9f9f9f9f9f9f9f9f9f9", user_id=1)
        assert success is False


# ---------------------------------------------------------------------------
# notify_project_stakeholders — resolves owner + assigned PMs, dispatches to each
# ---------------------------------------------------------------------------
class TestNotifyProjectStakeholders:
    async def test_dispatches_to_owner_and_assigned_manager(self, seed_notification_data, db):
        project = seed_notification_data["project"]
        manager = seed_notification_data["manager"]
        with (
            patch("app.services.notification.create_notification", new=AsyncMock(return_value={"_id": "n1"})) as mock_create,
            patch("app.services.notification.manager.send_to_user", new=AsyncMock()) as mock_send,
        ):
            await notify_project_stakeholders(
                project_id=project.id,
                type="incident",
                title="Test",
                message="msg",
                data={"incident_id": 1},
                db=db,
            )
        recipient_ids = {call.kwargs["user_id"] for call in mock_create.call_args_list}
        assert project.owner_id in recipient_ids
        assert manager.id in recipient_ids
        assert mock_send.call_count == len(recipient_ids)

    async def test_project_not_found_does_not_dispatch(self, db):
        with patch("app.services.notification.create_notification", new=AsyncMock()) as mock_create:
            await notify_project_stakeholders(
                project_id=999999,
                type="incident",
                title="Test",
                message="msg",
                data={},
                db=db,
            )
        mock_create.assert_not_called()

    async def test_per_recipient_failure_does_not_stop_others(self, seed_notification_data, db):
        project = seed_notification_data["project"]
        with (
            patch("app.services.notification.create_notification", new=AsyncMock(side_effect=[Exception("boom"), {"_id": "n2"}])),
            patch("app.services.notification.manager.send_to_user", new=AsyncMock()) as mock_send,
        ):
            await notify_project_stakeholders(
                project_id=project.id,
                type="incident",
                title="Test",
                message="msg",
                data={},
                db=db,
            )
        assert mock_send.call_count == 1


# ---------------------------------------------------------------------------
# notify_project_stakeholders_sync — Celery-safe sync wrapper (bridges to async)
# ---------------------------------------------------------------------------
class TestNotifyProjectStakeholdersSync:
    def test_sync_wrapper_dispatches_via_asyncio_run(self, seed_notification_data):
        project = seed_notification_data["project"]
        manager_user = seed_notification_data["manager"]
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = project
        mock_db.execute.return_value.scalars.return_value.all.return_value = [manager_user.id]
        with patch("app.services.notification.asyncio.run") as mock_run:
            notify_project_stakeholders_sync(
                project_id=project.id,
                type="report_ready",
                title="Report Ready",
                message="msg",
                data={},
                db=mock_db,
            )
        mock_run.assert_called_once()

    def test_sync_wrapper_project_not_found_skips_dispatch(self):
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with patch("app.services.notification.asyncio.run") as mock_run:
            notify_project_stakeholders_sync(
                project_id=999999,
                type="report_ready",
                title="Report Ready",
                message="msg",
                data={},
                db=mock_db,
            )
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Notification router — list, unread-count, mark as read
# ---------------------------------------------------------------------------
class TestNotificationRouter:
    async def test_list_notifications_returns_data(self, owner_client: AsyncClient):
        with patch("app.routers.notification._get_notifications", new=AsyncMock(return_value=[{"_id": "n1"}])):
            res = await owner_client.get("/api/v1/notifications")
        assert res.status_code == 200
        assert res.json() == [{"_id": "n1"}]

    async def test_unread_count_returns_data(self, owner_client: AsyncClient):
        with patch("app.routers.notification._get_unread_count", new=AsyncMock(return_value=5)):
            res = await owner_client.get("/api/v1/notifications/unread-count")
        assert res.status_code == 200
        assert res.json() == {"unread_count": 5}

    async def test_mark_as_read_success(self, owner_client: AsyncClient):
        with patch("app.routers.notification._mark_as_read", new=AsyncMock(return_value=True)):
            res = await owner_client.patch("/api/v1/notifications/64b7f9f9f9f9f9f9f9f9f9f9/read")
        assert res.status_code == 200
        assert res.json() == {"status": "read"}

    async def test_mark_as_read_not_found_returns_404(self, owner_client: AsyncClient):
        with patch("app.routers.notification.mark_as_read", new=AsyncMock(return_value=False)):
            res = await owner_client.patch("/api/v1/notifications/64b7f9f9f9f9f9f9f9f9f9f9/read")
        assert res.status_code == 404

    async def test_delete_notification_success(self, owner_client: AsyncClient):
        with patch("app.routers.notification._delete_notification", new=AsyncMock(return_value=True)):
            res = await owner_client.delete("/api/v1/notifications/64b7f9f9f9f9f9f9f9f9f9f9")
        assert res.status_code == 200
        assert res.json() == {"status": "deleted"}

    async def test_delete_notification_not_found_returns_404(self, owner_client: AsyncClient):
        with patch("app.routers.notification._delete_notification", new=AsyncMock(return_value=False)):
            res = await owner_client.delete("/api/v1/notifications/64b7f9f9f9f9f9f9f9f9f9f9")
        assert res.status_code == 404
