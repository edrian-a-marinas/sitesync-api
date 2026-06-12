from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import create_daily_log, create_role, create_user, get_auth_token

PROJECT_PAYLOAD = {
    "name": "Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}

LOG_PAYLOAD = {
    "log_date": "2026-01-01",
    "work_accomplished": "Poured concrete",
    "weather_condition": "Sunny",
    "notes": "No issues",
}


async def setup_owner_and_project(client: AsyncClient, db: AsyncSession):
    owner_role = await create_role(db, "owner")
    owner = await create_user(db, owner_role.id, email="owner@test.com")
    token = await get_auth_token(client, "owner@test.com", "password123")
    res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
    project_id = res.json()["id"]
    return owner, token, project_id


async def setup_manager_assigned(client: AsyncClient, db: AsyncSession, owner_token: str, project_id: int, db_session: AsyncSession):
    manager_role = await create_role(db_session, "project_manager")
    manager = await create_user(db_session, manager_role.id, email="manager@test.com")
    await client.post(
        f"/api/v1/projects/{project_id}/assign-manager",
        json={"user_id": manager.id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    manager_token = await get_auth_token(client, "manager@test.com", "password123")
    return manager, manager_token


class TestDailyLogCreate:
    async def test_owner_can_create(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.post(f"/api/v1/projects/{project_id}/daily-logs", json=LOG_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 201
        assert res.json()["work_accomplished"] == "Poured concrete"

    async def test_manager_can_create_on_assigned_project(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com")
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
        res = await client.post(f"/api/v1/projects/{project_id}/daily-logs", json=LOG_PAYLOAD, headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 201

    async def test_manager_cannot_create_on_unassigned_project(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        owner_token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
        project_id = res.json()["id"]
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.post(f"/api/v1/projects/{project_id}/daily-logs", json=LOG_PAYLOAD, headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 404

    async def test_unauthenticated_cannot_create(self, client: AsyncClient, db: AsyncSession):
        res = await client.post("/api/v1/projects/1/daily-logs", json=LOG_PAYLOAD)
        assert res.status_code == 401


class TestDailyLogList:
    async def test_owner_sees_all_logs(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        owner = await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        await create_daily_log(db, project_id, owner.id, "2026-01-01")
        await create_daily_log(db, project_id, owner.id, "2026-01-02")
        res = await client.get(f"/api/v1/projects/{project_id}/daily-logs", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert len(res.json()) == 2

    async def test_manager_sees_logs_on_assigned_project(self, client: AsyncClient, db: AsyncSession):
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
        await create_daily_log(db, project_id, owner.id, "2026-01-01")
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get(f"/api/v1/projects/{project_id}/daily-logs", headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_manager_gets_empty_on_unassigned_project(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        owner_token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
        project_id = res.json()["id"]
        await create_daily_log(db, project_id, owner.id, "2026-01-01")
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get(f"/api/v1/projects/{project_id}/daily-logs", headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 200
        assert len(res.json()) == 0


class TestDailyLogGet:
    async def test_owner_can_get_log(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        owner = await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        log = await create_daily_log(db, project_id, owner.id)
        res = await client.get(f"/api/v1/projects/{project_id}/daily-logs/{log.id}", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["id"] == log.id

    async def test_manager_can_get_log_on_assigned_project(self, client: AsyncClient, db: AsyncSession):
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
        log = await create_daily_log(db, project_id, owner.id)
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get(f"/api/v1/projects/{project_id}/daily-logs/{log.id}", headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 200

    async def test_manager_denied_on_unassigned_project(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        owner = await create_user(db, owner_role.id, email="owner@test.com")
        await create_user(db, manager_role.id, email="manager@test.com")
        owner_token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {owner_token}"})
        project_id = res.json()["id"]
        log = await create_daily_log(db, project_id, owner.id)
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.get(f"/api/v1/projects/{project_id}/daily-logs/{log.id}", headers={"Authorization": f"Bearer {manager_token}"})
        assert res.status_code == 404

    async def test_log_not_found(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.get(f"/api/v1/projects/{project_id}/daily-logs/99999", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 404


class TestDailyLogUpdate:
    async def test_owner_can_update(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        owner = await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        log = await create_daily_log(db, project_id, owner.id)
        res = await client.patch(
            f"/api/v1/projects/{project_id}/daily-logs/{log.id}",
            json={"work_accomplished": "Updated work"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["work_accomplished"] == "Updated work"

    async def test_manager_can_update_on_assigned_project(self, client: AsyncClient, db: AsyncSession):
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
        log = await create_daily_log(db, project_id, owner.id)
        manager_token = await get_auth_token(client, "manager@test.com", "password123")
        res = await client.patch(
            f"/api/v1/projects/{project_id}/daily-logs/{log.id}",
            json={"work_accomplished": "Manager updated"},
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert res.status_code == 200
        assert res.json()["work_accomplished"] == "Manager updated"

    async def test_update_not_found(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com")
        token = await get_auth_token(client, "owner@test.com", "password123")
        res = await client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers={"Authorization": f"Bearer {token}"})
        project_id = res.json()["id"]
        res = await client.patch(
            f"/api/v1/projects/{project_id}/daily-logs/99999",
            json={"work_accomplished": "Ghost update"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
