from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import create_role, create_user, get_auth_token

PROJECT_PAYLOAD = {
    "name": "Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}


class TestProjectCreate:
    async def test_owner_can_create(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 201
        assert res.json()["name"] == "Test Project"

    async def test_manager_cannot_create(self, client: AsyncClient, db: AsyncSession):
        await create_role(db, "owner")
        role = await create_role(db, "project_manager")
        await create_user(db, role.id, email="manager@test.com")
        token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient, db: AsyncSession):
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 401


class TestProjectList:
    async def test_owner_sees_all(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        await client.post("/api/v1/projects", json={**PROJECT_PAYLOAD, "name": "Project 2"}, headers={"Authorization": f"Bearer {token}"})
        res = await client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert len(res.json()) == 2

    async def test_manager_sees_only_assigned(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        owner_token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
        project_id = res.json()["id"]
        await client.post(
            f"/api/v1/projects/{project_id}/assign-manager", json={"user_id": manager.id}, headers={"Authorization": f"Bearer {owner_token}"}
        )
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get("/api/v1/projects", headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 200
        assert len(res.json()) == 1


class TestProjectGet:
    async def test_owner_can_get(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.get(f"/api/v1/projects/{project_id}", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200

    async def test_not_found(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.get("/api/v1/projects/99999", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 404

    async def test_manager_access_denied_unassigned(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        owner_token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
        project_id = res.json()["id"]
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get(f"/api/v1/projects/{project_id}", headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 404


class TestProjectUpdate:
    async def test_owner_can_update(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.patch(f"/api/v1/projects/{project_id}", json={"status": "Completed"}, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["status"] == "Completed"

    async def test_manager_cannot_update(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        owner_token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
        project_id = res.json()["id"]
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(f"/api/v1/projects/{project_id}", json={"status": "Completed"}, headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 403


class TestAssignManager:
    async def test_assign_valid_manager(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com")
        manager = await create_user(db, manager_role.id, email="manager@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.post(
            f"/api/v1/projects/{project_id}/assign-manager", json={"user_id": manager.id}, headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 200
        assert res.json()["message"] == "Manager assigned successfully"

    async def test_assign_non_manager_fails(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        worker_role = await create_role(db, "site_worker")
        await create_user(db, owner_role.id, email="owner@test.com")
        worker = await create_user(db, worker_role.id, email="worker@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.post(
            f"/api/v1/projects/{project_id}/assign-manager", json={"user_id": worker.id}, headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 400


class TestPhases:
    async def test_create_phase(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.post(
            f"/api/v1/projects/{project_id}/phases",
            json={"name": "Foundation", "allocated_budget": 500000.0, "status": "Not Started"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201
        assert res.json()["name"] == "Foundation"

    async def test_update_phase(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.post(
            f"/api/v1/projects/{project_id}/phases",
            json={"name": "Foundation", "allocated_budget": 500000.0, "status": "Not Started"},
            headers={"Authorization": f"Bearer {token}"},
        )
        phase_id = res.json()["id"]
        res = await client.patch(
            f"/api/v1/projects/{project_id}/phases/{phase_id}",
            json={"status": "In Progress"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "In Progress"
