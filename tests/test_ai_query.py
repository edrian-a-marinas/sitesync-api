from datetime import date
from unittest.mock import patch

import pytest_asyncio
from httpx import AsyncClient
from kombu.exceptions import OperationalError
from sqlalchemy import delete, select

from app.models.ai_query import AIQuery
from app.models.project import Project


# ---------------------------------------------------------------------------
# Session-scoped seed
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_ai_query_data(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="AI Query Test Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(project)
            await session.flush()

    yield {"project": project}

    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(AIQuery).where(AIQuery.project_id == project.id))
            await session.execute(delete(Project).where(Project.id == project.id))


AI_QUERY_URL = "/api/v1/ai/query"
AI_QUERIES_URL = "/api/v1/ai/queries"


def query_detail_url(query_id: int) -> str:
    return f"/api/v1/ai/query/{query_id}"


# ---------------------------------------------------------------------------
# POST /ai/query (create)
# ---------------------------------------------------------------------------
class TestCreateAIQuery:
    async def test_owner_can_submit_query(self, owner_client: AsyncClient, seed_users):
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

    async def test_query_with_project_id_scoped(self, owner_client: AsyncClient, seed_ai_query_data):
        d = seed_ai_query_data
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "What is the budget status?", "project_id": d["project"].id},
            )
        assert res.status_code == 201
        assert res.json()["project_id"] == d["project"].id

    async def test_query_without_project_id_is_cross_project(self, owner_client: AsyncClient):
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Which site had the most incidents this quarter?"},
            )
        assert res.status_code == 201
        assert res.json()["project_id"] is None

    async def test_manager_cannot_submit_query(self, manager_client: AsyncClient):
        res = await manager_client.post(
            AI_QUERY_URL,
            json={"question": "Which project used the most cement?"},
        )
        assert res.status_code == 403

    async def test_worker_cannot_submit_query(self, worker_client: AsyncClient):
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
# GET /ai/query/{query_id} (get single)
# ---------------------------------------------------------------------------
class TestGetAIQuery:
    async def test_owner_can_get_own_query(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Which project used the most cement?",
                    answer="Project A used the most cement.",
                    status="Done",
                )
                session.add(query)
                await session.flush()
        res = await owner_client.get(query_detail_url(query.id))
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == query.id
        assert data["status"] == "Done"
        assert data["answer"] == "Project A used the most cement."

    async def test_pending_query_has_null_answer(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Pending question?",
                    answer=None,
                    status="Pending",
                )
                session.add(query)
                await session.flush()
        res = await owner_client.get(query_detail_url(query.id))
        assert res.status_code == 200
        assert res.json()["status"] == "Pending"
        assert res.json()["answer"] is None

    async def test_owner_cannot_get_another_users_query(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["manager"].id,
                    question="Manager question?",
                    answer=None,
                    status="Pending",
                )
                session.add(query)
                await session.flush()
        res = await owner_client.get(query_detail_url(query.id))
        assert res.status_code == 404

    async def test_nonexistent_query_returns_404(self, owner_client: AsyncClient):
        res = await owner_client.get(query_detail_url(99999))
        assert res.status_code == 404

    async def test_manager_cannot_get_query(self, manager_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Owner question?",
                    answer=None,
                    status="Pending",
                )
                session.add(query)
                await session.flush()
        res = await manager_client.get(query_detail_url(query.id))
        assert res.status_code == 403

    async def test_unauthenticated_cannot_get_query(self, unauth_client: AsyncClient):
        res = await unauth_client.get(query_detail_url(1))
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /ai/queries (list all)
# ---------------------------------------------------------------------------
class TestGetAIQueries:
    async def test_owner_can_list_own_queries(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        AIQuery(user_id=seed_users["owner"].id, question="Q1", status="Done", answer="A1"),
                        AIQuery(user_id=seed_users["owner"].id, question="Q2", status="Done", answer="A2"),
                    ]
                )
        res = await owner_client.get(AI_QUERIES_URL)
        assert res.status_code == 200
        assert len(res.json()) >= 2

    async def test_owner_only_sees_own_queries(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        AIQuery(user_id=seed_users["owner"].id, question="Owner Q", status="Done", answer="A"),
                        AIQuery(user_id=seed_users["manager"].id, question="Manager Q", status="Done", answer="A"),
                    ]
                )
        res = await owner_client.get(AI_QUERIES_URL)
        assert res.status_code == 200
        user_ids = [q["user_id"] for q in res.json()]
        assert all(uid == seed_users["owner"].id for uid in user_ids)

    async def test_manager_cannot_list_queries(self, manager_client: AsyncClient):
        res = await manager_client.get(AI_QUERIES_URL)
        assert res.status_code == 403

    async def test_worker_cannot_list_queries(self, worker_client: AsyncClient):
        res = await worker_client.get(AI_QUERIES_URL)
        assert res.status_code == 403

    async def test_unauthenticated_cannot_list_queries(self, unauth_client: AsyncClient):
        res = await unauth_client.get(AI_QUERIES_URL)
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /ai/query (celery unavailable / broker failure — no false success)
# ---------------------------------------------------------------------------
class TestCreateAIQueryServiceUnavailable:
    async def test_celery_worker_down_returns_503(self, owner_client: AsyncClient):
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.app.control.ping.return_value = None
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Which project used the most cement?"},
            )
        assert res.status_code == 503
        mock_task.delay.assert_not_called()

    async def test_celery_worker_down_does_not_create_orphaned_row(self, owner_client: AsyncClient, test_session_factory):
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.app.control.ping.return_value = None
            await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Orphan check question?"},
            )
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.question == "Orphan check question?"))
            assert result.scalar_one_or_none() is None

    async def test_broker_error_on_dispatch_returns_503_and_cleans_up(self, owner_client: AsyncClient, test_session_factory):
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.app.control.ping.return_value = True
            mock_task.delay.side_effect = OperationalError("broker unreachable")
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Broker drop question?"},
            )
        assert res.status_code == 503
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.question == "Broker drop question?"))
            assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# DELETE /ai/query/{query_id} (delete single)
# ---------------------------------------------------------------------------
class TestDeleteAIQuery:
    async def test_owner_can_delete_own_query(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Delete me?",
                    answer="Some answer",
                    status="Done",
                )
                session.add(query)
                await session.flush()
            query_id = query.id
        res = await owner_client.delete(query_detail_url(query_id))
        assert res.status_code == 204
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            assert result.scalar_one_or_none() is None

    async def test_owner_cannot_delete_another_users_query(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["manager"].id,
                    question="Manager's query",
                    answer=None,
                    status="Pending",
                )
                session.add(query)
                await session.flush()
            query_id = query.id
        res = await owner_client.delete(query_detail_url(query_id))
        assert res.status_code == 404
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            assert result.scalar_one_or_none() is not None

    async def test_nonexistent_query_delete_returns_404(self, owner_client: AsyncClient):
        res = await owner_client.delete(query_detail_url(99999))
        assert res.status_code == 404

    async def test_manager_cannot_delete_query(self, manager_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Owner question?",
                    answer=None,
                    status="Pending",
                )
                session.add(query)
                await session.flush()
            query_id = query.id
        res = await manager_client.delete(query_detail_url(query_id))
        assert res.status_code == 403

    async def test_worker_cannot_delete_query(self, worker_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Owner question?",
                    answer=None,
                    status="Pending",
                )
                session.add(query)
                await session.flush()
            query_id = query.id
        res = await worker_client.delete(query_detail_url(query_id))
        assert res.status_code == 403

    async def test_unauthenticated_cannot_delete_query(self, unauth_client: AsyncClient):
        res = await unauth_client.delete(query_detail_url(1))
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /ai/queries (delete all)
# ---------------------------------------------------------------------------
class TestDeleteAllAIQueries:
    async def test_owner_can_delete_all_own_queries(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        AIQuery(user_id=seed_users["owner"].id, question="Q1", status="Done", answer="A1"),
                        AIQuery(user_id=seed_users["owner"].id, question="Q2", status="Done", answer="A2"),
                    ]
                )
        res = await owner_client.delete(AI_QUERIES_URL)
        assert res.status_code == 200
        assert res.json()["deleted"] >= 2
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.user_id == seed_users["owner"].id))
            assert result.scalars().all() == []

    async def test_delete_all_does_not_affect_other_users_queries(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["manager"].id,
                    question="Manager Q",
                    status="Done",
                    answer="A",
                )
                session.add(query)
                await session.flush()
            query_id = query.id
        await owner_client.delete(AI_QUERIES_URL)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            assert result.scalar_one_or_none() is not None

    async def test_manager_cannot_delete_all_queries(self, manager_client: AsyncClient):
        res = await manager_client.delete(AI_QUERIES_URL)
        assert res.status_code == 403

    async def test_worker_cannot_delete_all_queries(self, worker_client: AsyncClient):
        res = await worker_client.delete(AI_QUERIES_URL)
        assert res.status_code == 403

    async def test_unauthenticated_cannot_delete_all_queries(self, unauth_client: AsyncClient):
        res = await unauth_client.delete(AI_QUERIES_URL)
        assert res.status_code == 401
