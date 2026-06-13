from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.role import Role
from tests.conftest import (
    create_daily_log,
    create_role,
    create_user,
    create_worker_assignment,
    get_auth_token,
)

PROJECT_PAYLOAD = {
    "name": "Attendance Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}


# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------


async def setup_project_with_manager_and_worker(client: AsyncClient, db: AsyncSession):
    """
    Creates owner, manager, worker.
    Owner creates project, assigns manager.
    Returns all IDs and tokens needed by tests.
    """
    owner_role = await create_role(db, "owner")
    manager_role = await create_role(db, "project_manager")
    worker_role = await create_role(db, "site_worker")

    owner = await create_user(db, owner_role.id, email="owner@test.com")
    manager = await create_user(db, manager_role.id, email="manager@test.com")
    worker = await create_user(db, worker_role.id, email="worker@test.com")

    owner_token = await get_auth_token(client, "owner@test.com", "password123")

    res = await client.post(
        "/api/v1/projects",
        json=PROJECT_PAYLOAD,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    project_id = res.json()["id"]

    await client.post(
        f"/api/v1/projects/{project_id}/assign-manager",
        json={"user_id": manager.id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    manager_token = await get_auth_token(client, "manager@test.com", "password123")

    log = await create_daily_log(db, project_id, owner.id, "2026-01-01")

    return {
        "owner": owner,
        "owner_token": owner_token,
        "manager": manager,
        "manager_token": manager_token,
        "worker": worker,
        "project_id": project_id,
        "log_id": log.id,
    }


# ---------------------------------------------------------------------------
# Submit Attendance
# ---------------------------------------------------------------------------


class TestAttendanceSubmit:
    async def test_owner_can_submit_attendance(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 201
        assert res.json()["worker_id"] == ctx["worker"].id
        assert res.json()["hours_worked"] == 8.0

    async def test_assigned_manager_can_submit_attendance(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 9.0},
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )

        assert res.status_code == 201
        assert res.json()["daily_log_id"] == ctx["log_id"]

    async def test_worker_not_assigned_to_project_returns_400(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        # Intentionally skip create_worker_assignment

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 400

    async def test_duplicate_submission_returns_400(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        payload = {"worker_id": ctx["worker"].id, "hours_worked": 8.0}
        url = f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance"

        # First submission via HTTP — goes through its own session via dependency override
        res1 = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res1.status_code == 201

        # Second submission — same worker same log, should be rejected
        res2 = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res2.status_code == 400

    async def test_invalid_log_id_returns_400(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/99999/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 400

    async def test_unauthenticated_cannot_submit(self, client: AsyncClient, db: AsyncSession):
        res = await client.post(
            "/api/v1/projects/1/daily-logs/1/attendance",
            json={"worker_id": 1, "hours_worked": 8.0},
        )

        assert res.status_code == 401

    async def test_unassigned_manager_cannot_submit(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        # Reuse existing project_manager role
        from sqlalchemy.future import select

        from app.models.role import Role

        manager_role = (await db.execute(select(Role).where(Role.name == "project_manager"))).scalar_one()
        await create_user(db, manager_role.id, email="manager2@test.com")
        unassigned_token = await get_auth_token(client, "manager2@test.com", "password123")

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {unassigned_token}"},
        )

        # Unassigned manager gets blocked by require_owner_or_manager dependency
        assert res.status_code in [400, 403]


# ---------------------------------------------------------------------------
# Get Attendance
# ---------------------------------------------------------------------------


class TestAttendanceGet:
    async def test_owner_can_get_attendance(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["worker_id"] == ctx["worker"].id

    async def test_assigned_manager_can_get_attendance(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )

        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_invalid_log_returns_empty_list(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/99999/attendance",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_get(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/projects/1/daily-logs/1/attendance")

        assert res.status_code == 401

    async def test_worker_can_see_own_attendance(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        # Submit attendance for the worker
        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        worker_token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            headers={"Authorization": f"Bearer {worker_token}"},
        )

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["worker_id"] == ctx["worker"].id

    async def test_worker_cannot_see_other_workers_attendance(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        # Assign both workers to project
        worker_role = (await db.execute(select(Role).where(Role.name == "site_worker"))).scalar_one()
        other_worker = await create_user(db, worker_role.id, email="worker2@test.com")
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)
        await create_worker_assignment(db, ctx["project_id"], other_worker.id)

        # Submit attendance for both workers
        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": ctx["worker"].id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            json={"worker_id": other_worker.id, "hours_worked": 8.0},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        # Worker 1 should only see their own record
        worker_token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/attendance",
            headers={"Authorization": f"Bearer {worker_token}"},
        )

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["worker_id"] == ctx["worker"].id
