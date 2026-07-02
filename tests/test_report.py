from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.cache import delete_cache
from app.models.attendance import Attendance
from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.material import Material
from app.models.project import Project, ProjectAssignment
from app.models.report import Report
from app.services.report import (
    cleanup_old_reports_sync,
    generate_report,
    generate_report_sync,
    get_report_for_download,
    get_reports,
    report_exists_today,
)


# ---------------------------------------------------------------------------
# Session-scoped seed
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_report_data(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="Report Test Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            assigned_project = Project(
                owner_id=seed_users["owner"].id,
                name="Report Assigned Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([project, assigned_project])
            await session.flush()
            session.add(
                ProjectAssignment(
                    project_id=assigned_project.id,
                    user_id=seed_users["manager"].id,
                )
            )

    yield {"project": project, "assigned_project": assigned_project}

    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Report).where(Report.project_id.in_([project.id, assigned_project.id])))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id.in_([project.id, assigned_project.id])))
            await session.execute(delete(Project).where(Project.id.in_([project.id, assigned_project.id])))


def report_url(project_id: int) -> str:
    return f"/api/v1/reports/{project_id}"


def generate_url(project_id: int) -> str:
    return f"/api/v1/reports/{project_id}/generate"


# ---------------------------------------------------------------------------
# POST /reports/{project_id}/generate
# ---------------------------------------------------------------------------
class TestTriggerReport:
    async def test_owner_can_trigger_report(self, owner_client: AsyncClient, seed_users, seed_report_data):
        d = seed_report_data
        with patch("app.routers.report.generate_weekly_report") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(generate_url(d["project"].id))
        assert res.status_code == 202
        mock_task.delay.assert_called_once_with(d["project"].id, seed_users["owner"].id, "manual")

    async def test_assigned_manager_can_trigger_report(self, manager_client: AsyncClient, seed_report_data):
        d = seed_report_data
        with patch("app.routers.report.generate_weekly_report") as mock_task:
            mock_task.delay.return_value = None
            res = await manager_client.post(generate_url(d["assigned_project"].id))
        assert res.status_code == 202

    async def test_unassigned_manager_cannot_trigger_report(self, manager_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await manager_client.post(generate_url(d["project"].id))
        assert res.status_code == 403

    async def test_site_worker_cannot_trigger_report(self, worker_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await worker_client.post(generate_url(d["project"].id))
        assert res.status_code == 403

    async def test_unauthenticated_cannot_trigger_report(self, unauth_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await unauth_client.post(generate_url(d["project"].id))
        assert res.status_code == 401

    async def test_trigger_report_already_exists_returns_200(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Existing Report Project",
                    location="Manila",
                    total_budget=500_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(project)
                await session.flush()
                week_start = date.today() - timedelta(days=7)

                session.add(
                    Report(
                        project_id=project.id,
                        generated_by=seed_users["owner"].id,
                        week_start=week_start,
                        week_end=date.today(),
                        s3_key=f"reports/report_{project.id}_{week_start}.txt",
                        created_at=datetime.now(timezone.utc),
                    )
                )
        res = await owner_client.post(generate_url(project.id))
        assert res.status_code == 200
        assert res.json()["status"] == "exists"


# ---------------------------------------------------------------------------
# GET /reports/{project_id}
# ---------------------------------------------------------------------------
class TestGetReports:
    async def test_owner_can_list_reports(self, owner_client: AsyncClient, seed_users, seed_report_data, test_session_factory):
        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                session.add(
                    Report(
                        project_id=d["project"].id,
                        generated_by=seed_users["owner"].id,
                        week_start=date(2026, 2, 1),
                        week_end=date(2026, 2, 7),
                        s3_key=f"reports/report_{d['project'].id}_2026-02-01.txt",
                    )
                )
        await delete_cache(f"report:list:{d['project'].id}")
        with patch("app.services.report.generate_presigned_url", return_value="https://fake-s3-url.com/report.pdf"):
            res = await owner_client.get(report_url(d["project"].id))
        assert res.status_code == 200
        assert len(res.json()["items"]) >= 1
        data = res.json()["items"][0]
        assert data["project_id"] == d["project"].id
        assert "week_start" in data
        assert "week_end" in data
        assert "s3_key" in data
        assert "file_url" in data
        assert data["source"] == "manual"

    async def test_assigned_manager_can_list_reports(self, manager_client: AsyncClient, seed_users, seed_report_data, test_session_factory):
        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                # PM can only see own reports + scheduled
                session.add(
                    Report(
                        project_id=d["assigned_project"].id,
                        generated_by=seed_users["manager"].id,
                        week_start=date(2026, 2, 1),
                        week_end=date(2026, 2, 7),
                        s3_key=f"reports/report_{d['assigned_project'].id}_2026-02-01.txt",
                    )
                )
        await delete_cache(f"report:list:{d['assigned_project'].id}:{seed_users['manager'].id}:1:20")
        with patch("app.services.report.generate_presigned_url", return_value="https://fake-s3-url.com/report.pdf"):
            res = await manager_client.get(report_url(d["assigned_project"].id))
        assert res.status_code == 200
        assert len(res.json()["items"]) >= 1

    async def test_unassigned_manager_cannot_list_reports(self, manager_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await manager_client.get(report_url(d["project"].id))
        assert res.status_code == 403

    async def test_reports_ordered_newest_first(self, owner_client: AsyncClient, seed_users, seed_report_data, test_session_factory):
        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                session.add_all(
                    [
                        Report(
                            project_id=d["project"].id,
                            generated_by=seed_users["owner"].id,
                            week_start=date(2026, 3, 1),
                            week_end=date(2026, 3, 7),
                            s3_key=f"reports/report_{d['project'].id}_2026-03-01.txt",
                        ),
                        Report(
                            project_id=d["project"].id,
                            generated_by=seed_users["owner"].id,
                            week_start=date(2026, 3, 8),
                            week_end=date(2026, 3, 14),
                            s3_key=f"reports/report_{d['project'].id}_2026-03-08.txt",
                        ),
                    ]
                )
        res = await owner_client.get(report_url(d["project"].id))
        assert res.status_code == 200
        dates = [r["week_start"] for r in res.json()["items"]]
        assert dates == sorted(dates, reverse=True)

    async def test_no_reports_returns_empty_list(self, owner_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Empty Report Project",
                    location="Manila",
                    total_budget=500_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(project)
                await session.flush()
        res = await owner_client.get(report_url(project.id))
        assert res.status_code == 200
        assert res.json()["items"] == []
        assert res.json()["total"] == 0

    async def test_site_worker_cannot_list_reports(self, worker_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await worker_client.get(report_url(d["project"].id))
        assert res.status_code == 403

    async def test_unauthenticated_cannot_list_reports(self, unauth_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await unauth_client.get(report_url(d["project"].id))
        assert res.status_code == 401


class TestReportExistsToday:
    async def test_cache_hit_returns_true_without_db_query(self, seed_users, test_session_factory):
        from app.core.cache import set_cache

        today = date.today()
        cache_key = f"report:exists:1:{seed_users['owner'].id}:{today}"
        await set_cache(cache_key, True, ttl=86400)
        async with test_session_factory() as session:
            result = await report_exists_today(1, seed_users["owner"].id, session)
        assert result is True

    async def test_db_hit_sets_cache_and_returns_true(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Exists Today Isolated Project",
                    location="Manila",
                    total_budget=500_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(project)
                await session.flush()
                session.add(
                    Report(
                        project_id=project.id,
                        generated_by=seed_users["owner"].id,
                        week_start=date.today() - timedelta(days=7),
                        week_end=date.today(),
                        s3_key="reports/exists_today_test.pdf",
                        created_at=datetime.now(timezone.utc),
                    )
                )
                await session.flush()
                project_id = project.id
        async with test_session_factory() as session:
            result = await report_exists_today(project_id, seed_users["owner"].id, session)
        assert result is True


# ---------------------------------------------------------------------------
# generate_report (async — core report generation logic)
# ---------------------------------------------------------------------------
class TestGenerateReportAsync:
    async def test_generates_report_with_aggregated_data(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Generate Report Project",
                    location="Manila",
                    total_budget=500_000,
                    start_date=date(2026, 1, 1),
                    target_end_date=date(2026, 12, 31),
                    status="Active",
                )
                session.add(project)
                await session.flush()
                log = DailyLog(
                    project_id=project.id,
                    submitted_by=seed_users["owner"].id,
                    log_date=date.today() - timedelta(days=1),
                    work_accomplished="Poured foundation",
                )
                session.add(log)
                await session.flush()
                session.add(Attendance(daily_log_id=log.id, worker_id=seed_users["worker"].id, hours_worked=8.0))
                session.add(Material(daily_log_id=log.id, name="Cement", quantity=10, unit="bags", unit_cost=250.0))
                session.add(
                    Incident(daily_log_id=log.id, reported_by=seed_users["owner"].id, description="Minor issue", severity="Low", status="Open")
                )
                await session.flush()
                project_id = project.id
        with (
            patch("app.services.report.upload_file", return_value="reports/fake.pdf") as mock_upload,
            patch("app.services.report.build_report_pdf", return_value=b"%PDF-fake"),
        ):
            async with test_session_factory() as session:
                report = await generate_report(project_id, seed_users["owner"].id, session, source="manual")
        assert report is not None
        assert report.project_id == project_id
        assert report.log_count == 1
        assert report.incident_count == 1
        assert report.open_incident_count == 1
        assert float(report.total_hours) == 8.0
        assert float(report.total_material_cost) == 2500.0
        mock_upload.assert_called_once()

    async def test_project_not_found_returns_none(self, seed_users, test_session_factory):

        async with test_session_factory() as session:
            result = await generate_report(999999, seed_users["owner"].id, session, source="manual")
        assert result is None

    async def test_exception_during_generation_returns_none(self, seed_users, test_session_factory, seed_report_data):

        d = seed_report_data
        with patch("app.services.report.upload_file", side_effect=Exception("s3 upload failed")):
            async with test_session_factory() as session:
                result = await generate_report(d["project"].id, seed_users["owner"].id, session, source="manual")
        assert result is None


# ---------------------------------------------------------------------------
# generate_report_sync (Celery task version — sync db session)
# ---------------------------------------------------------------------------
class TestGenerateReportSync:
    def test_generates_report_success(self):
        mock_project = MagicMock()
        mock_project.name = "Sync Test Project"
        mock_project.id = 1
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = mock_project
        db.execute.return_value.scalar.return_value = 10.0
        db.execute.return_value.scalars.return_value.all.return_value = []
        with (
            patch("app.services.report.upload_file", return_value="reports/fake.pdf"),
            patch("app.services.report.build_report_pdf", return_value=b"%PDF-fake"),
        ):
            report = generate_report_sync(1, None, db, source="scheduled")
        assert report is not None
        db.commit.assert_called_once()

    def test_project_not_found_returns_none(self):

        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        result = generate_report_sync(999999, None, db, source="scheduled")
        assert result is None

    def test_unique_constraint_violation_returns_none_silently(self):
        mock_project = MagicMock()
        mock_project.name = "Sync Test Project"
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = mock_project
        db.execute.return_value.scalar.return_value = 0.0
        db.execute.return_value.scalars.return_value.all.return_value = []
        db.commit.side_effect = Exception("duplicate key value violates unique constraint uq_report_project_week")
        with (
            patch("app.services.report.upload_file", return_value="reports/fake.pdf"),
            patch("app.services.report.build_report_pdf", return_value=b"%PDF-fake"),
        ):
            result = generate_report_sync(1, None, db, source="scheduled")
        assert result is None

    def test_generic_exception_returns_none(self):
        mock_project = MagicMock()
        mock_project.name = "Sync Test Project"
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = mock_project
        db.execute.return_value.scalar.return_value = 0.0
        db.execute.return_value.scalars.return_value.all.return_value = []
        db.commit.side_effect = Exception("connection lost")
        with (
            patch("app.services.report.upload_file", return_value="reports/fake.pdf"),
            patch("app.services.report.build_report_pdf", return_value=b"%PDF-fake"),
        ):
            result = generate_report_sync(1, None, db, source="scheduled")
        assert result is None


# ---------------------------------------------------------------------------
# get_report_for_download (role-scoped download access)
# ---------------------------------------------------------------------------
class TestGetReportForDownload:
    async def test_owner_can_get_any_report(self, seed_users, seed_report_data, test_session_factory):

        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                report = Report(
                    project_id=d["project"].id,
                    generated_by=seed_users["manager"].id,
                    week_start=date(2026, 4, 1),
                    week_end=date(2026, 4, 7),
                    s3_key="reports/dl_test.pdf",
                )
                session.add(report)
                await session.flush()
                report_id = report.id
        async with test_session_factory() as session:
            result = await get_report_for_download(d["project"].id, report_id, seed_users["owner"], session)
        assert result is not None
        assert result.id == report_id

    async def test_pm_can_get_own_report(self, seed_users, seed_report_data, test_session_factory):
        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                report = Report(
                    project_id=d["assigned_project"].id,
                    generated_by=seed_users["manager"].id,
                    week_start=date(2026, 4, 8),
                    week_end=date(2026, 4, 14),
                    s3_key="reports/dl_test2.pdf",
                )
                session.add(report)
                await session.flush()
                report_id = report.id
        async with test_session_factory() as session:
            result = await get_report_for_download(d["assigned_project"].id, report_id, seed_users["manager"], session)
        assert result is not None

    async def test_pm_cannot_get_other_users_report(self, seed_users, seed_report_data, test_session_factory):
        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                report = Report(
                    project_id=d["assigned_project"].id,
                    generated_by=seed_users["owner"].id,
                    week_start=date(2026, 4, 15),
                    week_end=date(2026, 4, 21),
                    s3_key="reports/dl_test3.pdf",
                )
                session.add(report)
                await session.flush()
                report_id = report.id
        async with test_session_factory() as session:
            result = await get_report_for_download(d["assigned_project"].id, report_id, seed_users["manager"], session)
        assert result is None

    async def test_pm_can_get_scheduled_report(self, seed_users, seed_report_data, test_session_factory):

        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                report = Report(
                    project_id=d["assigned_project"].id,
                    generated_by=None,
                    week_start=date(2026, 4, 22),
                    week_end=date(2026, 4, 28),
                    s3_key="reports/dl_test4.pdf",
                )
                session.add(report)
                await session.flush()
                report_id = report.id
        async with test_session_factory() as session:
            result = await get_report_for_download(d["assigned_project"].id, report_id, seed_users["manager"], session)
        assert result is not None


# ---------------------------------------------------------------------------
# cleanup_old_reports_sync (deletes reports older than 14 days)
# ---------------------------------------------------------------------------
class TestCleanupOldReportsSync:
    def test_deletes_old_reports(self):
        old_report = MagicMock()
        old_report.id = 1
        old_report.project_id = 1
        old_report.s3_key = "reports/old.pdf"
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [old_report]
        with patch("app.services.report.delete_file") as mock_delete:
            count = cleanup_old_reports_sync(db)
        assert count == 1
        mock_delete.assert_called_once_with("reports/old.pdf")
        db.delete.assert_called_once_with(old_report)

    def test_delete_failure_rolls_back_and_continues(self):
        old_report = MagicMock()
        old_report.id = 1
        old_report.project_id = 1
        old_report.s3_key = "reports/old.pdf"
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = [old_report]
        with patch("app.services.report.delete_file", side_effect=Exception("s3 error")):
            count = cleanup_old_reports_sync(db)
        assert count == 0
        db.rollback.assert_called_once()

    def test_no_old_reports_returns_zero(self):
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.return_value = []
        count = cleanup_old_reports_sync(db)
        assert count == 0


# ---------------------------------------------------------------------------
# get_reports (exception branch)
# ---------------------------------------------------------------------------
class TestGetReportsException:
    async def test_db_error_returns_empty_result(self, seed_users, test_session_factory):
        async with test_session_factory() as session:
            original_execute = session.execute
            call_count = {"n": 0}

            async def flaky_execute(*args, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return await original_execute(*args, **kwargs)
                raise Exception("db connection lost")

            with patch.object(session, "execute", AsyncMock(side_effect=flaky_execute)):
                result = await get_reports(1, session, page=1, page_size=20, current_user=seed_users["owner"])
        assert result == {"items": [], "total": 0, "page": 1, "page_size": 20}
