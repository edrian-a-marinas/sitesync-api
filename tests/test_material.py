from datetime import date

from httpx import AsyncClient

from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment, WorkerAssignment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def material_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/materials"


def material_detail_url(project_id: int, log_id: int, material_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/materials/{material_id}"


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Material Test Project",
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


async def create_material_in_db(session_factory, log_id: int) -> int:
    from app.models.material import Material

    async with session_factory() as session:
        material = Material(
            daily_log_id=log_id,
            name="Cement",
            quantity=10.0,
            unit="bags",
            unit_cost=250.0,
        )
        session.add(material)
        await session.commit()
        await session.refresh(material)
        return material.id


MATERIAL_PAYLOAD = {
    "name": "Cement",
    "quantity": 10.0,
    "unit": "bags",
    "unit_cost": 250.0,
}

MATERIAL_UPDATE_PAYLOAD = {
    "quantity": 20.0,
    "unit_cost": 300.0,
}


# ---------------------------------------------------------------------------
# GET /materials  (list)
# ---------------------------------------------------------------------------


class TestGetMaterials:
    async def test_owner_can_list_materials(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        res = await owner_client.get(material_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["name"] == "Cement"

    async def test_manager_can_list_materials(self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        res = await manager_client.get(material_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_assigned_worker_can_list_materials(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        res = await worker_client.get(material_url(project.id, log.id))

        assert res.status_code == 200
        assert len(res.json()) == 1

    async def test_unassigned_worker_gets_empty_list(self, owner_client: AsyncClient, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        # worker NOT assigned via WorkerAssignment
        await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        res = await worker_client.get(material_url(project.id, log.id))

        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.get(material_url(project.id, log.id))

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /materials  (create)
# ---------------------------------------------------------------------------


class TestCreateMaterial:
    async def test_owner_can_create_material(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Cement"
        assert data["daily_log_id"] == log.id
        assert data["total_cost"] == 2500.0  # 10 * 250

    async def test_assigned_manager_can_create_material(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)

        res = await manager_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        assert res.status_code == 201
        assert res.json()["name"] == "Cement"

    async def test_unassigned_manager_cannot_create_material(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        # manager NOT assigned to this project

        res = await manager_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        assert res.status_code == 403

    async def test_total_cost_is_computed_correctly(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        payload = {"name": "Steel", "quantity": 5.0, "unit": "bars", "unit_cost": 400.0}
        res = await owner_client.post(material_url(project.id, log.id), json=payload)

        assert res.status_code == 201
        assert res.json()["total_cost"] == 2000.0  # 5 * 400

    async def test_site_worker_cannot_create_material(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await worker_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)

        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /materials/{material_id}  (update)
# ---------------------------------------------------------------------------


class TestUpdateMaterial:
    async def test_owner_can_update_material(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        create_res = await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)
        material_id = create_res.json()["id"]

        res = await owner_client.patch(
            material_detail_url(project.id, log.id, material_id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )

        assert res.status_code == 200
        data = res.json()
        assert data["quantity"] == 20.0
        assert data["unit_cost"] == 300.0
        assert data["total_cost"] == 6000.0  # 20 * 300

    async def test_assigned_manager_can_update_material(
        self, owner_client: AsyncClient, manager_client: AsyncClient, seed_users, test_session_factory
    ):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        create_res = await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)
        material_id = create_res.json()["id"]

        res = await manager_client.patch(
            material_detail_url(project.id, log.id, material_id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )

        assert res.status_code == 200
        assert res.json()["quantity"] == 20.0

    async def test_unassigned_manager_cannot_update_material(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        material_id = await create_material_in_db(test_session_factory, log.id)

        res = await manager_client.patch(
            material_detail_url(project.id, log.id, material_id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )

        assert res.status_code == 403

    async def test_update_nonexistent_material_returns_404(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await owner_client.patch(
            material_detail_url(project.id, log.id, 99999),
            json=MATERIAL_UPDATE_PAYLOAD,
        )

        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        create_res = await owner_client.post(material_url(project.id, log.id), json=MATERIAL_PAYLOAD)
        material_id = create_res.json()["id"]

        res = await owner_client.patch(
            material_detail_url(project.id, log.id, material_id),
            json={"quantity": 50.0},
        )

        assert res.status_code == 200
        data = res.json()
        assert data["quantity"] == 50.0
        assert data["unit_cost"] == 250.0  # unchanged
        assert data["name"] == "Cement"  # unchanged
        assert data["total_cost"] == 12500.0  # 50 * 250

    async def test_site_worker_cannot_update_material(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        material_id = await create_material_in_db(test_session_factory, log.id)

        res = await worker_client.patch(
            material_detail_url(project.id, log.id, material_id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )

        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)

        res = await unauth_client.patch(
            material_detail_url(project.id, log.id, 1),
            json=MATERIAL_UPDATE_PAYLOAD,
        )

        assert res.status_code == 401
