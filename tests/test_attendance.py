from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment, WorkerAssignment


# ---------------------------------------------------------------------------
# Session-scoped seed
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_attendance_data(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="Attendance Test Project",
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
                log_date=date(2026, 1, 1),
                work_accomplished="Test work",
            )
            session.add(log)
            await session.flush()
            session.add_all(
                [
                    ProjectAssignment(project_id=project.id, user_id=seed_users["manager"].id),
                    WorkerAssignment(project_id=project.id, user_id=seed_users["worker"].id),
                ]
            )

    yield {"project": project, "log": log}

    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Attendance).where(Attendance.daily_log_id.in_(select(DailyLog.id).where(DailyLog.project_id == project.id))))
            await session.execute(delete(DailyLog).where(DailyLog.project_id == project.id))
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id == project.id))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id == project.id))
            await session.execute(delete(Project).where(Project.id == project.id))


def attendance_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/attendance"


def attendance_payload(worker_id: int, hours: float = 8.0) -> dict:
    return {"worker_id": worker_id, "hours_worked": hours}


# ---------------------------------------------------------------------------
# POST attendance (create)
# ---------------------------------------------------------------------------
class TestCreateAttendance:
    async def test_owner_can_create_attendance(self, owner_client: AsyncClient, seed_users, seed_attendance_data):
        d = seed_attendance_data
        res = await owner_client.post(
            attendance_url(d["project"].id, d["log"].id),
            json=attendance_payload(seed_users["worker"].id),
        )
        assert res.status_code == 201
        data = res.json()
        assert data["worker_id"] == seed_users["worker"].id
        assert data["daily_log_id"] == d["log"].id
        assert data["hours_worked"] == 8.0

    async def test_assigned_manager_can_create_attendance(self, manager_client: AsyncClient, seed_users, seed_attendance_data, test_session_factory):
        d = seed_attendance_data
        # Use a second log to avoid duplicate conflict
        async with test_session_factory() as session:
            async with session.begin():
                log2 = DailyLog(
                    project_id=d["project"].id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 1, 2),
                    work_accomplished="Test work 2",
                )
                session.add(log2)
                await session.flush()
        res = await manager_client.post(
            attendance_url(d["project"].id, log2.id),
            json=attendance_payload(seed_users["worker"].id),
        )
        assert res.status_code == 201
        assert res.json()["worker_id"] == seed_users["worker"].id

    async def test_unassigned_manager_cannot_create_attendance(self, manager_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Unassigned Project",
                    location="Manila",
                    total_budget=500_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(project)
                await session.flush()
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 1, 1),
                    work_accomplished="Test",
                )
                session.add(log)
                await session.flush()
        res = await manager_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )
        assert res.status_code == 400

    async def test_worker_not_assigned_returns_400(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="No Worker Project",
                    location="Manila",
                    total_budget=500_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(project)
                await session.flush()
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 1, 1),
                    work_accomplished="Test",
                )
                session.add(log)
                await session.flush()
        res = await owner_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )
        assert res.status_code == 400

    async def test_duplicate_attendance_returns_400(self, owner_client: AsyncClient, seed_users, test_session_factory, seed_attendance_data):
        d = seed_attendance_data
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=d["project"].id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 1, 3),
                    work_accomplished="Dup test",
                )
                session.add(log)
                await session.flush()
        payload = attendance_payload(seed_users["worker"].id)
        await owner_client.post(attendance_url(d["project"].id, log.id), json=payload)
        res = await owner_client.post(attendance_url(d["project"].id, log.id), json=payload)
        assert res.status_code == 400

    async def test_nonexistent_log_returns_400(self, owner_client: AsyncClient, seed_users, seed_attendance_data):
        d = seed_attendance_data
        res = await owner_client.post(
            attendance_url(d["project"].id, 99999),
            json=attendance_payload(seed_users["worker"].id),
        )
        assert res.status_code == 400

    async def test_site_worker_cannot_create_attendance(self, worker_client: AsyncClient, seed_users, seed_attendance_data):
        d = seed_attendance_data
        res = await worker_client.post(
            attendance_url(d["project"].id, d["log"].id),
            json=attendance_payload(seed_users["worker"].id),
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_users, seed_attendance_data):
        d = seed_attendance_data
        res = await unauth_client.post(
            attendance_url(d["project"].id, d["log"].id),
            json=attendance_payload(seed_users["worker"].id),
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET attendance (list)
# ---------------------------------------------------------------------------
class TestGetAttendance:
    async def test_owner_sees_all_attendance_for_log(self, owner_client: AsyncClient, seed_users, seed_attendance_data):
        d = seed_attendance_data
        res = await owner_client.get(attendance_url(d["project"].id, d["log"].id))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    async def test_manager_sees_attendance_for_assigned_log(self, manager_client: AsyncClient, seed_attendance_data):
        d = seed_attendance_data
        res = await manager_client.get(attendance_url(d["project"].id, d["log"].id))
        assert res.status_code == 200

    async def test_worker_sees_only_own_attendance(self, worker_client: AsyncClient, seed_users, seed_attendance_data):
        d = seed_attendance_data
        res = await worker_client.get(attendance_url(d["project"].id, d["log"].id))
        assert res.status_code == 200
        records = res.json()
        assert all(r["worker_id"] == seed_users["worker"].id for r in records)

    async def test_nonexistent_log_returns_empty_list(self, owner_client: AsyncClient, seed_attendance_data):
        d = seed_attendance_data
        res = await owner_client.get(attendance_url(d["project"].id, 99999))
        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_get(self, unauth_client: AsyncClient, seed_attendance_data):
        d = seed_attendance_data
        res = await unauth_client.get(attendance_url(d["project"].id, d["log"].id))
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /me (attendance history)
# ---------------------------------------------------------------------------
class TestGetMyAttendanceHistory:
    async def test_worker_sees_own_history(self, worker_client: AsyncClient, seed_users, seed_attendance_data):
        d = seed_attendance_data
        res = await worker_client.get(f"/api/v1/projects/{d['project'].id}/daily-logs/attendance/me")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    async def test_owner_gets_empty_own_history(self, owner_client: AsyncClient, seed_attendance_data):
        d = seed_attendance_data
        res = await owner_client.get(f"/api/v1/projects/{d['project'].id}/daily-logs/attendance/me")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_history_empty_when_no_records(self, worker_client: AsyncClient, test_session_factory, seed_users):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Empty History Project",
                    location="Manila",
                    total_budget=500_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(project)
                await session.flush()
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 1, 4),
                    work_accomplished="Empty history test",
                )
                session.add(log)
                await session.flush()
        res = await worker_client.get(f"/api/v1/projects/{project.id}/daily-logs/attendance/me")
        assert res.status_code == 200
        data = res.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_unauthenticated_cannot_get_history(self, unauth_client: AsyncClient, seed_attendance_data):
        d = seed_attendance_data
        res = await unauth_client.get(f"/api/v1/projects/{d['project'].id}/daily-logs/attendance/me")
        assert res.status_code == 401
