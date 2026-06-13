from datetime import date

from httpx import AsyncClient

from app.models.project import Project, ProjectAssignment

PROJECT_PAYLOAD = {
    "name": "Daily Log Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}

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
# Helpers
# ---------------------------------------------------------------------------


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Daily Log Test Project",
            location="Manila",
            total_budget=1_000_000,
            start_date=date(2026, 1, 1),
            target_end_date=date(2026, 12, 31),
            status="Active",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def assign_manager(session_factory, project_id: int, user_id: int) -> None:
    async with session_factory() as session:
        assignment = ProjectAssignment(project_id=project_id, user_id=user_id)
        session.add(assignment)
        await session.commit()


async def create_log(session_factory, project_id: int, submitted_by: int) -> int:
    from app.models.daily_log import DailyLog

    async with session_factory() as session:
        log = DailyLog(
            project_id=project_id,
            submitted_by=submitted_by,
            log_date=date(2026, 1, 1),
            work_accomplished="Test work",
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log.id


# ---------------------------------------------------------------------------
# List Daily Logs
# ---------------------------------------------------------------------------


class TestDailyLogList:
    async def test_owner_can_list_logs(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )

        res = await owner_client.get(f"/api/v1/projects/{project.id}/daily-logs")
        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_assigned_manager_can_list_logs(self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )

        res = await manager_client.get(f"/api/v1/projects/{project.id}/daily-logs")
        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_unassigned_manager_gets_empty_list(self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )

        res = await manager_client.get(f"/api/v1/projects/{project.id}/daily-logs")
        assert res.status_code == 200
        assert res.json() == []

    async def test_worker_cannot_list_logs(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await worker_client.get(f"/api/v1/projects/{project.id}/daily-logs")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await unauth_client.get(f"/api/v1/projects/{project.id}/daily-logs")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Get Daily Log by ID
# ---------------------------------------------------------------------------


class TestDailyLogGet:
    async def test_owner_can_get_log(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        create_res = await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        log_id = create_res.json()["id"]

        res = await owner_client.get(f"/api/v1/projects/{project.id}/daily-logs/{log_id}")
        assert res.status_code == 200
        assert res.json()["id"] == log_id

    async def test_assigned_manager_can_get_log(self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        create_res = await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        log_id = create_res.json()["id"]

        res = await manager_client.get(f"/api/v1/projects/{project.id}/daily-logs/{log_id}")
        assert res.status_code == 200

    async def test_unassigned_manager_cannot_get_log(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log_id = await create_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await manager_client.get(f"/api/v1/projects/{project.id}/daily-logs/{log_id}")
        assert res.status_code == 404

    async def test_log_not_found(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await owner_client.get(f"/api/v1/projects/{project.id}/daily-logs/99999")
        assert res.status_code == 404

    async def test_unauthenticated_cannot_get(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await unauth_client.get(f"/api/v1/projects/{project.id}/daily-logs/1")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Create Daily Log
# ---------------------------------------------------------------------------


class TestDailyLogCreate:
    async def test_owner_can_create_log(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        assert res.status_code == 201
        assert res.json()["work_accomplished"] == "Poured concrete for foundation."
        assert res.json()["project_id"] == project.id

    async def test_assigned_manager_can_create_log(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        res = await manager_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        assert res.status_code == 201
        assert res.json()["submitted_by"] == seed_users["manager"].id

    async def test_unassigned_manager_cannot_create_log(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await manager_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        assert res.status_code == 404

    async def test_duplicate_log_date_returns_400(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        res = await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        assert res.status_code == 400

    async def test_worker_cannot_create_log(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await worker_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await unauth_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Update Daily Log
# ---------------------------------------------------------------------------


class TestDailyLogUpdate:
    async def test_owner_can_update_log(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        create_res = await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        log_id = create_res.json()["id"]

        res = await owner_client.patch(
            f"/api/v1/projects/{project.id}/daily-logs/{log_id}",
            json=LOG_UPDATE_PAYLOAD,
        )
        assert res.status_code == 200
        assert res.json()["work_accomplished"] == "Updated work accomplished."

    async def test_assigned_manager_can_update_log(self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        create_res = await owner_client.post(
            f"/api/v1/projects/{project.id}/daily-logs",
            json=LOG_PAYLOAD,
        )
        log_id = create_res.json()["id"]

        res = await manager_client.patch(
            f"/api/v1/projects/{project.id}/daily-logs/{log_id}",
            json=LOG_UPDATE_PAYLOAD,
        )
        assert res.status_code == 200
        assert res.json()["work_accomplished"] == "Updated work accomplished."

    async def test_unassigned_manager_cannot_update_log(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log_id = await create_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await manager_client.patch(
            f"/api/v1/projects/{project.id}/daily-logs/{log_id}",
            json=LOG_UPDATE_PAYLOAD,
        )
        assert res.status_code == 404

    async def test_update_log_not_found(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await owner_client.patch(
            f"/api/v1/projects/{project.id}/daily-logs/99999",
            json=LOG_UPDATE_PAYLOAD,
        )
        assert res.status_code == 404

    async def test_worker_cannot_update_log(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await worker_client.patch(
            f"/api/v1/projects/{project.id}/daily-logs/1",
            json=LOG_UPDATE_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await unauth_client.patch(
            f"/api/v1/projects/{project.id}/daily-logs/1",
            json=LOG_UPDATE_PAYLOAD,
        )
        assert res.status_code == 401
