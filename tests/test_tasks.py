from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import groq
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.future import select

from app.models.ai_query import AIQuery
from app.models.daily_log import DailyLog
from app.models.embedding import DailyLogEmbedding
from app.models.project import Project
from app.tasks.ai_query import (
    _cleanup_old_ai_queries,
    _process_ai_query,
    cleanup_old_ai_queries,
    process_ai_query,
)
from app.tasks.embedding import (
    _backfill_embeddings_async,
    _generate_daily_log_embedding,
    backfill_daily_log_embeddings,
    generate_daily_log_embedding,
)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_embedding_task_project(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="Embedding Task Test Project",
                location="Manila",
                total_budget=500_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(project)
            await session.flush()
    yield project
    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Project).where(Project.id == project.id))


from app.tasks.ml import _retrain, retrain_ml_models
from app.tasks.report import (
    _cleanup_old_reports,
    _generate_weekly_report,
    _trigger_all_weekly_reports,
    cleanup_old_reports,
    generate_weekly_report,
    trigger_all_weekly_reports,
)


def make_session_factory_wrapper(test_session_factory):
    def factory():
        @asynccontextmanager
        async def _session():
            async with test_session_factory() as session:
                yield session

        class _Wrapper:
            def __call__(self):
                return _session()

        return _Wrapper()

    return factory


# ---------------------------------------------------------------------------
#  AI_QUERY CELERY TESTS
# ---------------------------------------------------------------------------
class TestProcessAIQueryTask:
    async def test_success_sets_answer_and_done_status(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="How many workers today?",
                    status="Pending",
                )
                session.add(query)
                await session.flush()
                query_id = query.id
        mock_client = AsyncMock(return_value=MagicMock(content="5 workers were present today."))
        with (
            patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ai_query.get_groq_client", return_value=mock_client),
            patch("app.tasks.ai_query.retrieve_context", new=AsyncMock(return_value="ATTENDANCE: 5 workers.")),
        ):
            await _process_ai_query(query_id)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            updated = result.scalar_one()
        assert updated.status == "Done"
        assert updated.answer == "5 workers were present today."

    async def test_query_not_found_returns_early(self, test_session_factory):
        with patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)):
            # Should not raise
            await _process_ai_query(999999)


# ---------------------------------------------------------------------------
# _process_ai_query — error branches (missing key, rate limit, timeout, generic)
# ---------------------------------------------------------------------------
class TestProcessAIQueryTaskErrors:
    async def test_missing_api_key_raises_and_marks_error(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(user_id=seed_users["owner"].id, question="Q?", status="Pending")
                session.add(query)
                await session.flush()
                query_id = query.id
        with (
            patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ai_query.get_groq_client", side_effect=ValueError("GROQ_API_KEY is not set")),
            patch("app.tasks.ai_query.retrieve_context", new=AsyncMock(return_value="context")),
        ):
            await _process_ai_query(query_id)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            updated = result.scalar_one()
        assert updated.status == "Failed"
        assert updated.answer == "ERROR"

    async def test_rate_limit_error_with_retry_after_header(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(user_id=seed_users["owner"].id, question="Q?", status="Pending")
                session.add(query)
                await session.flush()
                query_id = query.id
        mock_request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        mock_response = httpx.Response(429, request=mock_request, headers={"retry-after": "30"})
        rate_limit_error = groq.RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        mock_client = AsyncMock(side_effect=rate_limit_error)
        with (
            patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ai_query.get_groq_client", return_value=mock_client),
            patch("app.tasks.ai_query.retrieve_context", new=AsyncMock(return_value="context")),
        ):
            await _process_ai_query(query_id)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            updated = result.scalar_one()
        assert updated.status == "Failed"
        assert updated.answer == "RATE_LIMIT:30"

    async def test_rate_limit_error_with_unparseable_header_defaults_to_60(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(user_id=seed_users["owner"].id, question="Q?", status="Pending")
                session.add(query)
                await session.flush()
                query_id = query.id
        mock_request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        mock_response = httpx.Response(429, request=mock_request, headers={"retry-after": "not-a-number"})
        rate_limit_error = groq.RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        mock_client = AsyncMock(side_effect=rate_limit_error)
        with (
            patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ai_query.get_groq_client", return_value=mock_client),
            patch("app.tasks.ai_query.retrieve_context", new=AsyncMock(return_value="context")),
        ):
            await _process_ai_query(query_id)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            updated = result.scalar_one()
        assert updated.answer == "RATE_LIMIT:60"

    async def test_api_timeout_error(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(user_id=seed_users["owner"].id, question="Q?", status="Pending")
                session.add(query)
                await session.flush()
                query_id = query.id
        mock_request = httpx.Request("POST", "https://api.groq.com/v1/chat/completions")
        timeout_error = groq.APITimeoutError(request=mock_request)
        mock_client = AsyncMock(side_effect=timeout_error)
        with (
            patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ai_query.get_groq_client", return_value=mock_client),
            patch("app.tasks.ai_query.retrieve_context", new=AsyncMock(return_value="context")),
        ):
            await _process_ai_query(query_id)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            updated = result.scalar_one()
        assert updated.status == "Failed"
        assert updated.answer == "TIMEOUT"

    async def test_generic_exception(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                query = AIQuery(user_id=seed_users["owner"].id, question="Q?", status="Pending")
                session.add(query)
                await session.flush()
                query_id = query.id
        mock_client = AsyncMock(side_effect=Exception("unexpected failure"))
        with (
            patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ai_query.get_groq_client", return_value=mock_client),
            patch("app.tasks.ai_query.retrieve_context", new=AsyncMock(return_value="context")),
        ):
            await _process_ai_query(query_id)
        async with test_session_factory() as session:
            result = await session.execute(select(AIQuery).where(AIQuery.id == query_id))
            updated = result.scalar_one()
        assert updated.status == "Failed"
        assert updated.answer == "ERROR"


# ---------------------------------------------------------------------------
# get_groq_client — direct unit test (missing API key)
# ---------------------------------------------------------------------------
class TestGetGroqClient:
    def test_raises_when_api_key_not_set(self):
        from app.tasks.ai_query import get_groq_client

        with patch("app.tasks.ai_query.settings.GROQ_API_KEY", ""):
            with pytest.raises(ValueError, match="GROQ_API_KEY is not set"):
                get_groq_client()

    def test_returns_client_when_api_key_set(self):
        from app.tasks.ai_query import get_groq_client

        with patch("app.tasks.ai_query.settings.GROQ_API_KEY", "fake-key-123"):
            client = get_groq_client()
        assert client is not None


# ---------------------------------------------------------------------------
# process_ai_query — Celery task wrapper (asyncio.run dispatch)
# ---------------------------------------------------------------------------
class TestProcessAIQueryTaskWrapper:
    def test_wrapper_invokes_asyncio_run(self):
        with patch("app.tasks.ai_query.asyncio.run") as mock_run:
            process_ai_query.run(123)
        mock_run.assert_called_once()
        mock_run.call_args[0][0].close()


# ---------------------------------------------------------------------------
# _cleanup_old_ai_queries — stale-pending expiry + old-record deletion
# ---------------------------------------------------------------------------
class TestCleanupOldAIQueriesTask:
    async def test_expires_stale_pending_and_deletes_old(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                stale_query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Stale pending",
                    status="Pending",
                )
                old_query = AIQuery(
                    user_id=seed_users["owner"].id,
                    question="Very old done query",
                    status="Done",
                    answer="Old answer",
                )
                session.add_all([stale_query, old_query])
                await session.flush()
                stale_query.created_at = datetime.now(timezone.utc) - timedelta(minutes=100)
                old_query.created_at = datetime.now(timezone.utc) - timedelta(days=91)
                await session.flush()
                stale_id = stale_query.id
                old_id = old_query.id
        with patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)):
            await _cleanup_old_ai_queries()
        async with test_session_factory() as session:
            stale_result = await session.execute(select(AIQuery).where(AIQuery.id == stale_id))
            stale_updated = stale_result.scalar_one_or_none()
            old_result = await session.execute(select(AIQuery).where(AIQuery.id == old_id))
            old_deleted = old_result.scalar_one_or_none()
        assert stale_updated.status == "Failed"
        assert stale_updated.answer == "TIMEOUT"
        assert old_deleted is None

    async def test_no_stale_or_old_queries_does_nothing(self, test_session_factory):
        with patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)):
            await _cleanup_old_ai_queries()

    async def test_exception_inside_cleanup_is_caught_and_logged(self, test_session_factory):
        with (
            patch("app.tasks.ai_query.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ai_query.select", side_effect=Exception("query build failed")),
        ):
            # Should not raise — caught internally and logged
            await _cleanup_old_ai_queries()


# ---------------------------------------------------------------------------
# cleanup_old_ai_queries — Celery task wrapper (asyncio.run dispatch)
# ---------------------------------------------------------------------------
class TestCleanupOldAIQueriesTaskWrapper:
    def test_wrapper_invokes_asyncio_run(self):
        with patch("app.tasks.ai_query.asyncio.run") as mock_run:
            cleanup_old_ai_queries.run()
        mock_run.assert_called_once()
        mock_run.call_args[0][0].close()


# ---------------------------------------------------------------------------
# ML CELERY TASKS TESTS
# ---------------------------------------------------------------------------
class TestRetrainMLModelsTask:
    async def test_retrain_success_trains_all_models_and_clears_cache(self, test_session_factory):
        mock_redis_client = MagicMock()
        mock_redis_client.scan_iter.return_value = ["ml:budget:1", "ml:delay:1"]
        with (
            patch("app.tasks.ml.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ml.get_budget_overrun_features", new=AsyncMock(return_value=[{"status": "Active"}])) as mock_budget_feat,
            patch("app.tasks.ml.get_delay_risk_features", new=AsyncMock(return_value=[{"status": "Active"}])) as mock_delay_feat,
            patch("app.tasks.ml.get_material_forecast_features", new=AsyncMock(return_value=[{"status": "Active"}])) as mock_forecast_feat,
            patch("app.tasks.ml.train_budget_overrun") as mock_train_budget,
            patch("app.tasks.ml.train_delay_risk") as mock_train_delay,
            patch("app.tasks.ml.train_material_forecast") as mock_train_forecast,
            patch("app.tasks.ml.redis.from_url", return_value=mock_redis_client),
        ):
            await _retrain()
        mock_budget_feat.assert_called_once()
        mock_delay_feat.assert_called_once()
        mock_forecast_feat.assert_called_once()
        mock_train_budget.assert_called_once()
        mock_train_delay.assert_called_once()
        mock_train_forecast.assert_called_once()
        assert mock_redis_client.delete.call_count == 2

    async def test_retrain_exception_is_caught_and_logged(self, test_session_factory):
        with (
            patch("app.tasks.ml.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.ml.get_budget_overrun_features", new=AsyncMock(side_effect=Exception("db error"))),
        ):
            # Should not raise — caught internally and logged
            await _retrain()


class TestRetrainMLModelsTaskWrapper:
    def test_wrapper_invokes_asyncio_run(self):
        with patch("app.tasks.ml.asyncio.run") as mock_run:
            retrain_ml_models.run()
        mock_run.assert_called_once()
        mock_run.call_args[0][0].close()


# ---------------------------------------------------------------------------
# REPORT CELERY TASKS TESTS
# ---------------------------------------------------------------------------
class TestGenerateWeeklyReportTask:
    def test_success_with_result_invalidates_cache(self):
        mock_db = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        mock_redis_client = MagicMock()
        mock_redis_client.keys.side_effect = [["report:list:1:a"], ["report:exists:1:a"]]
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.report.generate_report_sync", return_value=MagicMock()) as mock_gen,
            patch("app.tasks.report.redis.from_url", return_value=mock_redis_client),
        ):
            _generate_weekly_report(1, 5, source="manual")
        mock_gen.assert_called_once_with(1, 5, mock_db, source="manual")
        mock_redis_client.delete.assert_called_once()

    def test_success_with_no_matching_cache_keys_skips_delete(self):
        mock_db = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        mock_redis_client = MagicMock()
        mock_redis_client.keys.return_value = []
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.report.generate_report_sync", return_value=MagicMock()),
            patch("app.tasks.report.redis.from_url", return_value=mock_redis_client),
        ):
            _generate_weekly_report(1, 5, source="manual")
        mock_redis_client.delete.assert_not_called()

    def test_result_none_skips_cache_invalidation(self):
        mock_db = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.report.generate_report_sync", return_value=None),
            patch("app.tasks.report.redis.from_url") as mock_redis_from_url,
        ):
            _generate_weekly_report(1, None, source="scheduled")
        mock_redis_from_url.assert_not_called()

    def test_exception_is_caught_and_logged(self):
        mock_db = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.report.generate_report_sync", side_effect=Exception("db error")),
        ):
            # Should not raise — caught internally and logged
            _generate_weekly_report(1, 5, source="manual")


class TestGenerateWeeklyReportTaskWrapper:
    def test_wrapper_calls_inner_function(self):
        with patch("app.tasks.report._generate_weekly_report") as mock_inner:
            generate_weekly_report.run(1, 5, "manual")
        mock_inner.assert_called_once_with(1, 5, "manual")


class TestTriggerAllWeeklyReportsTask:
    def test_queues_report_for_each_active_project(self):
        mock_project_1 = MagicMock(id=1)
        mock_project_2 = MagicMock(id=2)
        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_project_1, mock_project_2]
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.generate_weekly_report") as mock_task,
        ):
            _trigger_all_weekly_reports()
        assert mock_task.delay.call_count == 2
        mock_task.delay.assert_any_call(1, None)
        mock_task.delay.assert_any_call(2, None)

    def test_no_active_projects_queues_nothing(self):
        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.generate_weekly_report") as mock_task,
        ):
            _trigger_all_weekly_reports()
        mock_task.delay.assert_not_called()


class TestTriggerAllWeeklyReportsTaskWrapper:
    def test_wrapper_calls_inner_function(self):
        with patch("app.tasks.report._trigger_all_weekly_reports") as mock_inner:
            trigger_all_weekly_reports.run()
        mock_inner.assert_called_once()


class TestCleanupOldReportsTask:
    def test_success_delegates_to_service(self):
        mock_db = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.report.cleanup_old_reports_sync") as mock_cleanup,
        ):
            _cleanup_old_reports()
        mock_cleanup.assert_called_once_with(mock_db)

    def test_exception_is_caught_and_logged(self):
        mock_db = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_db)
        mock_session_factory.__enter__ = MagicMock(return_value=mock_db)
        mock_session_factory.__exit__ = MagicMock(return_value=False)
        mock_make_sync_session = MagicMock(return_value=lambda: mock_session_factory)
        with (
            patch("app.tasks.report.make_celery_sync_session", mock_make_sync_session),
            patch("app.tasks.report.report.cleanup_old_reports_sync", side_effect=Exception("s3 error")),
        ):
            # Should not raise — caught internally and logged
            _cleanup_old_reports()


class TestCleanupOldReportsTaskWrapper:
    def test_wrapper_calls_inner_function(self):
        with patch("app.tasks.report._cleanup_old_reports") as mock_inner:
            cleanup_old_reports.run()
        mock_inner.assert_called_once()


# ---------------------------------------------------------------------------
# EMBEDDING CELERY TASKS TESTS
# ---------------------------------------------------------------------------
class TestGenerateDailyLogEmbeddingTask:
    async def test_success_creates_embedding(self, seed_users, seed_embedding_task_project, test_session_factory):
        project = seed_embedding_task_project
        async with test_session_factory() as session:
            async with session.begin():
                from datetime import date

                from app.models.daily_log import DailyLog

                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 4, 1),
                    work_accomplished="Test embedding generation",
                )
                session.add(log)
                await session.flush()
                log_id = log.id
        with (
            patch("app.tasks.embedding.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.embedding.build_daily_log_chunk_text", new=AsyncMock(return_value="Some content")),
            patch("app.tasks.embedding.generate_embedding", return_value=[0.1] * 384),
        ):
            await _generate_daily_log_embedding(log_id)
        async with test_session_factory() as session:
            result = await session.execute(select(DailyLogEmbedding).where(DailyLogEmbedding.daily_log_id == log_id))
            embedding = result.scalar_one_or_none()
        assert embedding is not None
        assert embedding.content_text == "Some content"
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLogEmbedding).where(DailyLogEmbedding.daily_log_id == log_id))
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_upsert_updates_existing_embedding(self, seed_users, seed_embedding_task_project, test_session_factory):
        project = seed_embedding_task_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 4, 2),
                    work_accomplished="Original work",
                )
                session.add(log)
                await session.flush()
                embedding = DailyLogEmbedding(
                    daily_log_id=log.id,
                    project_id=project.id,
                    content_text="Old content",
                    embedding=[0.0] * 384,
                )
                session.add(embedding)
                await session.flush()
                log_id = log.id
        with (
            patch("app.tasks.embedding.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.embedding.build_daily_log_chunk_text", new=AsyncMock(return_value="Updated content")),
            patch("app.tasks.embedding.generate_embedding", return_value=[0.2] * 384),
        ):
            await _generate_daily_log_embedding(log_id)
        async with test_session_factory() as session:
            result = await session.execute(select(DailyLogEmbedding).where(DailyLogEmbedding.daily_log_id == log_id))
            updated = result.scalar_one()
        assert updated.content_text == "Updated content"
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLogEmbedding).where(DailyLogEmbedding.daily_log_id == log_id))
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_daily_log_not_found_returns_early(self, test_session_factory):
        with patch("app.tasks.embedding.make_celery_session", make_session_factory_wrapper(test_session_factory)):
            # Should not raise
            await _generate_daily_log_embedding(999999)

    async def test_exception_is_caught_rolled_back_and_logged(self, seed_users, seed_embedding_task_project, test_session_factory):
        project = seed_embedding_task_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 4, 3),
                    work_accomplished="Will fail",
                )
                session.add(log)
                await session.flush()
                log_id = log.id
        with (
            patch("app.tasks.embedding.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.embedding.build_daily_log_chunk_text", new=AsyncMock(side_effect=Exception("boom"))),
        ):
            # Should not raise — caught internally and logged
            await _generate_daily_log_embedding(log_id)
        async with test_session_factory() as session:
            result = await session.execute(select(DailyLogEmbedding).where(DailyLogEmbedding.daily_log_id == log_id))
            assert result.scalar_one_or_none() is None
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))


class TestGenerateDailyLogEmbeddingTaskWrapper:
    def test_wrapper_invokes_asyncio_run(self):
        with patch("app.tasks.embedding.asyncio.run") as mock_run:
            generate_daily_log_embedding.run(1)
        mock_run.assert_called_once()
        mock_run.call_args[0][0].close()


class TestBackfillDailyLogEmbeddingsTask:
    async def test_queues_embedding_for_each_daily_log(self, seed_users, seed_embedding_task_project, test_session_factory):
        project = seed_embedding_task_project
        async with test_session_factory() as session:
            async with session.begin():
                log1 = DailyLog(project_id=project.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 4, 4), work_accomplished="A")
                log2 = DailyLog(project_id=project.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 4, 5), work_accomplished="B")
                session.add_all([log1, log2])
                await session.flush()
                log1_id, log2_id = log1.id, log2.id
        with (
            patch("app.tasks.embedding.make_celery_session", make_session_factory_wrapper(test_session_factory)),
            patch("app.tasks.embedding.generate_daily_log_embedding") as mock_task,
        ):
            await _backfill_embeddings_async()
        queued_ids = [c.args[0] for c in mock_task.delay.call_args_list]
        assert log1_id in queued_ids
        assert log2_id in queued_ids
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLog).where(DailyLog.id.in_([log1_id, log2_id])))


class TestBackfillDailyLogEmbeddingsTaskWrapper:
    def test_wrapper_invokes_asyncio_run(self):
        with patch("app.tasks.embedding.asyncio.run") as mock_run:
            backfill_daily_log_embeddings.run()
        mock_run.assert_called_once()
        mock_run.call_args[0][0].close()
