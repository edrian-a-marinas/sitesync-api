from datetime import date

from httpx import AsyncClient

from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment, ProjectPhase, WorkerAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def create_project(session_factory, owner_id: int, name: str = "Test Project") -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name=name,
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


async def create_material(session_factory, log_id: int) -> None:
    async with session_factory() as session:
        session.add(
            Material(
                daily_log_id=log_id,
                name="Cement",
                quantity=10.0,
                unit="bags",
                unit_cost=250.0,
            )
        )
        await session.commit()


async def create_attendance(session_factory, log_id: int, worker_id: int, hours: float = 8.0) -> None:
    async with session_factory() as session:
        session.add(
            Attendance(
                daily_log_id=log_id,
                worker_id=worker_id,
                hours_worked=hours,
            )
        )
        await session.commit()


async def create_incident(session_factory, log_id: int, reported_by: int, status: str = "Open") -> None:
    async with session_factory() as session:
        session.add(
            Incident(
                daily_log_id=log_id,
                reported_by=reported_by,
                description="Test incident",
                severity="High",
                status=status,
            )
        )
        await session.commit()


async def create_phase(session_factory, project_id: int) -> ProjectPhase:
    async with session_factory() as session:
        phase = ProjectPhase(
            project_id=project_id,
            name="Foundation",
            allocated_budget=500_000,
            status="In Progress",
        )
        session.add(phase)
        await session.commit()
        await session.refresh(phase)
        return phase


# ---------------------------------------------------------------------------
# GET /dashboard/owner
# ---------------------------------------------------------------------------


class TestOwnerDashboard:
    async def test_owner_can_access_dashboard(self, owner_client: AsyncClient, seed_users, test_session_factory):
        await create_project(test_session_factory, seed_users["owner"].id)

        res = await owner_client.get("/api/v1/dashboard/owner")

        assert res.status_code == 200
        data = res.json()
        assert "total_active_projects" in data
        assert "total_budget" in data
        assert "total_spending" in data
        assert "over_budget_projects" in data
        assert "total_workers_active" in data
        assert "total_material_cost" in data

    async def test_owner_dashboard_counts_active_projects(self, owner_client: AsyncClient, seed_users, test_session_factory):
        await create_project(test_session_factory, seed_users["owner"].id, name="Project A")
        await create_project(test_session_factory, seed_users["owner"].id, name="Project B")

        res = await owner_client.get("/api/v1/dashboard/owner")

        assert res.status_code == 200
        assert res.json()["total_active_projects"] >= 2

    async def test_owner_dashboard_reflects_material_cost(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await create_material(test_session_factory, log.id)

        res = await owner_client.get("/api/v1/dashboard/owner")

        assert res.status_code == 200
        assert res.json()["total_material_cost"] >= 2500.0  # 10 * 250

    async def test_manager_cannot_access_owner_dashboard(self, manager_client: AsyncClient, seed_users, test_session_factory):
        res = await manager_client.get("/api/v1/dashboard/owner")

        assert res.status_code == 403

    async def test_worker_cannot_access_owner_dashboard(self, worker_client: AsyncClient, seed_users, test_session_factory):
        res = await worker_client.get("/api/v1/dashboard/owner")

        assert res.status_code == 403

    async def test_unauthenticated_cannot_access_owner_dashboard(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/dashboard/owner")

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /dashboard/manager/{project_id}
# ---------------------------------------------------------------------------


class TestManagerDashboard:
    async def test_owner_can_access_manager_dashboard(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await owner_client.get(f"/api/v1/dashboard/manager/{project.id}")

        assert res.status_code == 200
        data = res.json()
        assert data["project_id"] == project.id
        assert data["project_name"] == project.name
        assert "logs_submitted" in data
        assert "attendance_rate" in data
        assert "total_material_cost" in data
        assert "total_incidents" in data
        assert "open_incidents" in data
        assert "phases" in data

    async def test_assigned_manager_can_access_dashboard(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        res = await manager_client.get(f"/api/v1/dashboard/manager/{project.id}")

        assert res.status_code == 200
        assert res.json()["project_id"] == project.id

    async def test_unassigned_manager_gets_404(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await manager_client.get(f"/api/v1/dashboard/manager/{project.id}")

        assert res.status_code == 404

    async def test_nonexistent_project_returns_404(self, owner_client: AsyncClient, seed_users, test_session_factory):
        res = await owner_client.get("/api/v1/dashboard/manager/99999")

        assert res.status_code == 404

    async def test_dashboard_reflects_logs_and_incidents(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await create_incident(test_session_factory, log.id, seed_users["owner"].id, status="Open")

        res = await owner_client.get(f"/api/v1/dashboard/manager/{project.id}")

        assert res.status_code == 200
        data = res.json()
        assert data["logs_submitted"] >= 1
        assert data["total_incidents"] >= 1
        assert data["open_incidents"] >= 1

    async def test_dashboard_includes_phases(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await create_phase(test_session_factory, project.id)

        res = await owner_client.get(f"/api/v1/dashboard/manager/{project.id}")

        assert res.status_code == 200
        assert len(res.json()["phases"]) == 1
        assert res.json()["phases"][0]["phase_name"] == "Foundation"

    async def test_worker_cannot_access_manager_dashboard(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await worker_client.get(f"/api/v1/dashboard/manager/{project.id}")

        assert res.status_code == 403

    async def test_unauthenticated_cannot_access_manager_dashboard(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await unauth_client.get(f"/api/v1/dashboard/manager/{project.id}")

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /dashboard/worker
# ---------------------------------------------------------------------------


class TestWorkerDashboard:
    async def test_worker_can_access_own_dashboard(self, worker_client: AsyncClient, seed_users, test_session_factory):
        res = await worker_client.get("/api/v1/dashboard/worker")

        assert res.status_code == 200
        data = res.json()
        assert data["worker_id"] == seed_users["worker"].id
        assert "worker_name" in data
        assert "total_logs" in data
        assert "total_hours_worked" in data
        assert "current_shift_log" in data

    async def test_worker_dashboard_reflects_assigned_project(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)

        res = await worker_client.get("/api/v1/dashboard/worker")

        assert res.status_code == 200
        assert res.json()["assigned_project"] == project.name

    async def test_worker_dashboard_reflects_attendance(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await create_attendance(test_session_factory, log.id, seed_users["worker"].id, hours=8.0)

        res = await worker_client.get("/api/v1/dashboard/worker")

        assert res.status_code == 200
        data = res.json()
        assert data["total_logs"] >= 1
        assert data["total_hours_worked"] >= 8.0

    async def test_worker_with_no_assignment_has_null_project(self, worker_client: AsyncClient, seed_users, test_session_factory):
        # worker not assigned to any project
        res = await worker_client.get("/api/v1/dashboard/worker")

        assert res.status_code == 200
        assert res.json()["assigned_project"] is None

    async def test_owner_can_access_worker_dashboard(self, owner_client: AsyncClient, seed_users, test_session_factory):
        # get_current_user — any authenticated user can hit /worker
        res = await owner_client.get("/api/v1/dashboard/worker")

        assert res.status_code == 200

    async def test_unauthenticated_cannot_access_worker_dashboard(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/dashboard/worker")

        assert res.status_code == 401
