from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment, ProjectPhase, WorkerAssignment

# ---------------------------------------------------------------------------
# Session-scoped seeds
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_owner_dashboard(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            p1 = Project(
                owner_id=seed_users["owner"].id,
                name="Dash Project A",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            p2 = Project(
                owner_id=seed_users["owner"].id,
                name="Dash Project B",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([p1, p2])
            await session.flush()
            log = DailyLog(project_id=p1.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 6, 16), work_accomplished="Test work")
            session.add(log)
            await session.flush()
            session.add(Material(daily_log_id=log.id, name="Cement", quantity=10.0, unit="bags", unit_cost=250.0))
    yield {"p1": p1, "p2": p2, "log": log}
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Material).where(Material.daily_log_id == log.id))
            await session.execute(delete(DailyLog).where(DailyLog.id == log.id))
            await session.execute(delete(Project).where(Project.id.in_([p1.id, p2.id])))


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_manager_dashboard(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            p = Project(
                owner_id=seed_users["owner"].id,
                name="Mgr Dash Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(p)
            await session.flush()
            assignment = ProjectAssignment(project_id=p.id, user_id=seed_users["manager"].id)
            log = DailyLog(project_id=p.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 1, 1), work_accomplished="Test work")
            session.add_all([assignment, log])
            await session.flush()
            incident = Incident(daily_log_id=log.id, reported_by=seed_users["owner"].id, description="Test incident", severity="High", status="Open")
            phase = ProjectPhase(project_id=p.id, name="Foundation", allocated_budget=500_000, status="In Progress")
            session.add_all([incident, phase])
    yield {"project": p, "log": log, "phase": phase, "incident": incident}
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Incident).where(Incident.daily_log_id == log.id))
            await session.execute(delete(ProjectPhase).where(ProjectPhase.project_id == p.id))
            await session.execute(delete(DailyLog).where(DailyLog.id == log.id))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id == p.id))
            await session.execute(delete(Project).where(Project.id == p.id))


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_manager_aggregate_dashboard(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            p1 = Project(
                owner_id=seed_users["owner"].id,
                name="Agg Dash Project A",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            p2 = Project(
                owner_id=seed_users["owner"].id,
                name="Agg Dash Project B",
                location="Manila",
                total_budget=2_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([p1, p2])
            await session.flush()
            a1 = ProjectAssignment(project_id=p1.id, user_id=seed_users["manager"].id)
            a2 = ProjectAssignment(project_id=p2.id, user_id=seed_users["manager"].id)
            log1 = DailyLog(project_id=p1.id, submitted_by=seed_users["manager"].id, log_date=date(2026, 6, 16), work_accomplished="Work A")
            log2 = DailyLog(project_id=p2.id, submitted_by=seed_users["manager"].id, log_date=date(2026, 6, 17), work_accomplished="Work B")
            session.add_all([a1, a2, log1, log2])
            await session.flush()
            session.add(Material(daily_log_id=log1.id, name="Cement", quantity=10.0, unit="bags", unit_cost=250.0))
            session.add(Material(daily_log_id=log2.id, name="Steel", quantity=5.0, unit="bars", unit_cost=500.0))
    yield {"p1": p1, "p2": p2, "log1": log1, "log2": log2}
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Material).where(Material.daily_log_id.in_([log1.id, log2.id])))
            await session.execute(delete(DailyLog).where(DailyLog.id.in_([log1.id, log2.id])))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id.in_([p1.id, p2.id])))
            await session.execute(delete(Project).where(Project.id.in_([p1.id, p2.id])))


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_worker_dashboard(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            p = Project(
                owner_id=seed_users["owner"].id,
                name="Worker Dash Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(p)
            await session.flush()
            assignment = WorkerAssignment(project_id=p.id, user_id=seed_users["worker"].id)
            log = DailyLog(project_id=p.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 1, 1), work_accomplished="Test work")
            session.add_all([assignment, log])
            await session.flush()
            attendance = Attendance(daily_log_id=log.id, worker_id=seed_users["worker"].id, hours_worked=8.0)
            session.add(attendance)
    yield {"project": p, "log": log, "attendance": attendance}
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Attendance).where(Attendance.daily_log_id == log.id))
            await session.execute(delete(DailyLog).where(DailyLog.id == log.id))
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id == p.id))
            await session.execute(delete(Project).where(Project.id == p.id))


# ---------------------------------------------------------------------------
# GET /dashboard/owner
# ---------------------------------------------------------------------------


class TestOwnerDashboard:
    async def test_owner_can_access_dashboard(self, owner_client: AsyncClient, seed_owner_dashboard):
        res = await owner_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 200
        data = res.json()
        assert "total_active_projects" in data
        assert "total_budget" in data
        assert "total_spending" in data
        assert "over_budget_projects" in data
        assert "all_projects_budget" in data
        assert "material_trends" in data
        assert "total_workers_active" in data
        assert "total_material_cost" in data

    async def test_owner_dashboard_includes_delta_fields(self, owner_client: AsyncClient, seed_owner_dashboard):
        res = await owner_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 200
        data = res.json()
        assert "total_spending_delta_percent" in data
        assert "total_workers_active_delta" in data
        assert "incidents_this_week_delta" in data

    async def test_owner_dashboard_counts_active_projects(self, owner_client: AsyncClient, seed_owner_dashboard):
        res = await owner_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 200
        assert res.json()["total_active_projects"] >= 2

    async def test_owner_dashboard_reflects_material_cost(self, owner_client: AsyncClient, seed_owner_dashboard):
        res = await owner_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 200
        assert res.json()["total_material_cost"] >= 2500.0

    async def test_owner_dashboard_includes_all_projects_budget(self, owner_client: AsyncClient, seed_owner_dashboard):
        res = await owner_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data["all_projects_budget"], list)
        assert len(data["all_projects_budget"]) >= 2
        for proj in data["all_projects_budget"]:
            assert "project_id" in proj
            assert "project_name" in proj
            assert "total_budget" in proj
            assert "actual_spending" in proj
            assert "is_over_budget" in proj

    async def test_owner_dashboard_includes_material_trends(self, owner_client: AsyncClient, seed_owner_dashboard):
        res = await owner_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data["material_trends"], list)
        if data["material_trends"]:
            for trend in data["material_trends"]:
                assert "week" in trend
                assert "material_name" in trend
                assert "total_cost" in trend

    async def test_owner_dashboard_year_filter_scopes_projects(self, owner_client: AsyncClient, seed_owner_dashboard):
        res = await owner_client.get("/api/v1/dashboard/owner?year=2026")
        assert res.status_code == 200
        data = res.json()
        assert "total_active_projects" in data
        assert "total_workers_active" in data
        assert "incidents_this_week" in data
        assert isinstance(data["all_projects_budget"], list)
        for proj in data["all_projects_budget"]:
            assert "project_id" in proj
            assert "actual_spending" in proj

    async def test_manager_cannot_access_owner_dashboard(self, manager_client: AsyncClient):
        res = await manager_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 403

    async def test_worker_cannot_access_owner_dashboard(self, worker_client: AsyncClient):
        res = await worker_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access_owner_dashboard(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/dashboard/owner")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /dashboard/manager/{project_id}
# ---------------------------------------------------------------------------


class TestManagerDashboard:
    async def test_owner_can_access_manager_dashboard(self, owner_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await owner_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["project_id"] == p.id
        assert data["project_name"] == p.name
        assert "logs_submitted" in data
        assert "attendance_rate" in data
        assert "total_material_cost" in data
        assert "total_incidents" in data
        assert "open_incidents" in data
        assert "phases" in data

    async def test_manager_dashboard_includes_delta_fields(self, owner_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await owner_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 200
        data = res.json()
        assert "logs_submitted_delta" in data
        assert "attendance_rate_delta" in data
        assert "total_spending_delta_percent" in data
        assert "incidents_this_week_delta" in data

    async def test_assigned_manager_can_access_dashboard(self, manager_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await manager_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 200
        assert res.json()["project_id"] == p.id

    async def test_unassigned_manager_gets_404(self, manager_client: AsyncClient, test_session_factory, seed_users):
        # needs its own isolated project with no assignment
        async with test_session_factory() as session:
            async with session.begin():
                p = Project(
                    owner_id=seed_users["owner"].id,
                    name="Unassigned Project",
                    location="Manila",
                    total_budget=1_000_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(p)
        res = await manager_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 404
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(Project).where(Project.id == p.id))

    async def test_nonexistent_project_returns_404(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/dashboard/manager/99999")
        assert res.status_code == 404

    async def test_dashboard_reflects_logs_and_incidents(self, owner_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await owner_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["logs_submitted"] >= 1
        assert data["total_incidents"] >= 1
        assert data["open_incidents"] >= 1

    async def test_dashboard_includes_phases(self, owner_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await owner_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 200
        phases = res.json()["phases"]
        assert any(ph["phase_name"] == "Foundation" for ph in phases)

    async def test_manager_dashboard_includes_material_trends(self, owner_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await owner_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data["material_trends"], list)

    async def test_worker_cannot_access_manager_dashboard(self, worker_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await worker_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access_manager_dashboard(self, unauth_client: AsyncClient, seed_manager_dashboard):
        p = seed_manager_dashboard["project"]
        res = await unauth_client.get(f"/api/v1/dashboard/manager/{p.id}")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /dashboard/worker
# ---------------------------------------------------------------------------


class TestWorkerDashboard:
    async def test_worker_can_access_own_dashboard(self, worker_client: AsyncClient, seed_users, seed_worker_dashboard):
        res = await worker_client.get("/api/v1/dashboard/worker")
        assert res.status_code == 200
        data = res.json()
        assert data["worker_id"] == seed_users["worker"].id
        assert "worker_name" in data
        assert "total_logs" in data
        assert "total_hours_worked" in data
        assert "current_shift_log" in data

    async def test_worker_dashboard_reflects_assigned_project(self, worker_client: AsyncClient, seed_worker_dashboard):
        res = await worker_client.get("/api/v1/dashboard/worker")
        assert res.status_code == 200
        assert res.json()["assigned_project"] == seed_worker_dashboard["project"].name

    async def test_worker_dashboard_reflects_attendance(self, worker_client: AsyncClient, seed_worker_dashboard):
        res = await worker_client.get("/api/v1/dashboard/worker")
        assert res.status_code == 200
        data = res.json()
        assert data["total_logs"] >= 1
        assert data["total_hours_worked"] >= 8.0

    async def test_owner_can_access_worker_dashboard(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/dashboard/worker")
        assert res.status_code == 200

    async def test_unauthenticated_cannot_access_worker_dashboard(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/dashboard/worker")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /dashboard/manager/aggregate
# ---------------------------------------------------------------------------
class TestManagerAggregateDashboard:
    async def test_manager_can_access_aggregate_dashboard(self, manager_client: AsyncClient, seed_manager_aggregate_dashboard):
        res = await manager_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 200
        data = res.json()
        assert "total_logs_submitted" in data
        assert "total_budget" in data
        assert "total_spending" in data
        assert "average_attendance_rate" in data
        assert "incidents_this_week" in data
        assert "over_budget_projects" in data
        assert "all_projects_budget" in data
        assert "material_trends" in data

    async def test_aggregate_dashboard_includes_delta_fields(self, manager_client: AsyncClient, seed_manager_aggregate_dashboard):
        res = await manager_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 200
        data = res.json()
        assert "total_logs_submitted_delta" in data
        assert "total_spending_delta_percent" in data
        assert "average_attendance_rate_delta" in data
        assert "incidents_this_week_delta" in data

    async def test_aggregate_reflects_multiple_projects(self, manager_client: AsyncClient, seed_manager_aggregate_dashboard):
        res = await manager_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 200
        data = res.json()
        assert data["total_logs_submitted"] >= 2
        assert data["total_budget"] >= 3_000_000

    async def test_aggregate_dashboard_includes_all_projects_budget(self, manager_client: AsyncClient, seed_manager_aggregate_dashboard):
        res = await manager_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data["all_projects_budget"], list)
        assert len(data["all_projects_budget"]) >= 2
        for proj in data["all_projects_budget"]:
            assert "project_id" in proj
            assert "project_name" in proj
            assert "total_budget" in proj
            assert "actual_spending" in proj
            assert "is_over_budget" in proj

    async def test_aggregate_dashboard_includes_material_trends(self, manager_client: AsyncClient, seed_manager_aggregate_dashboard):
        res = await manager_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data["material_trends"], list)
        if data["material_trends"]:
            for trend in data["material_trends"]:
                assert "week" in trend
                assert "material_name" in trend
                assert "total_cost" in trend

    async def test_owner_can_access_aggregate_dashboard(self, owner_client: AsyncClient):
        res = await owner_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 200

    async def test_worker_cannot_access_aggregate_dashboard(self, worker_client: AsyncClient):
        res = await worker_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access_aggregate_dashboard(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/dashboard/manager/aggregate")
        assert res.status_code == 401
