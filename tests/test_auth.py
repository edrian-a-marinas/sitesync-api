from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import create_role, create_user


async def get_token(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json().get("access_token", "")


class TestAuthLogin:
    async def test_success(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com", password="password123")

        res = await client.post("/api/v1/auth/login", json={"email": "owner@test.com", "password": "password123"})
        assert res.status_code == 200
        assert "access_token" in res.json()

    async def test_wrong_password(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com", password="password123")

        res = await client.post("/api/v1/auth/login", json={"email": "owner@test.com", "password": "wrongpass"})
        assert res.status_code == 401

    async def test_nonexistent_email(self, client: AsyncClient, db: AsyncSession):
        res = await client.post("/api/v1/auth/login", json={"email": "ghost@test.com", "password": "password123"})
        assert res.status_code == 401

    async def test_inactive_user(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="inactive@test.com", password="password123", is_active=False)

        res = await client.post("/api/v1/auth/login", json={"email": "inactive@test.com", "password": "password123"})
        assert res.status_code == 401


class TestAuthMe:
    async def test_valid_token(self, client: AsyncClient, db: AsyncSession):
        role = await create_role(db, "owner")
        await create_user(db, role.id, email="owner@test.com", password="password123")

        token = await get_token(client, "owner@test.com", "password123")
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "owner@test.com"

    async def test_no_token(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/auth/me")
        assert res.status_code == 401

    async def test_invalid_token(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert res.status_code == 401


class TestAuthRegister:
    async def test_owner_creates_manager(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com", password="password123")

        token = await get_token(client, "owner@test.com", "password123")
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "manager@test.com",
                "password": "password123",
                "first_name": "Jane",
                "last_name": "Doe",
                "role_id": manager_role.id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201
        assert res.json()["email"] == "manager@test.com"

    async def test_manager_creates_worker(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        worker_role = await create_role(db, "site_worker")
        await create_user(db, owner_role.id, email="owner@test.com", password="password123")
        await create_user(db, manager_role.id, email="manager@test.com", password="password123")

        token = await get_token(client, "manager@test.com", "password123")
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "worker@test.com",
                "password": "password123",
                "first_name": "Bob",
                "last_name": "Smith",
                "role_id": worker_role.id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201

    async def test_manager_cannot_create_manager(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_role(db, "site_worker")
        await create_user(db, owner_role.id, email="owner@test.com", password="password123")
        await create_user(db, manager_role.id, email="manager@test.com", password="password123")

        token = await get_token(client, "manager@test.com", "password123")
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "manager2@test.com",
                "password": "password123",
                "first_name": "Bad",
                "last_name": "Actor",
                "role_id": manager_role.id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    async def test_duplicate_email(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        manager_role = await create_role(db, "project_manager")
        await create_user(db, owner_role.id, email="owner@test.com", password="password123")

        token = await get_token(client, "owner@test.com", "password123")
        payload = {
            "email": "manager@test.com",
            "password": "password123",
            "first_name": "Jane",
            "last_name": "Doe",
            "role_id": manager_role.id,
        }
        await client.post("/api/v1/auth/register", json=payload, headers={"Authorization": f"Bearer {token}"})
        res = await client.post("/api/v1/auth/register", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 400

    async def test_cannot_create_owner(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner@test.com", password="password123")

        token = await get_token(client, "owner@test.com", "password123")
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "owner2@test.com",
                "password": "password123",
                "first_name": "Bad",
                "last_name": "Actor",
                "role_id": owner_role.id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    async def test_unauthenticated(self, client: AsyncClient, db: AsyncSession):
        res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "someone@test.com",
                "password": "password123",
                "first_name": "No",
                "last_name": "Auth",
                "role_id": 1,
            },
        )
        assert res.status_code == 401
