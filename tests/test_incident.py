from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.models.daily_log import DailyLog
from app.models.incident import Incident
from app.models.project import Project, ProjectAssignment, WorkerAssignment


# ---------------------------------------------------------------------------
# Session-scoped seed
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_incident_data(test_session_factory, seed_users):
    async with test_session_factory() as session:
        async with session.begin():
            project = Project(
                owner_id=seed_users["owner"].id,
                name="Incident Test Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add(project)
            await session.flush()
            log = DailyLog(
                project_id=project.id,
                submitted_by=seed_users["owner"].id,
                log_date=date(2026, 1, 1),
                work_accomplished="Test work",
            )
            session.add(log)
            await session.flush()
            session.add_all(
                [
                    ProjectAssignment(project_id=project.id, user_id=seed_users["manager"].id),
                    WorkerAssignment(project_id=project.id, user_id=seed_users["worker"].id),
                ]
            )

    yield {"project": project, "log": log}

    async with test_session_factory() as session:
        async with session.begin():
            await session.execute(delete(Incident).where(Incident.daily_log_id.in_(select(DailyLog.id).where(DailyLog.project_id == project.id))))
            await session.execute(delete(DailyLog).where(DailyLog.project_id == project.id))
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id == project.id))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id == project.id))
            await session.execute(delete(Project).where(Project.id == project.id))


def incident_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/incidents"


def incident_detail_url(project_id: int, log_id: int, incident_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/incidents/{incident_id}"


INCIDENT_PAYLOAD = {
    "description": "A wall collapsed.",
    "severity": "High",
    "status": "Open",
}

INCIDENT_UPDATE_PAYLOAD = {
    "severity": "Low",
    "status": "Resolved",
}


# ---------------------------------------------------------------------------
# GET /incidents (list)
# ---------------------------------------------------------------------------
class TestGetIncidents:
    async def test_owner_can_list_incidents(self, owner_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        await owner_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        res = await owner_client.get(incident_url(d["project"].id, d["log"].id))
        assert res.status_code == 200
        assert len(res.json()) >= 1
        assert res.json()[0]["severity"] == "High"

    async def test_manager_can_list_incidents(self, manager_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await manager_client.get(incident_url(d["project"].id, d["log"].id))
        assert res.status_code == 200

    async def test_assigned_worker_can_list_incidents(self, worker_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await worker_client.get(incident_url(d["project"].id, d["log"].id))
        assert res.status_code == 200

    async def test_unassigned_worker_gets_empty_list(self, worker_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Unassigned Incident Project",
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
                    log_date=date(2026, 1, 1),
                    work_accomplished="Test",
                )
                session.add(log)
                await session.flush()
        res = await worker_client.get(incident_url(project.id, log.id))
        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await unauth_client.get(incident_url(d["project"].id, d["log"].id))
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /incidents (create)
# ---------------------------------------------------------------------------
class TestCreateIncident:
    async def test_owner_can_create_incident(self, owner_client: AsyncClient, seed_users, seed_incident_data):
        d = seed_incident_data
        res = await owner_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        assert res.status_code == 201
        data = res.json()
        assert data["description"] == "A wall collapsed."
        assert data["severity"] == "High"
        assert data["status"] == "Open"
        assert data["daily_log_id"] == d["log"].id
        assert data["reported_by"] == seed_users["owner"].id

    async def test_assigned_manager_can_create_incident(self, manager_client: AsyncClient, seed_users, seed_incident_data):
        d = seed_incident_data
        res = await manager_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        assert res.status_code == 201
        assert res.json()["reported_by"] == seed_users["manager"].id

    async def test_unassigned_manager_cannot_create_incident(self, manager_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Unassigned Mgr Project",
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
                    log_date=date(2026, 1, 1),
                    work_accomplished="Test",
                )
                session.add(log)
                await session.flush()
        res = await manager_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)
        assert res.status_code == 403

    async def test_default_status_is_open(self, owner_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await owner_client.post(
            incident_url(d["project"].id, d["log"].id),
            json={"description": "Minor crack.", "severity": "Low"},
        )
        assert res.status_code == 201
        assert res.json()["status"] == "Open"

    async def test_site_worker_cannot_create_incident(self, worker_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await worker_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await unauth_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /incidents/{incident_id} (update)
# ---------------------------------------------------------------------------
class TestUpdateIncident:
    async def test_owner_can_update_incident(self, owner_client: AsyncClient, seed_users, seed_incident_data):
        d = seed_incident_data
        create_res = await owner_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        incident_id = create_res.json()["id"]
        res = await owner_client.patch(
            incident_detail_url(d["project"].id, d["log"].id, incident_id),
            json=INCIDENT_UPDATE_PAYLOAD,
        )
        assert res.status_code == 200
        assert res.json()["severity"] == "Low"
        assert res.json()["status"] == "Resolved"

    async def test_assigned_manager_can_update_incident(self, manager_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        create_res = await manager_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        incident_id = create_res.json()["id"]
        res = await manager_client.patch(
            incident_detail_url(d["project"].id, d["log"].id, incident_id),
            json=INCIDENT_UPDATE_PAYLOAD,
        )
        assert res.status_code == 200
        assert res.json()["status"] == "Resolved"

    async def test_unassigned_manager_cannot_update_incident(self, manager_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            async with session.begin():
                project = Project(
                    owner_id=seed_users["owner"].id,
                    name="Unassigned Update Project",
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
                    log_date=date(2026, 1, 1),
                    work_accomplished="Test",
                )
                session.add(log)
                await session.flush()
                incident = Incident(
                    daily_log_id=log.id,
                    reported_by=seed_users["owner"].id,
                    description="A wall collapsed.",
                    severity="High",
                    status="Open",
                )
                session.add(incident)
                await session.flush()
        res = await manager_client.patch(
            incident_detail_url(project.id, log.id, incident.id),
            json=INCIDENT_UPDATE_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_update_nonexistent_incident_returns_404(self, owner_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await owner_client.patch(
            incident_detail_url(d["project"].id, d["log"].id, 99999),
            json=INCIDENT_UPDATE_PAYLOAD,
        )
        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, owner_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        create_res = await owner_client.post(incident_url(d["project"].id, d["log"].id), json=INCIDENT_PAYLOAD)
        incident_id = create_res.json()["id"]
        res = await owner_client.patch(
            incident_detail_url(d["project"].id, d["log"].id, incident_id),
            json={"status": "Resolved"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "Resolved"
        assert data["severity"] == "High"
        assert data["description"] == "A wall collapsed."

    async def test_site_worker_cannot_update_incident(self, worker_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await worker_client.patch(
            incident_detail_url(d["project"].id, d["log"].id, 1),
            json=INCIDENT_UPDATE_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, unauth_client: AsyncClient, seed_incident_data):
        d = seed_incident_data
        res = await unauth_client.patch(
            incident_detail_url(d["project"].id, d["log"].id, 1),
            json=INCIDENT_UPDATE_PAYLOAD,
        )
        assert res.status_code == 401
