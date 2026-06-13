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
    "name": "Equipment Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}

EQUIPMENT_PAYLOAD = {
    "name": "Concrete Mixer",
    "quantity": 2,
    "condition": "Good",
}

EQUIPMENT_UPDATE_PAYLOAD = {
    "condition": "Needs Repair",
}


# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------


async def setup_project_with_manager_and_worker(client: AsyncClient, db: AsyncSession):
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
# List Equipment
# ---------------------------------------------------------------------------


class TestEquipmentList:
    async def test_owner_can_list_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["name"] == "Concrete Mixer"

    async def test_assigned_manager_can_list_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_assigned_worker_can_list_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        worker_token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            headers={"Authorization": f"Bearer {worker_token}"},
        )

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_unassigned_worker_gets_empty_list(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        worker_token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.get(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            headers={"Authorization": f"Bearer {worker_token}"},
        )

        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/projects/1/daily-logs/1/equipment")
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Create Equipment
# ---------------------------------------------------------------------------


class TestEquipmentCreate:
    async def test_owner_can_create_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 201
        assert res.json()["name"] == "Concrete Mixer"
        assert res.json()["daily_log_id"] == ctx["log_id"]

    async def test_assigned_manager_can_create_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )

        assert res.status_code == 201
        assert res.json()["daily_log_id"] == ctx["log_id"]

    async def test_unassigned_manager_cannot_create_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        manager_role = (await db.execute(select(Role).where(Role.name == "project_manager"))).scalar_one()
        await create_user(db, manager_role.id, email="manager2@test.com")
        unassigned_token = await get_auth_token(client, "manager2@test.com", "password123")

        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {unassigned_token}"},
        )

        assert res.status_code == 403

    async def test_worker_cannot_create_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        worker_token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {worker_token}"},
        )

        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, client: AsyncClient, db: AsyncSession):
        res = await client.post(
            "/api/v1/projects/1/daily-logs/1/equipment",
            json=EQUIPMENT_PAYLOAD,
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# Update Equipment
# ---------------------------------------------------------------------------


class TestEquipmentUpdate:
    async def test_owner_can_update_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        create_res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        equipment_id = create_res.json()["id"]

        res = await client.patch(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment/{equipment_id}",
            json=EQUIPMENT_UPDATE_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 200
        assert res.json()["condition"] == "Needs Repair"

    async def test_assigned_manager_can_update_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        create_res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        equipment_id = create_res.json()["id"]

        res = await client.patch(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment/{equipment_id}",
            json=EQUIPMENT_UPDATE_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )

        assert res.status_code == 200
        assert res.json()["condition"] == "Needs Repair"

    async def test_unassigned_manager_cannot_update_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        create_res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        equipment_id = create_res.json()["id"]

        manager_role = (await db.execute(select(Role).where(Role.name == "project_manager"))).scalar_one()
        await create_user(db, manager_role.id, email="manager2@test.com")
        unassigned_token = await get_auth_token(client, "manager2@test.com", "password123")

        res = await client.patch(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment/{equipment_id}",
            json=EQUIPMENT_UPDATE_PAYLOAD,
            headers={"Authorization": f"Bearer {unassigned_token}"},
        )

        assert res.status_code == 403

    async def test_update_equipment_not_found(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)

        res = await client.patch(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment/99999",
            json=EQUIPMENT_UPDATE_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )

        assert res.status_code == 404

    async def test_worker_cannot_update_equipment(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_project_with_manager_and_worker(client, db)
        await create_worker_assignment(db, ctx["project_id"], ctx["worker"].id)

        create_res = await client.post(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment",
            json=EQUIPMENT_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        equipment_id = create_res.json()["id"]

        worker_token = await get_auth_token(client, "worker@test.com", "password123")
        res = await client.patch(
            f"/api/v1/projects/{ctx['project_id']}/daily-logs/{ctx['log_id']}/equipment/{equipment_id}",
            json=EQUIPMENT_UPDATE_PAYLOAD,
            headers={"Authorization": f"Bearer {worker_token}"},
        )

        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, client: AsyncClient, db: AsyncSession):
        res = await client.patch(
            "/api/v1/projects/1/daily-logs/1/equipment/1",
            json=EQUIPMENT_UPDATE_PAYLOAD,
        )
        assert res.status_code == 401
