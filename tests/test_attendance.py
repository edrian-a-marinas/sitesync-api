from datetime import date

from httpx import AsyncClient

from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment, WorkerAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/v1/projects/{project_id}/daily-logs/{log_id}/attendance"


def attendance_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/attendance"


def me_url(project_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/1/attendance/me"


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Attendance Test Project",
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


async def create_daily_log(session_factory, project_id: int, submitted_by: int) -> DailyLog:
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
        return log


async def assign_manager(session_factory, project_id: int, user_id: int) -> None:
    async with session_factory() as session:
        session.add(ProjectAssignment(project_id=project_id, user_id=user_id))
        await session.commit()


async def assign_worker(session_factory, project_id: int, user_id: int) -> None:
    async with session_factory() as session:
        session.add(WorkerAssignment(project_id=project_id, user_id=user_id))
        await session.commit()


def attendance_payload(worker_id: int, hours: float = 8.0) -> dict:
    return {"worker_id": worker_id, "hours_worked": hours}


# ---------------------------------------------------------------------------
# POST attendance  (create)
# ---------------------------------------------------------------------------


class TestCreateAttendance:
    async def test_owner_can_create_attendance(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)

        res = await owner_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        assert res.status_code == 201
        data = res.json()
        assert data["worker_id"] == seed_users["worker"].id
        assert data["daily_log_id"] == log.id
        assert data["hours_worked"] == 8.0

    async def test_assigned_manager_can_create_attendance(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)

        res = await manager_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        assert res.status_code == 201
        assert res.json()["worker_id"] == seed_users["worker"].id

    async def test_unassigned_manager_cannot_create_attendance(self, manager_client: AsyncClient, seed_users, test_session_factory):
        # manager NOT assigned to this project
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)

        res = await manager_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        assert res.status_code == 400

    async def test_worker_not_assigned_to_project_returns_400(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        # worker NOT assigned via WorkerAssignment

        res = await owner_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        assert res.status_code == 400

    async def test_duplicate_attendance_returns_400(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)

        payload = attendance_payload(seed_users["worker"].id)
        await owner_client.post(attendance_url(project.id, log.id), json=payload)
        res = await owner_client.post(attendance_url(project.id, log.id), json=payload)

        assert res.status_code == 400

    async def test_nonexistent_log_returns_400(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)

        res = await owner_client.post(
            attendance_url(project.id, 99999),
            json=attendance_payload(seed_users["worker"].id),
        )

        assert res.status_code == 400

    async def test_site_worker_cannot_create_attendance(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await worker_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET attendance  (list)
# ---------------------------------------------------------------------------


class TestGetAttendance:
    async def test_owner_sees_all_attendance_for_log(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await owner_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        res = await owner_client.get(attendance_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["worker_id"] == seed_users["worker"].id

    async def test_manager_sees_all_attendance_for_log(
        self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory
    ):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await owner_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        res = await manager_client.get(attendance_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_worker_sees_only_own_attendance(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await owner_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        res = await worker_client.get(attendance_url(project.id, log.id))

        assert res.status_code == 200
        records = res.json()
        assert all(r["worker_id"] == seed_users["worker"].id for r in records)

    async def test_nonexistent_log_returns_empty_list(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await owner_client.get(attendance_url(project.id, 99999))

        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_get(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.get(attendance_url(project.id, log.id))

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /me  (attendance history)
# ---------------------------------------------------------------------------


class TestGetMyAttendanceHistory:
    async def test_worker_sees_own_history(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await owner_client.post(
            attendance_url(project.id, log.id),
            json=attendance_payload(seed_users["worker"].id),
        )

        res = await worker_client.get(f"/api/v1/projects/{project.id}/daily-logs/{log.id}/attendance/me")

        assert res.status_code == 200
        assert len(res.json()) == 1
        record = res.json()[0]
        assert record["daily_log_id"] == log.id
        assert record["hours_worked"] == 8.0
        assert "log_date" in record

    async def test_owner_can_view_own_history_endpoint(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        # owner has no attendance records — should return empty list, not error
        res = await owner_client.get(f"/api/v1/projects/{project.id}/daily-logs/{log.id}/attendance/me")

        assert res.status_code == 200
        assert res.json() == []

    async def test_history_returns_empty_when_no_records(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await worker_client.get(f"/api/v1/projects/{project.id}/daily-logs/{log.id}/attendance/me")

        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_get_history(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.get(f"/api/v1/projects/{project.id}/daily-logs/{log.id}/attendance/me")

        assert res.status_code == 401
