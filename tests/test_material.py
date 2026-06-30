from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.daily_log import DailyLog
from app.models.material import Material
from app.models.project import Project, ProjectAssignment, WorkerAssignment

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


def material_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/materials"


def material_detail_url(project_id: int, log_id: int, material_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/materials/{material_id}"


# ---------------------------------------------------------------------------
# Session-scoped seeds
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_material_data(test_session_factory, seed_users):
    """
    - owner_project: owner-only, has a log and pre-seeded material
    - manager_project: manager assigned, has a log and pre-seeded material
    - unassigned_project: no manager assignment, has a log and material
    - worker_project: worker assigned, has a log and pre-seeded material
    """
    async with test_session_factory() as session:
        async with session.begin():
            owner_project = Project(
                owner_id=seed_users["owner"].id,
                name="Mat Owner Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            manager_project = Project(
                owner_id=seed_users["owner"].id,
                name="Mat Manager Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            unassigned_project = Project(
                owner_id=seed_users["owner"].id,
                name="Mat Unassigned Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            worker_project = Project(
                owner_id=seed_users["owner"].id,
                name="Mat Worker Project",
                location="Manila",
                total_budget=1_000_000,
                start_date=date(2026, 1, 1),
                target_end_date=date(2026, 12, 31),
                status="Active",
            )
            session.add_all([owner_project, manager_project, unassigned_project, worker_project])
            await session.flush()

            session.add(ProjectAssignment(project_id=manager_project.id, user_id=seed_users["manager"].id))
            session.add(WorkerAssignment(project_id=worker_project.id, user_id=seed_users["worker"].id))

            owner_log = DailyLog(
                project_id=owner_project.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 1, 1), work_accomplished="Test"
            )
            manager_log = DailyLog(
                project_id=manager_project.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 1, 1), work_accomplished="Test"
            )
            unassigned_log = DailyLog(
                project_id=unassigned_project.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 1, 1), work_accomplished="Test"
            )
            worker_log = DailyLog(
                project_id=worker_project.id, submitted_by=seed_users["owner"].id, log_date=date(2026, 1, 1), work_accomplished="Test"
            )
            session.add_all([owner_log, manager_log, unassigned_log, worker_log])
            await session.flush()

            owner_material = Material(daily_log_id=owner_log.id, name="Cement", quantity=10.0, unit="bags", unit_cost=250.0)
            manager_material = Material(daily_log_id=manager_log.id, name="Cement", quantity=10.0, unit="bags", unit_cost=250.0)
            worker_material = Material(daily_log_id=worker_log.id, name="Cement", quantity=10.0, unit="bags", unit_cost=250.0)
            unassigned_material = Material(daily_log_id=unassigned_log.id, name="Cement", quantity=10.0, unit="bags", unit_cost=250.0)
            session.add_all([owner_material, manager_material, worker_material, unassigned_material])

    yield {
        "owner_project": owner_project,
        "owner_log": owner_log,
        "owner_material": owner_material,
        "manager_project": manager_project,
        "manager_log": manager_log,
        "manager_material": manager_material,
        "unassigned_project": unassigned_project,
        "unassigned_log": unassigned_log,
        "unassigned_material": unassigned_material,
        "worker_project": worker_project,
        "worker_log": worker_log,
        "worker_material": worker_material,
    }
    async with test_session_factory() as session:
        async with session.begin():
            project_ids = [owner_project.id, manager_project.id, unassigned_project.id, worker_project.id]
            log_ids = [owner_log.id, manager_log.id, unassigned_log.id, worker_log.id]
            await session.execute(delete(Material).where(Material.daily_log_id.in_(log_ids)))
            await session.execute(delete(DailyLog).where(DailyLog.id.in_(log_ids)))
            await session.execute(delete(ProjectAssignment).where(ProjectAssignment.project_id.in_(project_ids)))
            await session.execute(delete(WorkerAssignment).where(WorkerAssignment.project_id.in_(project_ids)))
            await session.execute(delete(Project).where(Project.id.in_(project_ids)))


# ---------------------------------------------------------------------------
# GET /materials
# ---------------------------------------------------------------------------


class TestGetMaterials:
    async def test_owner_can_list_materials(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await owner_client.get(material_url(d["owner_project"].id, d["owner_log"].id))
        assert res.status_code == 200
        assert len(res.json()) >= 1
        assert res.json()[0]["name"] == "Cement"

    async def test_manager_can_list_materials(self, manager_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await manager_client.get(material_url(d["manager_project"].id, d["manager_log"].id))
        assert res.status_code == 200
        assert len(res.json()) >= 1

    async def test_assigned_worker_can_list_materials(self, worker_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await worker_client.get(material_url(d["worker_project"].id, d["worker_log"].id))
        assert res.status_code == 200
        assert len(res.json()) >= 1

    async def test_unassigned_worker_gets_empty_list(self, worker_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await worker_client.get(material_url(d["unassigned_project"].id, d["unassigned_log"].id))
        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await unauth_client.get(material_url(d["owner_project"].id, d["owner_log"].id))
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /materials
# ---------------------------------------------------------------------------


class TestCreateMaterial:
    async def test_owner_can_create_material(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await owner_client.post(
            material_url(d["owner_project"].id, d["owner_log"].id),
            json={"name": "Steel", "quantity": 5.0, "unit": "bars", "unit_cost": 400.0},
        )
        assert res.status_code == 201
        assert res.json()["name"] == "Steel"
        assert res.json()["daily_log_id"] == d["owner_log"].id

    async def test_assigned_manager_can_create_material(self, manager_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await manager_client.post(
            material_url(d["manager_project"].id, d["manager_log"].id),
            json={"name": "Sand", "quantity": 3.0, "unit": "bags", "unit_cost": 100.0},
        )
        assert res.status_code == 201
        assert res.json()["name"] == "Sand"

    async def test_unassigned_manager_cannot_create_material(self, manager_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await manager_client.post(
            material_url(d["unassigned_project"].id, d["unassigned_log"].id),
            json=MATERIAL_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_total_cost_is_computed_correctly(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await owner_client.post(
            material_url(d["owner_project"].id, d["owner_log"].id),
            json={"name": "Gravel", "quantity": 4.0, "unit": "tons", "unit_cost": 500.0},
        )
        assert res.status_code == 201
        assert res.json()["total_cost"] == 2000.0  # 4 * 500

    async def test_site_worker_cannot_create_material(self, worker_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await worker_client.post(
            material_url(d["owner_project"].id, d["owner_log"].id),
            json=MATERIAL_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_create(self, unauth_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await unauth_client.post(
            material_url(d["owner_project"].id, d["owner_log"].id),
            json=MATERIAL_PAYLOAD,
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /materials/{material_id}
# ---------------------------------------------------------------------------


class TestUpdateMaterial:
    async def test_owner_can_update_material(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await owner_client.patch(
            material_detail_url(d["owner_project"].id, d["owner_log"].id, d["owner_material"].id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )
        assert res.status_code == 200
        assert res.json()["quantity"] == 20.0
        assert res.json()["unit_cost"] == 300.0
        assert res.json()["total_cost"] == 6000.0  # 20 * 300

    async def test_assigned_manager_can_update_material(self, manager_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await manager_client.patch(
            material_detail_url(d["manager_project"].id, d["manager_log"].id, d["manager_material"].id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )
        assert res.status_code == 200
        assert res.json()["quantity"] == 20.0

    async def test_unassigned_manager_cannot_update_material(self, manager_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await manager_client.patch(
            material_detail_url(d["unassigned_project"].id, d["unassigned_log"].id, d["unassigned_material"].id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_update_nonexistent_material_returns_404(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await owner_client.patch(
            material_detail_url(d["owner_project"].id, d["owner_log"].id, 99999),
            json=MATERIAL_UPDATE_PAYLOAD,
        )
        assert res.status_code == 404

    async def test_partial_update_only_changes_provided_fields(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await owner_client.patch(
            material_detail_url(d["owner_project"].id, d["owner_log"].id, d["owner_material"].id),
            json={"quantity": 50.0},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["quantity"] == 50.0
        assert data["name"] == "Cement"  # unchanged

    async def test_site_worker_cannot_update_material(self, worker_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await worker_client.patch(
            material_detail_url(d["worker_project"].id, d["worker_log"].id, d["worker_material"].id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_update(self, unauth_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await unauth_client.patch(
            material_detail_url(d["owner_project"].id, d["owner_log"].id, d["owner_material"].id),
            json=MATERIAL_UPDATE_PAYLOAD,
        )
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /materials/{material_id}
# ---------------------------------------------------------------------------
class TestDeleteMaterial:
    async def test_owner_can_delete_material(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        create_res = await owner_client.post(
            material_url(d["owner_project"].id, d["owner_log"].id),
            json={"name": "Plywood", "quantity": 2.0, "unit": "sheets", "unit_cost": 50.0},
        )
        material_id = create_res.json()["id"]
        res = await owner_client.delete(material_detail_url(d["owner_project"].id, d["owner_log"].id, material_id))
        assert res.status_code == 204

    async def test_assigned_manager_can_delete_material(self, manager_client: AsyncClient, seed_material_data):
        d = seed_material_data
        create_res = await manager_client.post(
            material_url(d["manager_project"].id, d["manager_log"].id),
            json={"name": "Plywood", "quantity": 2.0, "unit": "sheets", "unit_cost": 50.0},
        )
        material_id = create_res.json()["id"]
        res = await manager_client.delete(material_detail_url(d["manager_project"].id, d["manager_log"].id, material_id))
        assert res.status_code == 204

    async def test_unassigned_manager_cannot_delete_material(self, manager_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await manager_client.delete(material_detail_url(d["unassigned_project"].id, d["unassigned_log"].id, d["unassigned_material"].id))
        assert res.status_code == 403

    async def test_delete_nonexistent_material_returns_404(self, owner_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await owner_client.delete(material_detail_url(d["owner_project"].id, d["owner_log"].id, 99999))
        assert res.status_code == 404

    async def test_site_worker_cannot_delete_material(self, worker_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await worker_client.delete(material_detail_url(d["worker_project"].id, d["worker_log"].id, d["worker_material"].id))
        assert res.status_code == 403

    async def test_unauthenticated_cannot_delete(self, unauth_client: AsyncClient, seed_material_data):
        d = seed_material_data
        res = await unauth_client.delete(material_detail_url(d["owner_project"].id, d["owner_log"].id, d["owner_material"].id))
        assert res.status_code == 401
