import uuid

from httpx import AsyncClient


def unique_email(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@test.com"


async def get_token(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return res.json().get("access_token", "")


class TestAuthLogin:
    async def test_success(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "password123"},
        )
        assert res.status_code == 200
        assert "access_token" in res.json()

    async def test_wrong_password(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@test.com", "password": "wrongpass"},
        )
        assert res.status_code == 401

    async def test_nonexistent_email(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@test.com", "password": "password123"},
        )
        assert res.status_code == 401

    async def test_inactive_user(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.post(
            "/api/v1/auth/login",
            json={"email": "inactive@test.com", "password": "password123"},
        )
        assert res.status_code == 401


class TestAuthMe:
    async def test_valid_token(self, unauth_client: AsyncClient, seed_users):
        token = await get_token(unauth_client, "owner@test.com", "password123")
        res = await unauth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.json()["email"] == "owner@test.com"

    async def test_no_token(self, unauth_client: AsyncClient):
        res = await unauth_client.get("/api/v1/auth/me")
        assert res.status_code == 401

    async def test_invalid_token(self, unauth_client: AsyncClient):
        res = await unauth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert res.status_code == 401


class TestAuthRegister:
    async def test_owner_creates_manager(self, unauth_client: AsyncClient, seed_users):
        token = await get_token(unauth_client, "owner@test.com", "password123")
        res = await unauth_client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email("newmanager"),
                "password": "password123",
                "first_name": "Jane",
                "last_name": "Doe",
                "role_id": seed_users["manager_role"].id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201
        assert res.status_code == 201

    async def test_manager_creates_worker(self, unauth_client: AsyncClient, seed_users):
        token = await get_token(unauth_client, "manager@test.com", "password123")
        res = await unauth_client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email("newworker"),
                "password": "password123",
                "first_name": "Bob",
                "last_name": "Smith",
                "role_id": seed_users["worker_role"].id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 201

    async def test_manager_cannot_create_manager(self, unauth_client: AsyncClient, seed_users):
        token = await get_token(unauth_client, "manager@test.com", "password123")
        res = await unauth_client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email("badmanager"),
                "password": "password123",
                "first_name": "Bad",
                "last_name": "Actor",
                "role_id": seed_users["manager_role"].id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    async def test_duplicate_email(self, unauth_client: AsyncClient, seed_users):
        token = await get_token(unauth_client, "owner@test.com", "password123")
        payload = {
            "email": unique_email("dupuser"),
            "password": "password123",
            "first_name": "Jane",
            "last_name": "Doe",
            "role_id": seed_users["manager_role"].id,
        }
        await unauth_client.post(
            "/api/v1/auth/register",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        res = await unauth_client.post(
            "/api/v1/auth/register",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    async def test_cannot_create_owner(self, unauth_client: AsyncClient, seed_users):
        token = await get_token(unauth_client, "owner@test.com", "password123")
        res = await unauth_client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email("owner2"),
                "password": "password123",
                "first_name": "Bad",
                "last_name": "Actor",
                "role_id": seed_users["owner_role"].id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400

    async def test_unauthenticated(self, unauth_client: AsyncClient, seed_users):
        res = await unauth_client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email("someone"),
                "password": "password123",
                "first_name": "No",
                "last_name": "Auth",
                "role_id": seed_users["owner_role"].id,
            },
        )
        assert res.status_code == 401
