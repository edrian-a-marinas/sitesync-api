from httpx import AsyncClient

from tests.conftest import create_project

PROJECT_PAYLOAD = {
    "name": "Test Project",
    "location": "Manila",
    "total_budget": 1000000.0,
    "start_date": "2026-01-01",
    "target_end_date": "2026-12-31",
    "status": "Active",
}


class TestProjectCreate:
    async def test_owner_can_create(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 201
        assert res.json()["name"] == "Test Project"

    async def test_manager_cannot_create(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 403

    async def test_unauthenticated(self, unauth_client: AsyncClient):
        res = await unauth_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        assert res.status_code == 401


class TestProjectList:
    async def test_owner_sees_all(self, owner_client: AsyncClient, seed_users):
        await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        await owner_client.post("/api/v1/projects", json={**PROJECT_PAYLOAD, "name": "Project 2"})
        res = await owner_client.get("/api/v1/projects")
        assert res.status_code == 200
        assert len(res.json()) >= 2

    async def test_manager_sees_only_assigned(self, manager_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            project = await create_project(session, seed_users["owner"].id)
            from app.models.project import ProjectAssignment

            assignment = ProjectAssignment(project_id=project.id, user_id=seed_users["manager"].id)
            session.add(assignment)
            await session.commit()
        res = await manager_client.get("/api/v1/projects")
        assert res.status_code == 200
        assert any(p["id"] == project.id for p in res.json())


class TestProjectGet:
    async def test_owner_can_get(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        project_id = res.json()["id"]
        res = await owner_client.get(f"/api/v1/projects/{project_id}")
        assert res.status_code == 200

    async def test_not_found(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.get("/api/v1/projects/99999")
        assert res.status_code == 404

    async def test_manager_access_denied_unassigned(self, manager_client: AsyncClient, seed_users, test_session_factory):
        async with test_session_factory() as session:
            project = await create_project(session, seed_users["owner"].id)
        res = await manager_client.get(f"/api/v1/projects/{project.id}")
        assert res.status_code == 404


class TestProjectUpdate:
    async def test_owner_can_update(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        project_id = res.json()["id"]
        res = await owner_client.patch(f"/api/v1/projects/{project_id}", json={"status": "Completed"})
        assert res.status_code == 200
        assert res.json()["status"] == "Completed"

    async def test_manager_cannot_update(self, manager_client: AsyncClient, seed_users):
        res = await manager_client.patch(
            "/api/v1/projects/99999",
            json={"status": "Completed"},
        )
        assert res.status_code == 403


class TestAssignManager:
    async def test_assign_valid_manager(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        project_id = res.json()["id"]
        res = await owner_client.post(
            f"/api/v1/projects/{project_id}/assign-manager",
            json={"user_id": seed_users["manager"].id},
        )
        assert res.status_code == 200
        assert res.json()["message"] == "Manager assigned successfully"

    async def test_assign_non_manager_fails(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        project_id = res.json()["id"]
        res = await owner_client.post(
            f"/api/v1/projects/{project_id}/assign-manager",
            json={"user_id": seed_users["worker"].id},
        )
        assert res.status_code == 400


class TestPhases:
    async def test_create_phase(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        project_id = res.json()["id"]
        res = await owner_client.post(
            f"/api/v1/projects/{project_id}/phases",
            json={"name": "Foundation", "allocated_budget": 500000.0, "status": "Not Started"},
        )
        assert res.status_code == 201
        assert res.json()["name"] == "Foundation"

    async def test_update_phase(self, owner_client: AsyncClient, seed_users):
        res = await owner_client.post("/api/v1/projects", json=PROJECT_PAYLOAD)
        project_id = res.json()["id"]
        res = await owner_client.post(
            f"/api/v1/projects/{project_id}/phases",
            json={"name": "Foundation", "allocated_budget": 500000.0, "status": "Not Started"},
        )
        phase_id = res.json()["id"]
        res = await owner_client.patch(
            f"/api/v1/projects/{project_id}/phases/{phase_id}",
            json={"status": "In Progress"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "In Progress"
