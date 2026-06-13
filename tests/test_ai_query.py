from datetime import date
from unittest.mock import patch

from httpx import AsyncClient

from app.models.ai_query import AIQuery
from app.models.project import Project

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AI_QUERY_URL = "/api/v1/ai/query"
AI_QUERIES_URL = "/api/v1/ai/queries"


def query_detail_url(query_id: int) -> str:
    return f"/api/v1/ai/query/{query_id}"


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="AI Query Test Project",
            location="Manila",
            total_budget=1_000_000,
            start_date=date(2026, 1, 1),
            target_end_date=date(2026, 12, 31),
            status="Active",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def create_query_in_db(
    session_factory,
    user_id: int,
    question: str = "Which project used the most cement?",
    status: str = "Done",
    answer: str = "Project A used the most cement.",
    project_id: int | None = None,
) -> AIQuery:
    async with session_factory() as session:
        query = AIQuery(
            user_id=user_id,
            project_id=project_id,
            question=question,
            answer=answer,
            status=status,
        )
        session.add(query)
        await session.commit()
        await session.refresh(query)
        return query


# ---------------------------------------------------------------------------
# POST /ai/query  (create)
# ---------------------------------------------------------------------------


class TestCreateAIQuery:
    async def test_owner_can_submit_query(self, owner_client: AsyncClient, seed_users, test_session_factory):
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Which project used the most cement?"},
            )

        assert res.status_code == 201
        data = res.json()
        assert data["question"] == "Which project used the most cement?"
        assert data["status"] == "Pending"
        assert data["answer"] is None
        assert data["user_id"] == seed_users["owner"].id
        mock_task.delay.assert_called_once_with(data["id"])

    async def test_query_with_project_id_scoped(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "What is the budget status?", "project_id": project.id},
            )

        assert res.status_code == 201
        assert res.json()["project_id"] == project.id

    async def test_query_without_project_id_is_cross_project(self, owner_client: AsyncClient, seed_users, test_session_factory):
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Which site had the most incidents this quarter?"},
            )

        assert res.status_code == 201
        assert res.json()["project_id"] is None

    async def test_manager_cannot_submit_query(self, manager_client: AsyncClient, seed_users, test_session_factory):
        res = await manager_client.post(
            AI_QUERY_URL,
            json={"question": "Which project used the most cement?"},
        )

        assert res.status_code == 403

    async def test_worker_cannot_submit_query(self, worker_client: AsyncClient, seed_users, test_session_factory):
        res = await worker_client.post(
            AI_QUERY_URL,
            json={"question": "Which project used the most cement?"},
        )

        assert res.status_code == 403

    async def test_unauthenticated_cannot_submit_query(self, unauth_client: AsyncClient):
        res = await unauth_client.post(
            AI_QUERY_URL,
            json={"question": "Which project used the most cement?"},
        )

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /ai/query/{query_id}  (get single)
# ---------------------------------------------------------------------------


class TestGetAIQuery:
    async def test_owner_can_get_own_query(self, owner_client: AsyncClient, seed_users, test_session_factory):
        query = await create_query_in_db(test_session_factory, seed_users["owner"].id)

        res = await owner_client.get(query_detail_url(query.id))

        assert res.status_code == 200
        data = res.json()
        assert data["id"] == query.id
        assert data["question"] == query.question
        assert data["status"] == "Done"
        assert data["answer"] == "Project A used the most cement."

    async def test_pending_query_has_null_answer(self, owner_client: AsyncClient, seed_users, test_session_factory):
        query = await create_query_in_db(
            test_session_factory,
            seed_users["owner"].id,
            status="Pending",
            answer=None,
        )

        res = await owner_client.get(query_detail_url(query.id))

        assert res.status_code == 200
        assert res.json()["status"] == "Pending"
        assert res.json()["answer"] is None

    async def test_owner_cannot_get_another_users_query(self, owner_client: AsyncClient, seed_users, test_session_factory):
        # Create query under a different user_id (manager, even though they can't submit via API)
        query = await create_query_in_db(test_session_factory, seed_users["manager"].id)

        res = await owner_client.get(query_detail_url(query.id))

        # service filters by user_id — returns None → 404
        assert res.status_code == 404

    async def test_nonexistent_query_returns_404(self, owner_client: AsyncClient, seed_users, test_session_factory):
        res = await owner_client.get(query_detail_url(99999))

        assert res.status_code == 404

    async def test_manager_cannot_get_query(self, manager_client: AsyncClient, seed_users, test_session_factory):
        query = await create_query_in_db(test_session_factory, seed_users["owner"].id)

        res = await manager_client.get(query_detail_url(query.id))

        assert res.status_code == 403

    async def test_unauthenticated_cannot_get_query(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        res = await unauth_client.get(query_detail_url(1))

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /ai/queries  (list all)
# ---------------------------------------------------------------------------


class TestGetAIQueries:
    async def test_owner_can_list_own_queries(self, owner_client: AsyncClient, seed_users, test_session_factory):
        await create_query_in_db(test_session_factory, seed_users["owner"].id, question="Q1")
        await create_query_in_db(test_session_factory, seed_users["owner"].id, question="Q2")

        res = await owner_client.get(AI_QUERIES_URL)

        assert res.status_code == 200
        assert len(res.json()) >= 2

    async def test_owner_only_sees_own_queries(self, owner_client: AsyncClient, seed_users, test_session_factory):
        await create_query_in_db(test_session_factory, seed_users["owner"].id, question="Owner Q")
        # query from another user
        await create_query_in_db(test_session_factory, seed_users["manager"].id, question="Manager Q")

        res = await owner_client.get(AI_QUERIES_URL)

        assert res.status_code == 200
        user_ids = [q["user_id"] for q in res.json()]
        assert all(uid == seed_users["owner"].id for uid in user_ids)

    async def test_no_queries_returns_empty_list(self, owner_client: AsyncClient, seed_users, test_session_factory):
        res = await owner_client.get(AI_QUERIES_URL)

        assert res.status_code == 200
        assert res.json() == []

    async def test_manager_cannot_list_queries(self, manager_client: AsyncClient, seed_users, test_session_factory):
        res = await manager_client.get(AI_QUERIES_URL)

        assert res.status_code == 403

    async def test_worker_cannot_list_queries(self, worker_client: AsyncClient, seed_users, test_session_factory):
        res = await worker_client.get(AI_QUERIES_URL)

        assert res.status_code == 403

    async def test_unauthenticated_cannot_list_queries(self, unauth_client: AsyncClient):
        res = await unauth_client.get(AI_QUERIES_URL)

        assert res.status_code == 401
