from datetime import date

from httpx import AsyncClient

from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment, WorkerAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def equipment_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/equipment"


def equipment_detail_url(project_id: int, log_id: int, equipment_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/equipment/{equipment_id}"


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Equipment Test Project",
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


async def create_equipment_in_db(session_factory, log_id: int) -> int:
    from app.models.equipment import Equipment

    async with session_factory() as session:
        equipment = Equipment(
            daily_log_id=log_id,
            name="Excavator",
            quantity=1,
            condition="Good",
        )
        session.add(equipment)
        await session.commit()
        await session.refresh(equipment)
        return equipment.id


EQUIPMENT_PAYLOAD = {
    "name": "Excavator",
    "quantity": 1,
    "condition": "Good",
}

EQUIPMENT_UPDATE_PAYLOAD = {
    "quantity": 2,
    "condition": "Needs Repair",
}


# ---------------------------------------------------------------------------
# GET /equipment  (list)
# ---------------------------------------------------------------------------


class TestGetEquipment:
    async def test_owner_can_list_equipment(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await owner_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        res = await owner_client.get(equipment_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["name"] == "Excavator"

    async def test_manager_can_list_equipment(self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        await owner_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        res = await manager_client.get(equipment_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_assigned_worker_can_list_equipment(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await owner_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        res = await worker_client.get(equipment_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_unassigned_worker_gets_empty_list(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await owner_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        res = await worker_client.get(equipment_url(project.id, log.id))

        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.get(equipment_url(project.id, log.id))

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /equipment  (create)
# ---------------------------------------------------------------------------


class TestCreateEquipment:
    async def test_owner_can_create_equipment(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Excavator"
        assert data["daily_log_id"] == log.id
        assert data["condition"] == "Good"

    async def test_assigned_manager_can_create_equipment(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        res = await manager_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        assert res.status_code == 201
        assert res.json()["name"] == "Excavator"

    async def test_unassigned_manager_cannot_create_equipment(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await manager_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        assert res.status_code == 403

    async def test_condition_is_optional(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.post(
            equipment_url(project.id, log.id),
            json={"name": "Crane", "quantity": 1},
        )

        assert res.status_code == 201
        assert res.json()["condition"] is None

    async def test_site_worker_cannot_create_equipment(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await worker_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.post(equipment_url(project.id, log.id), json=EQUIPMENT_PAYLOAD)

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /equipment/{equipment_id}  (update)
# ---------------------------------------------------------------------------


class TestUpdateEquipment:
    async def test_owner_can_update_equipment(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        equipment_id = await create_equipment_in_db(test_session_factory, log.id)

        res = await owner_client.patch(
            equipment_detail_url(project.id, log.id, equipment_id),
            json=EQUIPMENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 200
        data = res.json()
        assert data["quantity"] == 2
        assert data["condition"] == "Needs Repair"

    async def test_assigned_manager_can_update_equipment(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        equipment_id = await create_equipment_in_db(test_session_factory, log.id)

        res = await manager_client.patch(
            equipment_detail_url(project.id, log.id, equipment_id),
            json=EQUIPMENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 200
        assert res.json()["quantity"] == 2

    async def test_unassigned_manager_cannot_update_equipment(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        equipment_id = await create_equipment_in_db(test_session_factory, log.id)

        res = await manager_client.patch(
            equipment_detail_url(project.id, log.id, equipment_id),
            json=EQUIPMENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 403

    async def test_update_nonexistent_equipment_returns_404(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.patch(
            equipment_detail_url(project.id, log.id, 99999),
            json=EQUIPMENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        equipment_id = await create_equipment_in_db(test_session_factory, log.id)

        res = await owner_client.patch(
            equipment_detail_url(project.id, log.id, equipment_id),
            json={"condition": "Broken"},
        )

        assert res.status_code == 200
        data = res.json()
        assert data["condition"] == "Broken"
        assert data["name"] == "Excavator"  # unchanged
        assert data["quantity"] == 1  # unchanged

    async def test_site_worker_cannot_update_equipment(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        equipment_id = await create_equipment_in_db(test_session_factory, log.id)

        res = await worker_client.patch(
            equipment_detail_url(project.id, log.id, equipment_id),
            json=EQUIPMENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.patch(
            equipment_detail_url(project.id, log.id, 1),
            json=EQUIPMENT_UPDATE_PAYLOAD,
        )

        assert res.status_code == 401
