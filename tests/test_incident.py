from datetime import date

from httpx import AsyncClient

from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment, WorkerAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def incident_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/incidents"


def incident_detail_url(project_id: int, log_id: int, incident_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/incidents/{incident_id}"


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Incident Test Project",
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


async def create_daily_log(session_factory, project_id: int, submitted_by: int) -> DailyLog:
    async with session_factory() as session:
        log = DailyLog(
            project_id=project_id,
            submitted_by=submitted_by,
            log_date=date(2026, 1, 1),
            work_accomplished="Test work",
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        return log


async def assign_manager(session_factory, project_id: int, user_id: int) -> None:
    async with session_factory() as session:
        session.add(ProjectAssignment(project_id=project_id, user_id=user_id))
        await session.commit()


async def assign_worker(session_factory, project_id: int, user_id: int) -> None:
    async with session_factory() as session:
        session.add(WorkerAssignment(project_id=project_id, user_id=user_id))
        await session.commit()


async def create_incident_in_db(session_factory, log_id: int, reported_by: int) -> int:
    from app.models.incident import Incident

    async with session_factory() as session:
        incident = Incident(
            daily_log_id=log_id,
            reported_by=reported_by,
            description="A wall collapsed.",
            severity="High",
            status="Open",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)
        return incident.id


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
# GET /incidents  (list)
# ---------------------------------------------------------------------------


class TestGetIncidents:
    async def test_owner_can_list_incidents(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await owner_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        res = await owner_client.get(incident_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["severity"] == "High"

    async def test_manager_can_list_incidents(self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        await owner_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        res = await manager_client.get(incident_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_assigned_worker_can_list_incidents(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await owner_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        res = await worker_client.get(incident_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_unassigned_worker_gets_empty_list(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await owner_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        res = await worker_client.get(incident_url(project.id, log.id))

        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.get(incident_url(project.id, log.id))

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /incidents  (create)
# ---------------------------------------------------------------------------


class TestCreateIncident:
    async def test_owner_can_create_incident(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        assert res.status_code == 201
        data = res.json()
        assert data["description"] == "A wall collapsed."
        assert data["severity"] == "High"
        assert data["status"] == "Open"
        assert data["daily_log_id"] == log.id
        assert data["reported_by"] == seed_users["owner"].id

    async def test_assigned_manager_can_create_incident(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        res = await manager_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        assert res.status_code == 201
        assert res.json()["reported_by"] == seed_users["manager"].id

    async def test_unassigned_manager_cannot_create_incident(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await manager_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        assert res.status_code == 403

    async def test_default_status_is_open(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.post(
            incident_url(project.id, log.id),
            json={"description": "Minor crack.", "severity": "Low"},
        )

        assert res.status_code == 201
        assert res.json()["status"] == "Open"

    async def test_site_worker_cannot_create_incident(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await worker_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.post(incident_url(project.id, log.id), json=INCIDENT_PAYLOAD)

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /incidents/{incident_id}  (update)
# ---------------------------------------------------------------------------


class TestUpdateIncident:
    async def test_owner_can_update_incident(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        incident_id = await create_incident_in_db(test_session_factory, log.id, seed_users["owner"].id)

        res = await owner_client.patch(
            incident_detail_url(project.id, log.id, incident_id),
            json=INCIDENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 200
        data = res.json()
        assert data["severity"] == "Low"
        assert data["status"] == "Resolved"

    async def test_assigned_manager_can_update_incident(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        incident_id = await create_incident_in_db(test_session_factory, log.id, seed_users["manager"].id)

        res = await manager_client.patch(
            incident_detail_url(project.id, log.id, incident_id),
            json=INCIDENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 200
        assert res.json()["status"] == "Resolved"

    async def test_unassigned_manager_cannot_update_incident(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        incident_id = await create_incident_in_db(test_session_factory, log.id, seed_users["owner"].id)

        res = await manager_client.patch(
            incident_detail_url(project.id, log.id, incident_id),
            json=INCIDENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 403

    async def test_update_nonexistent_incident_returns_404(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.patch(
            incident_detail_url(project.id, log.id, 99999),
            json=INCIDENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        incident_id = await create_incident_in_db(test_session_factory, log.id, seed_users["owner"].id)

        res = await owner_client.patch(
            incident_detail_url(project.id, log.id, incident_id),
            json={"status": "Resolved"},
        )

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "Resolved"
        assert data["severity"] == "High"  # unchanged
        assert data["description"] == "A wall collapsed."  # unchanged

    async def test_site_worker_cannot_update_incident(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        incident_id = await create_incident_in_db(test_session_factory, log.id, seed_users["owner"].id)

        res = await worker_client.patch(
            incident_detail_url(project.id, log.id, incident_id),
            json=INCIDENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.patch(
            incident_detail_url(project.id, log.id, 1),
            json=INCIDENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 401
