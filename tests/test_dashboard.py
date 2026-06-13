from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    create_daily_log,
    create_role,
    create_user,
    create_worker_assignment,
    get_auth_token,
)

PROJECT_PAYLOAD = {
    "name": "Dashboard Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}


async def setup_dashboard(client: AsyncClient, db: AsyncSession):
    owner_role = await create_role(db, "owner")
    manager_role = await create_role(db, "project_manager")
    worker_role = await create_role(db, "site_worker")

    owner = await create_user(db, owner_role.id, email="owner@test.com")
    manager = await create_user(db, manager_role.id, email="manager@test.com")
    worker = await create_user(db, worker_role.id, email="worker@test.com")

    owner_token = await get_auth_token(client, "owner@test.com", "password123")
    res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
    project_id = res.json()["id"]

    await client.post(
        f"/api/v1/projects/{project_id}/assign-manager",
        json={"user_id": manager.id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    manager_token = await get_auth_token(client, "manager@test.com", "password123")
    worker_token = await get_auth_token(client, "worker@test.com", "password123")

    return {
        "owner": owner,
        "owner_token": owner_token,
        "manager": manager,
        "manager_token": manager_token,
        "worker": worker,
        "worker_token": worker_token,
        "project_id": project_id,
    }


class TestOwnerDashboard:
    async def test_owner_can_access(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get("/api/v1/dashboard/owner", headers={"Authorization": f"Bearer {ctx['owner_token']}"})
        assert res.status_code == 200
        data = res.json()
        assert "total_active_projects" in data
        assert "total_budget" in data
        assert "total_spending" in data
        assert "over_budget_projects" in data
        assert "total_workers_active" in data
        assert "total_material_cost" in data

    async def test_owner_dashboard_reflects_active_projects(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get("/api/v1/dashboard/owner", headers={"Authorization": f"Bearer {ctx['owner_token']}"})
        assert res.status_code == 200
        assert res.json()["total_active_projects"] == 1

    async def test_manager_cannot_access_owner_dashboard(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get("/api/v1/dashboard/owner", headers={"Authorization": f"Bearer {ctx['manager_token']}"})
        assert res.status_code == 403

    async def test_unauthenticated_cannot_access_owner_dashboard(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/dashboard/owner")
        assert res.status_code == 401


class TestManagerDashboard:
    async def test_owner_can_access_any_project_dashboard(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get(
            f"/api/v1/dashboard/manager/{ctx['project_id']}",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["project_id"] == ctx["project_id"]
        assert "logs_submitted" in data
        assert "attendance_rate" in data
        assert "total_material_cost" in data
        assert "total_incidents" in data
        assert "open_incidents" in data
        assert "phases" in data

    async def test_assigned_manager_can_access_dashboard(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get(
            f"/api/v1/dashboard/manager/{ctx['project_id']}",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )
        assert res.status_code == 200
        assert res.json()["project_id"] == ctx["project_id"]

    async def test_unassigned_manager_gets_404(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        manager_role_id = ctx["manager"].role_id
        await create_user(db, manager_role_id, email="manager2@test.com")
        unassigned_token = await get_auth_token(client, "manager2@test.com", "password123")
        res = await client.get(
            f"/api/v1/dashboard/manager/{ctx['project_id']}",
            headers={"Authorization": f"Bearer {unassigned_token}"},
        )
        assert res.status_code == 404

    async def test_project_not_found_returns_404(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get(
            "/api/v1/dashboard/manager/99999",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 404

    async def test_unauthenticated_cannot_access_manager_dashboard(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/dashboard/manager/1")
        assert res.status_code == 401


class TestWorkerDashboard:
    async def test_worker_can_access_own_dashboard(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get("/api/v1/dashboard/worker", headers={"Authorization": f"Bearer {ctx['worker_token']}"})
        assert res.status_code == 200
        data = res.json()
        assert data["worker_id"] == ctx["worker"].id
        assert "total_logs" in data
        assert "total_hours_worked" in data
        assert "current_shift_log" in data

    async def test_worker_with_no_assignment_returns_null_project_and_log(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get("/api/v1/dashboard/worker", headers={"Authorization": f"Bearer {ctx['worker_token']}"})
        assert res.status_code == 200
        assert res.json()["assigned_project"] is None
        assert res.json()["current_shift_log"] is None

    async def test_worker_with_assignment_and_todays_log_returns_current_shift(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)
        today = date.today().isoformat()
        await create_daily_log(db, ctx["project_id"], ctx["owner"].id, today)
        res = await client.get("/api/v1/dashboard/worker", headers={"Authorization": f"Bearer {ctx['worker_token']}"})
        assert res.status_code == 200
        data = res.json()
        assert data["assigned_project"] == PROJECT_PAYLOAD["name"]
        assert data["current_shift_log"] is not None
        assert data["current_shift_log"]["log_date"] == today

    async def test_worker_with_assignment_but_no_todays_log_returns_null_shift(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)
        # log from a past date, not today
        await create_daily_log(db, ctx["project_id"], ctx["owner"].id, "2026-01-01")
        res = await client.get("/api/v1/dashboard/worker", headers={"Authorization": f"Bearer {ctx['worker_token']}"})
        assert res.status_code == 200
        assert res.json()["assigned_project"] == PROJECT_PAYLOAD["name"]
        assert res.json()["current_shift_log"] is None

    async def test_owner_can_access_worker_dashboard(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_dashboard(client, db)
        res = await client.get("/api/v1/dashboard/worker", headers={"Authorization": f"Bearer {ctx['owner_token']}"})
        assert res.status_code == 200

    async def test_unauthenticated_cannot_access_worker_dashboard(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/dashboard/worker")
        assert res.status_code == 401
