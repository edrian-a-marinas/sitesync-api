from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment

LOG_PAYLOAD = {
    "log_date": "2026-01-01",
    "work_accomplished": "Poured concrete for foundation.",
    "weather_condition": "Sunny",
    "notes": "No issues.",
}

LOG_UPDATE_PAYLOAD = {
    "work_accomplished": "Updated work accomplished.",
}


# ---------------------------------------------------------------------------
# Session-scoped seeds
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_daily_log_data(test_session_factory, seed_users):
    """
    Two projects:
    - assigned_project: manager is assigned, has one log
    - unassigned_project: manager is NOT assigned, has one log
    Logs are pre-created for get/update tests.
    Create tests use their own projects via API to avoid date conflicts.
    """
    async with test_session_factory() as session:
        async with session.begin():
            assigned_project = Project(
                owner_id=seed_users["owner"].id,
                name="Assigned Log Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            unassigned_project = Project(
                owner_id=seed_users["owner"].id,
                name="Unassigned Log Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([assigned_project, unassigned_project])
            await session.flush()

            session.add(
                ProjectAssignment(
                    project_id=assigned_project.id,
                    user_id=seed_users["manager"].id,
                )
            )

            assigned_log = DailyLog(
                project_id=assigned_project.id,
                submitted_by=seed_users["owner"].id,
                log_date=date(2026, 1, 1),
                work_accomplished="Test work",
            )
            unassigned_log = DailyLog(
                project_id=unassigned_project.id,
                submitted_by=seed_users["owner"].id,
                log_date=date(2026, 1, 1),
                work_accomplished="Test work",
            )
            session.add_all([assigned_log, unassigned_log])

    yield {
        "assigned_project": assigned_project,
        "unassigned_project": unassigned_project,
        "assigned_log": assigned_log,
        "unassigned_log": unassigned_log,
    }
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(DailyLog).where(DailyLog.project_id.in_([assigned_project.id, unassigned_project.id])))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id.in_([assigned_project.id, unassigned_project.id])))
            await session.execute(delete(Project).where(Project.id.in_([assigned_project.id, unassigned_project.id])))


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_create_log_projects(test_session_factory, seed_users):
    """
    Dedicated projects for create/duplicate tests — isolated from seed_daily_log_data
    so log date conflicts don't bleed across test classes.
    """
    async with test_session_factory() as session:
        async with session.begin():
            owner_project = Project(
                owner_id=seed_users["owner"].id,
                name="Create Log Owner Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            manager_project = Project(
                owner_id=seed_users["owner"].id,
                name="Create Log Manager Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            unassigned_create_project = Project(
                owner_id=seed_users["owner"].id,
                name="Create Log Unassigned Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([owner_project, manager_project, unassigned_create_project])
            await session.flush()
            session.add(
                ProjectAssignment(
                    project_id=manager_project.id,
                    user_id=seed_users["manager"].id,
                )
            )

    yield {
        "owner_project": owner_project,
        "manager_project": manager_project,
        "unassigned_create_project": unassigned_create_project,
    }
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(DailyLog).where(
                    DailyLog.project_id.in_(
                        [
                            owner_project.id,
                            manager_project.id,
                            unassigned_create_project.id,
                        ]
                    )
                )
            )
            await session.execute(
                delete(ProjectAssignment).where(
                    ProjectAssignment.project_id.in_(
                        [
                            owner_project.id,
                            manager_project.id,
                            unassigned_create_project.id,
                        ]
                    )
                )
            )
            await session.execute(
                delete(Project).where(
                    Project.id.in_(
                        [
                            owner_project.id,
                            manager_project.id,
                            unassigned_create_project.id,
                        ]
                    )
                )
            )


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/daily-logs
# ---------------------------------------------------------------------------


class TestDailyLogList:
    async def test_owner_can_list_logs(self, owner_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        res = await owner_client.get(f"/api/v1/projects/{pid}/daily-logs")
        assert res.status_code == 200
        assert len(res.json()) >= 1

    async def test_assigned_manager_can_list_logs(self, manager_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        res = await manager_client.get(f"/api/v1/projects/{pid}/daily-logs")
        assert res.status_code == 200
        assert len(res.json()) >= 1

    async def test_unassigned_manager_gets_empty_list(self, manager_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["unassigned_project"].id
        res = await manager_client.get(f"/api/v1/projects/{pid}/daily-logs")
        assert res.status_code == 200
        assert res.json() == []

    async def test_worker_cannot_list_logs(self, worker_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        res = await worker_client.get(f"/api/v1/projects/{pid}/daily-logs")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        res = await unauth_client.get(f"/api/v1/projects/{pid}/daily-logs")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/daily-logs/{log_id}
# ---------------------------------------------------------------------------


class TestDailyLogGet:
    async def test_owner_can_get_log(self, owner_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        lid = seed_daily_log_data["assigned_log"].id
        res = await owner_client.get(f"/api/v1/projects/{pid}/daily-logs/{lid}")
        assert res.status_code == 200
        assert res.json()["id"] == lid

    async def test_assigned_manager_can_get_log(self, manager_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        lid = seed_daily_log_data["assigned_log"].id
        res = await manager_client.get(f"/api/v1/projects/{pid}/daily-logs/{lid}")
        assert res.status_code == 200

    async def test_unassigned_manager_cannot_get_log(self, manager_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["unassigned_project"].id
        lid = seed_daily_log_data["unassigned_log"].id
        res = await manager_client.get(f"/api/v1/projects/{pid}/daily-logs/{lid}")
        assert res.status_code == 404

    async def test_log_not_found(self, owner_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        res = await owner_client.get(f"/api/v1/projects/{pid}/daily-logs/99999")
        assert res.status_code == 404

    async def test_unauthenticated_cannot_get(self, unauth_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        lid = seed_daily_log_data["assigned_log"].id
        res = await unauth_client.get(f"/api/v1/projects/{pid}/daily-logs/{lid}")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/daily-logs
# ---------------------------------------------------------------------------


class TestDailyLogCreate:
    async def test_owner_can_create_log(self, owner_client: AsyncClient, seed_create_log_projects):
        pid = seed_create_log_projects["owner_project"].id
        res = await owner_client.post(f"/api/v1/projects/{pid}/daily-logs", json=LOG_PAYLOAD)
        assert res.status_code == 201
        assert res.json()["work_accomplished"] == "Poured concrete for foundation."
        assert res.json()["project_id"] == pid

    async def test_assigned_manager_can_create_log(self, manager_client: AsyncClient, seed_create_log_projects, seed_users):
        pid = seed_create_log_projects["manager_project"].id
        res = await manager_client.post(f"/api/v1/projects/{pid}/daily-logs", json=LOG_PAYLOAD)
        assert res.status_code == 201
        assert res.json()["submitted_by"] == seed_users["manager"].id

    async def test_unassigned_manager_cannot_create_log(self, manager_client: AsyncClient, seed_create_log_projects):
        pid = seed_create_log_projects["unassigned_create_project"].id
        res = await manager_client.post(f"/api/v1/projects/{pid}/daily-logs", json=LOG_PAYLOAD)
        assert res.status_code == 404

    async def test_duplicate_log_date_returns_400(self, owner_client: AsyncClient, seed_create_log_projects):
        pid = seed_create_log_projects["owner_project"].id
        # first post may already exist from test_owner_can_create_log — attempt second
        await owner_client.post(f"/api/v1/projects/{pid}/daily-logs", json=LOG_PAYLOAD)
        res = await owner_client.post(f"/api/v1/projects/{pid}/daily-logs", json=LOG_PAYLOAD)
        assert res.status_code == 400

    async def test_worker_cannot_create_log(self, worker_client: AsyncClient, seed_create_log_projects):
        pid = seed_create_log_projects["owner_project"].id
        res = await worker_client.post(f"/api/v1/projects/{pid}/daily-logs", json=LOG_PAYLOAD)
        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_create_log_projects):
        pid = seed_create_log_projects["owner_project"].id
        res = await unauth_client.post(f"/api/v1/projects/{pid}/daily-logs", json=LOG_PAYLOAD)
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/projects/{project_id}/daily-logs/{log_id}
# ---------------------------------------------------------------------------


class TestDailyLogUpdate:
    async def test_owner_can_update_log(self, owner_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        lid = seed_daily_log_data["assigned_log"].id
        res = await owner_client.patch(f"/api/v1/projects/{pid}/daily-logs/{lid}", json=LOG_UPDATE_PAYLOAD)
        assert res.status_code == 200
        assert res.json()["work_accomplished"] == "Updated work accomplished."

    async def test_assigned_manager_can_update_log(self, manager_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        lid = seed_daily_log_data["assigned_log"].id
        res = await manager_client.patch(f"/api/v1/projects/{pid}/daily-logs/{lid}", json=LOG_UPDATE_PAYLOAD)
        assert res.status_code == 200

    async def test_unassigned_manager_cannot_update_log(self, manager_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["unassigned_project"].id
        lid = seed_daily_log_data["unassigned_log"].id
        res = await manager_client.patch(f"/api/v1/projects/{pid}/daily-logs/{lid}", json=LOG_UPDATE_PAYLOAD)
        assert res.status_code == 404

    async def test_update_log_not_found(self, owner_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        res = await owner_client.patch(f"/api/v1/projects/{pid}/daily-logs/99999", json=LOG_UPDATE_PAYLOAD)
        assert res.status_code == 404

    async def test_worker_cannot_update_log(self, worker_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        lid = seed_daily_log_data["assigned_log"].id
        res = await worker_client.patch(f"/api/v1/projects/{pid}/daily-logs/{lid}", json=LOG_UPDATE_PAYLOAD)
        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, unauth_client: AsyncClient, seed_daily_log_data):
        pid = seed_daily_log_data["assigned_project"].id
        lid = seed_daily_log_data["assigned_log"].id
        res = await unauth_client.patch(f"/api/v1/projects/{pid}/daily-logs/{lid}", json=LOG_UPDATE_PAYLOAD)
        assert res.status_code == 401
