from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    create_role,
    create_user,
    get_auth_token,
)

QUERY_PAYLOAD = {
    "question": "Which project consumed the most cement this month?",
    "project_id": None,
}


async def setup_ai_query(client: AsyncClient, db: AsyncSession):
    owner_role = await create_role(db, "owner")
    manager_role = await create_role(db, "project_manager")

    owner = await create_user(db, owner_role.id, email="owner@test.com")
    await create_user(db, manager_role.id, email="manager@test.com")

    owner_token = await get_auth_token(client, "owner@test.com", "password123")
    manager_token = await get_auth_token(client, "manager@test.com", "password123")

    return {
        "owner": owner,
        "owner_token": owner_token,
        "manager_token": manager_token,
    }


class TestCreateQuery:
    async def test_owner_can_submit_query(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ai_query(client, db)
        res = await client.post(
            "/api/v1/ai/query",
            json=QUERY_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["question"] == QUERY_PAYLOAD["question"]
        assert data["status"] == "Pending"
        assert data["answer"] is None
        assert data["user_id"] == ctx["owner"].id

    async def test_owner_can_submit_query_with_project_id(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ai_query(client, db)
        # Create a real project first so the FK constraint is satisfied
        project_res = await client.post(
            "/api/v1/projects",
            json={
                "name": "Test Project",
                "location": "Manila",
                "total_budget": 1000000.0,
                "start_date": "2026-01-01",
                "target_end_date": "2026-12-31",
                "status": "Active",
            },
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        project_id = project_res.json()["id"]
        res = await client.post(
            "/api/v1/ai/query",
            json={"question": "What is the budget status?", "project_id": project_id},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 201
        assert res.json()["project_id"] == project_id

    async def test_manager_cannot_submit_query(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ai_query(client, db)
        res = await client.post(
            "/api/v1/ai/query",
            json=QUERY_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['manager_token']}"},
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_submit_query(self, client: AsyncClient, db: AsyncSession):
        res = await client.post("/api/v1/ai/query", json=QUERY_PAYLOAD)
        assert res.status_code == 401


class TestGetQuery:
    async def test_owner_can_get_own_query(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ai_query(client, db)
        create_res = await client.post(
            "/api/v1/ai/query",
            json=QUERY_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        query_id = create_res.json()["id"]
        res = await client.get(
            f"/api/v1/ai/query/{query_id}",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        assert res.json()["id"] == query_id

    async def test_owner_cannot_get_another_users_query(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner1@test.com")
        await create_user(db, owner_role.id, email="owner2@test.com")
        token1 = await get_auth_token(client, "owner1@test.com", "password123")
        token2 = await get_auth_token(client, "owner2@test.com", "password123")
        create_res = await client.post(
            "/api/v1/ai/query",
            json=QUERY_PAYLOAD,
            headers={"Authorization": f"Bearer {token1}"},
        )
        query_id = create_res.json()["id"]
        res = await client.get(
            f"/api/v1/ai/query/{query_id}",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert res.status_code == 404

    async def test_query_not_found_returns_404(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ai_query(client, db)
        res = await client.get(
            "/api/v1/ai/query/99999",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 404

    async def test_unauthenticated_cannot_get_query(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/ai/query/1")
        assert res.status_code == 401


class TestListQueries:
    async def test_owner_can_list_queries(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ai_query(client, db)
        await client.post(
            "/api/v1/ai/query",
            json=QUERY_PAYLOAD,
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        await client.post(
            "/api/v1/ai/query",
            json={"question": "Which site had the most incidents?", "project_id": None},
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        res = await client.get(
            "/api/v1/ai/queries",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        assert len(res.json()) == 2

    async def test_owner_sees_only_own_queries(self, client: AsyncClient, db: AsyncSession):
        owner_role = await create_role(db, "owner")
        await create_user(db, owner_role.id, email="owner1@test.com")
        await create_user(db, owner_role.id, email="owner2@test.com")
        token1 = await get_auth_token(client, "owner1@test.com", "password123")
        token2 = await get_auth_token(client, "owner2@test.com", "password123")
        await client.post(
            "/api/v1/ai/query",
            json=QUERY_PAYLOAD,
            headers={"Authorization": f"Bearer {token1}"},
        )
        res = await client.get(
            "/api/v1/ai/queries",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert res.status_code == 200
        assert len(res.json()) == 0

    async def test_empty_list_when_no_queries(self, client: AsyncClient, db: AsyncSession):
        ctx = await setup_ai_query(client, db)
        res = await client.get(
            "/api/v1/ai/queries",
            headers={"Authorization": f"Bearer {ctx['owner_token']}"},
        )
        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list_queries(self, client: AsyncClient, db: AsyncSession):
        res = await client.get("/api/v1/ai/queries")
        assert res.status_code == 401
