from datetime import date
from unittest.mock import patch

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.cache import delete_cache
from app.models.project import Project, ProjectAssignment
from app.models.report import Report


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
        mock_task.delay.assert_called_once_with(d["project"].id, seed_users["owner"].id)

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
        assert len(res.json()) >= 1
        data = res.json()[0]
        assert data["project_id"] == d["project"].id
        assert "week_start" in data
        assert "week_end" in data
        assert "s3_key" in data
        assert "file_url" in data

    async def test_assigned_manager_can_list_reports(self, manager_client: AsyncClient, seed_users, seed_report_data, test_session_factory):
        d = seed_report_data
        async with test_session_factory() as session:
            async with session.begin():
                session.add(
                    Report(
                        project_id=d["assigned_project"].id,
                        generated_by=seed_users["owner"].id,
                        week_start=date(2026, 2, 1),
                        week_end=date(2026, 2, 7),
                        s3_key=f"reports/report_{d['assigned_project'].id}_2026-02-01.txt",
                    )
                )
        await delete_cache(f"report:list:{d['assigned_project'].id}")
        with patch("app.services.report.generate_presigned_url", return_value="https://fake-s3-url.com/report.pdf"):
            res = await manager_client.get(report_url(d["assigned_project"].id))
        assert res.status_code == 200
        assert len(res.json()) >= 1

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
        dates = [r["week_start"] for r in res.json()]
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
        assert res.json() == []

    async def test_site_worker_cannot_list_reports(self, worker_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await worker_client.get(report_url(d["project"].id))
        assert res.status_code == 403

    async def test_unauthenticated_cannot_list_reports(self, unauth_client: AsyncClient, seed_report_data):
        d = seed_report_data
        res = await unauth_client.get(report_url(d["project"].id))
        assert res.status_code == 401
