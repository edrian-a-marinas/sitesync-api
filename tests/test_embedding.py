from datetime import date
from unittest.mock import MagicMock, patch

import pytest_asyncio
from sqlalchemy import delete

import app.services.embedding as embedding_module
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project
from app.services.embedding import build_daily_log_chunk_text, generate_embedding


# ---------------------------------------------------------------------------
# Session-scoped seed project (reused across tests, matches test_ai_query.py pattern)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_embedding_project(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="Embedding Test Project",
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


# ---------------------------------------------------------------------------
# _get_model (lazy load + cache) / generate_embedding
# ---------------------------------------------------------------------------
class TestGenerateEmbedding:
    def setup_method(self):
        # Reset the module-level cache before each test so loading behavior is isolated
        embedding_module._model = None

    def teardown_method(self):
        embedding_module._model = None

    def test_loads_model_on_first_call(self):
        mock_model_instance = MagicMock()
        mock_model_instance.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2, 0.3])
        with patch.object(embedding_module, "SentenceTransformer", return_value=mock_model_instance) as mock_st:
            result = generate_embedding("test text")
        mock_st.assert_called_once_with("all-MiniLM-L6-v2")
        assert result == [0.1, 0.2, 0.3]

    def test_reuses_cached_model_on_subsequent_calls(self):
        mock_model_instance = MagicMock()
        mock_model_instance.encode.return_value = MagicMock(tolist=lambda: [0.1])
        with patch.object(embedding_module, "SentenceTransformer", return_value=mock_model_instance) as mock_st:
            generate_embedding("first call")
            generate_embedding("second call")
        mock_st.assert_called_once()  # model only constructed once despite two calls

    def test_encode_called_with_normalize_embeddings(self):
        mock_model_instance = MagicMock()
        mock_model_instance.encode.return_value = MagicMock(tolist=lambda: [0.5])
        with patch.object(embedding_module, "SentenceTransformer", return_value=mock_model_instance):
            generate_embedding("normalize check")
        mock_model_instance.encode.assert_called_once_with("normalize check", normalize_embeddings=True)


# ---------------------------------------------------------------------------
# build_daily_log_chunk_text (RAG source text assembly)
# ---------------------------------------------------------------------------
class TestBuildDailyLogChunkText:
    async def test_raises_when_daily_log_not_found(self, test_session_factory):
        async with test_session_factory() as session:
            try:
                await build_daily_log_chunk_text(session, 999999)
                assert False, "Expected ValueError"
            except ValueError as e:
                assert "999999" in str(e)

    async def test_includes_basic_fields(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 10),
                    weather_condition="Sunny",
                    work_accomplished="Poured foundation slab",
                )
                session.add(log)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "2026-03-10" in text
        assert "Sunny" in text
        assert "Poured foundation slab" in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_missing_weather_shows_not_recorded(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 11),
                    weather_condition=None,
                    work_accomplished="Site cleanup",
                )
                session.add(log)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "Not recorded" in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_includes_notes_when_present(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 12),
                    work_accomplished="Rebar installation",
                    notes="Delayed due to material shortage",
                )
                session.add(log)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "Delayed due to material shortage" in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_omits_notes_section_when_absent(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 13),
                    work_accomplished="Electrical rough-in",
                    notes=None,
                )
                session.add(log)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "Notes:" not in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_includes_materials_when_present(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 14),
                    work_accomplished="Concrete pour",
                )
                session.add(log)
                await session.flush()
                material = Material(
                    daily_log_id=log.id,
                    name="Cement",
                    quantity=40,
                    unit="bags",
                    unit_cost=260.0,
                )
                session.add(material)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "Materials used:" in text
        assert "Cement" in text
        assert "₱260.00" in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(Material).where(Material.daily_log_id == log_id))
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_includes_attendance_summary_when_present(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 15),
                    work_accomplished="Framing",
                )
                session.add(log)
                await session.flush()
                attendance = Attendance(
                    daily_log_id=log.id,
                    worker_id=seed_users["worker"].id,
                    hours_worked=8.0,
                )
                session.add(attendance)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "Attendance: 1 workers, 8.0 total hours" in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(Attendance).where(Attendance.daily_log_id == log_id))
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_includes_incidents_when_present(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 16),
                    work_accomplished="Scaffolding setup",
                )
                session.add(log)
                await session.flush()
                incident = Incident(
                    daily_log_id=log.id,
                    reported_by=seed_users["owner"].id,
                    description="Worker slipped on wet surface",
                    severity="Medium",
                    status="Open",
                )
                session.add(incident)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "Incidents:" in text
        assert "[Medium/Open] Worker slipped on wet surface" in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(Incident).where(Incident.daily_log_id == log_id))
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))

    async def test_omits_sections_when_no_related_records(self, seed_embedding_project, seed_users, test_session_factory):
        project = seed_embedding_project
        async with test_session_factory() as session:
            async with session.begin():
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date(2026, 3, 17),
                    work_accomplished="Minimal day, no activity logged",
                )
                session.add(log)
                await session.flush()
                log_id = log.id
        async with test_session_factory() as session:
            text = await build_daily_log_chunk_text(session, log_id)
        assert "Materials used:" not in text
        assert "Attendance:" not in text
        assert "Incidents:" not in text
        async with test_session_factory() as session:
            async with session.begin():
                await session.execute(delete(DailyLog).where(DailyLog.id == log_id))
