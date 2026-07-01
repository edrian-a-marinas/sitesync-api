from datetime import date, timedelta

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment, WorkerAssignment


# ---------------------------------------------------------------------------
# Session-scoped seed
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_worker_data(test_session_factory, seed_users):
    """
    Two projects:
    - assigned_project: worker is assigned, has one log (today) and one log (yesterday)
    - unassigned_project: worker is NOT assigned
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    async with test_session_factory() as session:
        async with session.begin():
            assigned_project = Project(
                owner_id=seed_users["owner"].id,
                name="Worker Assigned Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            unassigned_project = Project(
                owner_id=seed_users["owner"].id,
                name="Worker Unassigned Project",
                location="Manila",
                total_budget=500_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([assigned_project, unassigned_project])
            await session.flush()

            session.add(
                WorkerAssignment(
                    project_id=assigned_project.id,
                    user_id=seed_users["worker"].id,
                )
            )
            session.add(
                ProjectAssignment(
                    project_id=assigned_project.id,
                    user_id=seed_users["manager"].id,
                )
            )

            today_log = DailyLog(
                project_id=assigned_project.id,
                submitted_by=seed_users["manager"].id,
                log_date=today,
                work_accomplished="Today's work",
                weather_condition="Sunny",
                notes="No issues.",
            )
            yesterday_log = DailyLog(
                project_id=assigned_project.id,
                submitted_by=seed_users["manager"].id,
                log_date=yesterday,
                work_accomplished="Yesterday's work",
            )
            session.add_all([today_log, yesterday_log])

    yield {
        "assigned_project": assigned_project,
        "unassigned_project": unassigned_project,
        "today_log": today_log,
        "yesterday_log": yesterday_log,
        "today": today,
    }

    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Attendance).where(Attendance.daily_log_id.in_([today_log.id, yesterday_log.id])))
            await session.execute(delete(DailyLog).where(DailyLog.project_id.in_([assigned_project.id, unassigned_project.id])))
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id.in_([assigned_project.id, unassigned_project.id])))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id.in_([assigned_project.id, unassigned_project.id])))
            await session.execute(delete(Project).where(Project.id.in_([assigned_project.id, unassigned_project.id])))


# ---------------------------------------------------------------------------
# GET /api/v1/workers/me/projects
# ---------------------------------------------------------------------------
class TestWorkerGetMyProjects:
    async def test_worker_sees_assigned_project(self, worker_client: AsyncClient, seed_worker_data):
        res = await worker_client.get("/api/v1/workers/me/projects")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        ids = [p["id"] for p in data]
        assert seed_worker_data["assigned_project"].id in ids

    async def test_worker_does_not_see_unassigned_project(self, worker_client: AsyncClient, seed_worker_data):
        res = await worker_client.get("/api/v1/workers/me/projects")
        assert res.status_code == 200
        ids = [p["id"] for p in res.json()]
        assert seed_worker_data["unassigned_project"].id not in ids

    async def test_response_shape(self, worker_client: AsyncClient, seed_worker_data):
        res = await worker_client.get("/api/v1/workers/me/projects")
        assert res.status_code == 200
        project = next(
            (p for p in res.json() if p["id"] == seed_worker_data["assigned_project"].id),
            None,
        )
        assert project is not None
        assert "name" in project
        assert "location" in project
        assert "status" in project
        assert "start_date" in project
        assert "target_end_date" in project
        assert "total_budget" in project

    async def test_owner_cannot_access_worker_endpoint(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/workers/me/projects")
        assert res.status_code == 403

    async def test_manager_cannot_access_worker_endpoint(self, manager_client: AsyncClient):
        res = await manager_client.get("/api/v1/workers/me/projects")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/workers/me/projects")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/workers/me/projects/{project_id}/daily-logs/today
# ---------------------------------------------------------------------------
class TestWorkerGetTodayLog:
    async def test_worker_sees_today_log(self, worker_client: AsyncClient, seed_worker_data):
        pid = seed_worker_data["assigned_project"].id
        res = await worker_client.get(f"/api/v1/workers/me/projects/{pid}/daily-logs/today")
        assert res.status_code == 200
        data = res.json()
        assert data["project_id"] == pid
        assert data["log_date"] == str(seed_worker_data["today"])

    async def test_response_shape(self, worker_client: AsyncClient, seed_worker_data):
        pid = seed_worker_data["assigned_project"].id
        res = await worker_client.get(f"/api/v1/workers/me/projects/{pid}/daily-logs/today")
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert "project_id" in data
        assert "submitted_by" in data
        assert "submitted_by_name" in data
        assert "log_date" in data
        assert "work_accomplished" in data

    async def test_worker_unassigned_project_returns_404(self, worker_client: AsyncClient, seed_worker_data):
        pid = seed_worker_data["unassigned_project"].id
        res = await worker_client.get(f"/api/v1/workers/me/projects/{pid}/daily-logs/today")
        assert res.status_code == 404

    async def test_nonexistent_project_returns_404(self, worker_client: AsyncClient):
        res = await worker_client.get("/api/v1/workers/me/projects/99999/daily-logs/today")
        assert res.status_code == 404

    async def test_owner_cannot_access_worker_today_log(self, owner_client: AsyncClient, seed_worker_data):
        pid = seed_worker_data["assigned_project"].id
        res = await owner_client.get(f"/api/v1/workers/me/projects/{pid}/daily-logs/today")
        assert res.status_code == 403

    async def test_manager_cannot_access_worker_today_log(self, manager_client: AsyncClient, seed_worker_data):
        pid = seed_worker_data["assigned_project"].id
        res = await manager_client.get(f"/api/v1/workers/me/projects/{pid}/daily-logs/today")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access(self, unauth_client: AsyncClient, seed_worker_data):
        pid = seed_worker_data["assigned_project"].id
        res = await unauth_client.get(f"/api/v1/workers/me/projects/{pid}/daily-logs/today")
        assert res.status_code == 401
