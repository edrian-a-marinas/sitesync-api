from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    create_role,
    create_user,
    get_auth_token,
)

PROJECT_PAYLOAD = {
    "name": "Report Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}


async def setup_report(client: AsyncClient, db: AsyncSession):
    owner_role = await create_role(db, "owner")
    manager_role = await create_role(db, "project_manager")

    owner = await create_user(db, owner_role.id, email="owner@test.com")
    manager = await create_user(db, manager_role.id, email="manager@test.com")

    owner_token = await get_auth_token(client, "owner@test.com", "password123")
    res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
    project_id = res.json()["id"]

    await client.post(
        f"/api/v1/projects/{project_id}/assign-manager",
        json={"user_id": manager.id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    manager_token = await get_auth_token(client, "manager@test.com", "password123")

    return {
        "owner": owner,
        "owner_token": owner_token,
        "manager": manager,
        "manager_token": manager_token,
        "project_id": project_id,
    }


class TestTriggerReport:
    async def test_owner_can_trigger_report(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_report(client, db)
        res = await client.post(
            f"/api/v1/reports/{ctx['project_id']}/generate",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 202

    async def test_assigned_manager_can_trigger_report(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_report(client, db)
        res = await client.post(
            f"/api/v1/reports/{ctx['project_id']}/generate",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )
        assert res.status_code == 202

    async def test_unassigned_manager_cannot_trigger_report(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_report(client, db)
        manager_role_id = ctx["manager"].role_id
        await create_user(db, manager_role_id, email="manager2@test.com")
        unassigned_token = await get_auth_token(client, "manager2@test.com", "password123")
        res = await client.post(
            f"/api/v1/reports/{ctx['project_id']}/generate",
            headers={"Authorization": f"Bearer {unassigned_token}"},
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_trigger_report(self, client: AsyncClient, db: AsyncSession):
        res = await client.post("/api/v1/reports/1/generate")
        assert res.status_code == 401


class TestGetReports:
    async def test_owner_can_list_reports(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_report(client, db)
        res = await client.get(
            f"/api/v1/reports/{ctx['project_id']}",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    async def test_assigned_manager_can_list_reports(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_report(client, db)
        res = await client.get(
            f"/api/v1/reports/{ctx['project_id']}",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    async def test_unassigned_manager_cannot_list_reports(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_report(client, db)
        manager_role_id = ctx["manager"].role_id
        await create_user(db, manager_role_id, email="manager2@test.com")
        unassigned_token = await get_auth_token(client, "manager2@test.com", "password123")
        res = await client.get(
            f"/api/v1/reports/{ctx['project_id']}",
            headers={"Authorization": f"Bearer {unassigned_token}"},
        )
        assert res.status_code == 403

    async def test_empty_list_when_no_reports(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_report(client, db)
        res = await client.get(
            f"/api/v1/reports/{ctx['project_id']}",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list_reports(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/reports/1")
        assert res.status_code == 401
