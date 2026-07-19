from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from kombu.exceptions import OperationalError
from langchain_core.documents import Document
from sqlalchemy import delete, select

from app.core.settings import settings
from app.models.ai_query import AIQuery
from app.models.daily_log import DailyLog
from app.models.embedding import AIQueryEmbedding, DailyLogEmbedding
from app.models.project import Project
from app.services.ai_query import (
    AIQueryEmbeddingRetriever,
    DailyLogEmbeddingRetriever,
    _retrieve_project_summary,
    maybe_store_query_embedding,
    retrieve_context,
)


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
    async def test_stale_pending_query_auto_expires(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Stale pending question?",
                    answer=None,
                    status="Pending",
                )
                session.add(query)
                await session.flush()
                query_id = query.id
                old_time = datetime.now(timezone.utc) - timedelta(minutes=settings.PENDING_TIMEOUT_MINUTES + 5)
                query.created_at = old_time
                await session.flush()
        res = await owner_client.get(query_detail_url(query_id))
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "Failed"
        assert data["answer"] == "TIMEOUT"

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
            mock_task.delay.side_effect = OperationalError("broker unreachable")
            res = await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Which project used the most cement?"},
            )
        assert res.status_code == 503

    async def test_celery_worker_down_does_not_create_orphaned_row(self, owner_client: AsyncClient, test_session_factory):
        with patch("app.routers.ai_query.process_ai_query") as mock_task:
            mock_task.delay.side_effect = OperationalError("broker unreachable")
            await owner_client.post(
                AI_QUERY_URL,
                json={"question": "Orphan check question?"},
            )
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.question == "Orphan check question?"))
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


# ---------------------------------------------------------------------------
# DailyLogEmbeddingRetriever (LangChain retriever backed by pgvector cosine similarity)
# ---------------------------------------------------------------------------
class TestDailyLogEmbeddingRetriever:
    async def _seed_embedding(self, test_session_factory, project_id: int, content_text: str, vector: list[float]):
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project_id,
                    submitted_by=1,
                    log_date=date(2026, 3, 1),
                    work_accomplished="Test work for embedding retrieval",
                )
                session.add(log)
                await session.flush()
                embedding = DailyLogEmbedding(
                    daily_log_id=log.id,
                    project_id=project_id,
                    content_text=content_text,
                    embedding=vector,
                )
                session.add(embedding)
                await session.flush()
                log_id = log.id
        return log_id

    async def _cleanup(self, test_session_factory, log_id: int):
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLogEmbedding).where(DailyLogEmbedding.daily_log_id == log_id))
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_returns_matching_documents_scoped_to_project(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_vector = [0.1] * 384
        log_id = await self._seed_embedding(test_session_factory, project.id, "Poured concrete for foundation", fake_vector)
        with patch("app.services.ai_query.generate_embedding", return_value=fake_vector):
            async with test_session_factory() as session:
                retriever = DailyLogEmbeddingRetriever(db=session, project_id=project.id, k=5)
                docs = await retriever.ainvoke("concrete foundation work")
        assert len(docs) >= 1
        assert any("concrete" in d.page_content.lower() for d in docs)
        assert all(d.metadata["project_id"] == project.id for d in docs)
        await self._cleanup(test_session_factory, log_id)

    async def test_respects_k_limit(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_vector = [0.2] * 384
        with patch("app.services.ai_query.generate_embedding", return_value=fake_vector):
            async with test_session_factory() as session:
                retriever = DailyLogEmbeddingRetriever(db=session, project_id=project.id, k=1)
                docs = await retriever.ainvoke("any question")
        assert len(docs) <= 1

    async def test_sync_retrieval_not_implemented(self, seed_ai_query_data, test_session_factory):
        async with test_session_factory() as session:
            retriever = DailyLogEmbeddingRetriever(db=session, project_id=None, k=5)
            with pytest.raises(NotImplementedError):
                retriever._get_relevant_documents("question")


# ---------------------------------------------------------------------------
# _retrieve_project_summary (overview fallback: budget, incidents, hours)
# ---------------------------------------------------------------------------
class TestRetrieveProjectSummary:
    async def test_includes_overview_fields(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        async with test_session_factory() as session:
            context = await _retrieve_project_summary(session, project_id=project.id)
        assert "PROJECT_SUMMARY" in context
        assert project.name in context
        assert "budget_used_percent=" in context
        assert "total_hours_worked=" in context
        assert "total_incidents=" in context
        assert "open_incidents=" in context

    async def test_no_project_id_scopes_to_active_projects(self, seed_ai_query_data, test_session_factory):
        async with test_session_factory() as session:
            context = await _retrieve_project_summary(session, project_id=None)
        assert "PROJECT_SUMMARY" in context

    async def test_nonexistent_project_id_returns_empty_message(self, test_session_factory):
        async with test_session_factory() as session:
            context = await _retrieve_project_summary(session, project_id=999999)
        assert "No project records found" in context


# ---------------------------------------------------------------------------
# retrieve_context (combines semantic matches + project summary for the LLM)
# ---------------------------------------------------------------------------
class TestRetrieveContext:
    async def test_formats_documents_into_semantic_matches_block(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_docs = [
            Document(page_content="Poured concrete for foundation", metadata={"daily_log_id": 1, "project_id": project.id}),
        ]
        with patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=fake_docs)):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "concrete work?", project.id)
        assert "SEMANTIC_MATCHES" in context
        assert "daily_log_id=1" in context
        assert "Poured concrete for foundation" in context

    async def test_always_includes_project_summary_alongside_semantic_matches(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        with patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=[])):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "how is this project?", project.id)
        assert "PROJECT_SUMMARY" in context
        assert project.name in context

    async def test_no_matches_returns_empty_message_but_keeps_summary(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        with patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=[])):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "no match question", project.id)
        assert "No related daily logs found" in context
        assert "PROJECT_SUMMARY" in context

    async def test_retriever_exception_produces_failed_message_but_keeps_summary(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        with patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(side_effect=Exception("db exploded"))):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "any question", project.id)
        assert "SEMANTIC_MATCHES: Retrieval failed." in context
        assert "PROJECT_SUMMARY" in context

    async def test_summary_exception_produces_failed_message_but_keeps_semantic(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_docs = [
            Document(page_content="Poured concrete for foundation", metadata={"daily_log_id": 1, "project_id": project.id}),
        ]
        with (
            patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=fake_docs)),
            patch("app.services.ai_query._retrieve_project_summary", new=AsyncMock(side_effect=Exception("db exploded"))),
        ):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "any question", project.id)
        assert "SEMANTIC_MATCHES" in context
        assert "PROJECT_SUMMARY: Retrieval failed." in context


# ---------------------------------------------------------------------------
# maybe_store_query_embedding (gate: project-specific + non-duplicate only)
# ---------------------------------------------------------------------------
class TestMaybeStoreQueryEmbedding:
    async def _cleanup(self, test_session_factory, query_id: int):
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(AIQueryEmbedding).where(AIQueryEmbedding.ai_query_id == query_id))
                await session.execute(delete(AIQuery).where(AIQuery.id == query_id))

    async def test_skips_when_no_project_id(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    project_id=None,
                    question="Which project used the most cement?",
                    answer="Project A used the most cement.",
                    status="Done",
                )
                session.add(query)
                await session.flush()
                query_id = query.id
                await maybe_store_query_embedding(session, query)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQueryEmbedding).where(AIQueryEmbedding.ai_query_id == query_id))
            assert result.scalar_one_or_none() is None
        await self._cleanup(test_session_factory, query_id)

    async def test_stores_when_project_specific_and_no_duplicate(self, seed_ai_query_data, seed_users, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_vector = [0.3] * 384
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    project_id=project.id,
                    question="What is the budget status?",
                    answer="Budget used is 40%.",
                    status="Done",
                )
                session.add(query)
                await session.flush()
                query_id = query.id
            with patch("app.services.ai_query.generate_embedding", return_value=fake_vector):
                await maybe_store_query_embedding(session, query)
            await session.commit()
        async with test_session_factory() as session:
            result = await session.execute(select(AIQueryEmbedding).where(AIQueryEmbedding.ai_query_id == query_id))
            row = result.scalar_one_or_none()
            assert row is not None
            assert row.project_id == project.id
            assert "What is the budget status?" in row.content_text
            assert "Budget used is 40%." in row.content_text
        await self._cleanup(test_session_factory, query_id)

    async def test_skips_when_near_duplicate_exists(self, seed_ai_query_data, seed_users, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_vector = [0.4] * 384
        async with test_session_factory() as session:
            async with session.begin():
                existing_query = AIQuery(
                    user_id=seed_users["owner"].id,
                    project_id=project.id,
                    question="How much budget is left?",
                    answer="60% remaining.",
                    status="Done",
                )
                session.add(existing_query)
                await session.flush()
                existing_embedding = AIQueryEmbedding(
                    ai_query_id=existing_query.id,
                    project_id=project.id,
                    content_text="Q: How much budget is left?\nA: 60% remaining.",
                    embedding=fake_vector,
                )
                session.add(existing_embedding)
                await session.flush()
                existing_query_id = existing_query.id

                new_query = AIQuery(
                    user_id=seed_users["owner"].id,
                    project_id=project.id,
                    question="What budget remains?",
                    answer="60% remaining.",
                    status="Done",
                )
                session.add(new_query)
                await session.flush()
                new_query_id = new_query.id
            with patch("app.services.ai_query.generate_embedding", return_value=fake_vector):
                await maybe_store_query_embedding(session, new_query)
            await session.commit()
        async with test_session_factory() as session:
            result = await session.execute(select(AIQueryEmbedding).where(AIQueryEmbedding.ai_query_id == new_query_id))
            assert result.scalar_one_or_none() is None
        await self._cleanup(test_session_factory, existing_query_id)
        await self._cleanup(test_session_factory, new_query_id)


# ---------------------------------------------------------------------------
# AIQueryEmbeddingRetriever (past project-specific Q&A via pgvector cosine similarity)
# ---------------------------------------------------------------------------
class TestAIQueryEmbeddingRetriever:
    async def _seed_embedding(self, test_session_factory, seed_users, project_id: int, content_text: str, vector: list[float]):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    project_id=project_id,
                    question="seed question",
                    answer="seed answer",
                    status="Done",
                )
                session.add(query)
                await session.flush()
                embedding = AIQueryEmbedding(
                    ai_query_id=query.id,
                    project_id=project_id,
                    content_text=content_text,
                    embedding=vector,
                )
                session.add(embedding)
                await session.flush()
                query_id = query.id
        return query_id

    async def _cleanup(self, test_session_factory, query_id: int):
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(AIQueryEmbedding).where(AIQueryEmbedding.ai_query_id == query_id))
                await session.execute(delete(AIQuery).where(AIQuery.id == query_id))

    async def test_returns_empty_when_no_project_id(self, test_session_factory):
        async with test_session_factory() as session:
            retriever = AIQueryEmbeddingRetriever(db=session, project_id=None, k=3)
            docs = await retriever.ainvoke("any question")
        assert docs == []

    async def test_returns_matching_documents_scoped_to_project(self, seed_ai_query_data, seed_users, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_vector = [0.5] * 384
        query_id = await self._seed_embedding(test_session_factory, seed_users, project.id, "Q: What is the budget?\nA: 40% used.", fake_vector)
        with patch("app.services.ai_query.generate_embedding", return_value=fake_vector):
            async with test_session_factory() as session:
                retriever = AIQueryEmbeddingRetriever(db=session, project_id=project.id, k=3)
                docs = await retriever.ainvoke("budget question")
        assert len(docs) >= 1
        assert any("budget" in d.page_content.lower() for d in docs)
        assert all(d.metadata["project_id"] == project.id for d in docs)
        await self._cleanup(test_session_factory, query_id)

    async def test_sync_retrieval_not_implemented(self, test_session_factory):
        async with test_session_factory() as session:
            retriever = AIQueryEmbeddingRetriever(db=session, project_id=None, k=3)
            with pytest.raises(NotImplementedError):
                retriever._get_relevant_documents("question")


# ---------------------------------------------------------------------------
# retrieve_context — PAST_ANSWERS section (built on AIQueryEmbeddingRetriever)
# ---------------------------------------------------------------------------
class TestRetrieveContextPastAnswers:
    async def test_includes_past_answers_when_relevant(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        fake_docs = [
            Document(page_content="Q: What is the budget?\nA: 40% used.", metadata={"ai_query_id": 1, "project_id": project.id}),
        ]
        with (
            patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=[])),
            patch.object(AIQueryEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=fake_docs)),
        ):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "budget question", project.id)
        assert "PAST_ANSWERS" in context
        assert "40% used." in context

    async def test_omits_past_answers_section_when_none_found(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        with (
            patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=[])),
            patch.object(AIQueryEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=[])),
        ):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "unrelated question", project.id)
        assert "PAST_ANSWERS" not in context

    async def test_omits_past_answers_when_no_project_id(self, test_session_factory):
        with patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=[])):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "general question", None)
        assert "PAST_ANSWERS" not in context

    async def test_past_answers_retrieval_failure_does_not_break_context(self, seed_ai_query_data, test_session_factory):
        project = seed_ai_query_data["project"]
        with (
            patch.object(DailyLogEmbeddingRetriever, "ainvoke", new=AsyncMock(return_value=[])),
            patch.object(AIQueryEmbeddingRetriever, "ainvoke", new=AsyncMock(side_effect=Exception("db exploded"))),
        ):
            async with test_session_factory() as session:
                context = await retrieve_context(session, "any question", project.id)
        assert "PROJECT_SUMMARY" in context
        assert "PAST_ANSWERS" not in context
