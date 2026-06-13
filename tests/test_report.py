from datetime import date
from unittest.mock import patch

from httpx import AsyncClient

from app.models.project import Project, ProjectAssignment
from app.models.report import Report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def report_url(project_id: int) -> str:
    return f"/api/v1/reports/{project_id}"


def generate_url(project_id: int) -> str:
    return f"/api/v1/reports/{project_id}/generate"


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Report Test Project",
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


async def assign_manager(session_factory, project_id: int, user_id: int) -> None:
    async with session_factory() as session:
        session.add(ProjectAssignment(project_id=project_id, user_id=user_id))
        await session.commit()


async def create_report_in_db(session_factory, project_id: int, generated_by: int) -> Report:
    async with session_factory() as session:
        report = Report(
            project_id=project_id,
            generated_by=generated_by,
            week_start=date(2026, 1, 1),
            week_end=date(2026, 1, 7),
            s3_key=f"reports/report_{project_id}_2026-01-01.txt",
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return report


# ---------------------------------------------------------------------------
# POST /reports/{project_id}/generate
# ---------------------------------------------------------------------------


class TestTriggerReport:
    async def test_owner_can_trigger_report(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        with patch("app.routers.report.generate_weekly_report") as mock_task:
            mock_task.delay.return_value = None
            res = await owner_client.post(generate_url(project.id))

        assert res.status_code == 202
        mock_task.delay.assert_called_once_with(project.id, seed_users["owner"].id)

    async def test_assigned_manager_can_trigger_report(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        with patch("app.routers.report.generate_weekly_report") as mock_task:
            mock_task.delay.return_value = None
            res = await manager_client.post(generate_url(project.id))

        assert res.status_code == 202

    async def test_unassigned_manager_cannot_trigger_report(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await manager_client.post(generate_url(project.id))

        assert res.status_code == 403

    async def test_site_worker_cannot_trigger_report(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await worker_client.post(generate_url(project.id))

        assert res.status_code == 403

    async def test_unauthenticated_cannot_trigger_report(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await unauth_client.post(generate_url(project.id))

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# GET /reports/{project_id}
# ---------------------------------------------------------------------------


class TestGetReports:
    async def test_owner_can_list_reports(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await create_report_in_db(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.get(report_url(project.id))

        assert res.status_code == 200
        assert len(res.json()) == 1
        data = res.json()[0]
        assert data["project_id"] == project.id
        assert data["generated_by"] == seed_users["owner"].id
        assert "week_start" in data
        assert "week_end" in data
        assert "s3_key" in data
        assert "file_url" in data

    async def test_assigned_manager_can_list_reports(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        await create_report_in_db(test_session_factory, project.id, seed_users["owner"].id)

        res = await manager_client.get(report_url(project.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_unassigned_manager_cannot_list_reports(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await manager_client.get(report_url(project.id))

        assert res.status_code == 403

    async def test_reports_ordered_newest_first(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        await create_report_in_db(test_session_factory, project.id, seed_users["owner"].id)

        async with test_session_factory() as session:
            session.add(
                Report(
                    project_id=project.id,
                    generated_by=seed_users["owner"].id,
                    week_start=date(2026, 1, 8),
                    week_end=date(2026, 1, 14),
                    s3_key=f"reports/report_{project.id}_2026-01-08.txt",
                )
            )
            await session.commit()

        res = await owner_client.get(report_url(project.id))

        assert res.status_code == 200
        assert len(res.json()) == 2
        dates = [r["week_start"] for r in res.json()]
        assert dates == sorted(dates, reverse=True)

    async def test_no_reports_returns_empty_list(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await owner_client.get(report_url(project.id))

        assert res.status_code == 200
        assert res.json() == []

    async def test_site_worker_cannot_list_reports(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await worker_client.get(report_url(project.id))

        assert res.status_code == 403

    async def test_unauthenticated_cannot_list_reports(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)

        res = await unauth_client.get(report_url(project.id))

        assert res.status_code == 401
