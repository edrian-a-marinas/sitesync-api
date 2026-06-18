import io
from datetime import date
from unittest.mock import patch

from httpx import AsyncClient

from app.models.daily_log import DailyLog
from app.models.project import Project, ProjectAssignment, WorkerAssignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def site_photo_url(project_id: int, log_id: int) -> str:
    return f"/api/v1/projects/{project_id}/daily-logs/{log_id}/site-photos"


async def create_project(session_factory, owner_id: int) -> Project:
    async with session_factory() as session:
        project = Project(
            owner_id=owner_id,
            name="Photo Test Project",
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


def _png_file():
    """Minimal valid PNG bytes."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _upload_files(filename="photo.png", content_type="image/png", data=None):
    file_data = data or _png_file()
    return {"file": (filename, io.BytesIO(file_data), content_type)}


# ---------------------------------------------------------------------------
# GET /site-photos  (list)
# ---------------------------------------------------------------------------
class TestGetSitePhotos:
    async def test_owner_can_list_photos(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        res = await owner_client.get(site_photo_url(project.id, log.id))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    async def test_assigned_manager_can_list_photos(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        res = await manager_client.get(site_photo_url(project.id, log.id))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    async def test_assigned_worker_can_list_photos(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_worker(test_session_factory, project.id, seed_users["worker"].id)
        res = await worker_client.get(site_photo_url(project.id, log.id))
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    async def test_unassigned_worker_gets_empty_list(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        res = await worker_client.get(site_photo_url(project.id, log.id))
        assert res.status_code == 200
        assert res.json() == []

    async def test_unauthenticated_cannot_list(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        res = await unauth_client.get(site_photo_url(project.id, log.id))
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /site-photos  (upload)
# ---------------------------------------------------------------------------
class TestUploadSitePhoto:
    async def test_owner_can_upload_photo(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        with patch("app.services.site_photo.upload_file", return_value="site_photos/1/photo.png"):
            with patch("app.services.site_photo.generate_presigned_url", return_value="https://fake-url.com/photo.png"):
                res = await owner_client.post(
                    site_photo_url(project.id, log.id),
                    files=_upload_files(),
                )
        assert res.status_code == 201
        data = res.json()
        assert data["daily_log_id"] == log.id
        assert data["filename"] == "photo.png"
        assert data["content_type"] == "image/png"
        assert "file_url" in data

    async def test_assigned_manager_can_upload_photo(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        await assign_manager(test_session_factory, project.id, seed_users["manager"].id)
        with patch("app.services.site_photo.upload_file", return_value="site_photos/1/photo.png"):
            with patch("app.services.site_photo.generate_presigned_url", return_value="https://fake-url.com/photo.png"):
                res = await manager_client.post(
                    site_photo_url(project.id, log.id),
                    files=_upload_files(),
                )
        assert res.status_code == 201
        assert res.json()["filename"] == "photo.png"

    async def test_unassigned_manager_cannot_upload_photo(self, manager_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        with patch("app.services.site_photo.upload_file", return_value="site_photos/1/photo.png"):
            res = await manager_client.post(
                site_photo_url(project.id, log.id),
                files=_upload_files(),
            )
        assert res.status_code == 403

    async def test_site_worker_cannot_upload_photo(self, worker_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        res = await worker_client.post(
            site_photo_url(project.id, log.id),
            files=_upload_files(),
        )
        assert res.status_code == 403

    async def test_unauthenticated_cannot_upload(self, unauth_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        res = await unauth_client.post(
            site_photo_url(project.id, log.id),
            files=_upload_files(),
        )
        assert res.status_code == 401

    async def test_invalid_file_type_rejected(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        res = await owner_client.post(
            site_photo_url(project.id, log.id),
            files=_upload_files(filename="malware.exe", content_type="application/octet-stream"),
        )
        assert res.status_code == 400
        assert "not allowed" in res.json()["detail"].lower()

    async def test_oversized_file_rejected(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        oversized = b"x" * (10 * 1024 * 1024 + 1)  # 10MB + 1 byte
        res = await owner_client.post(
            site_photo_url(project.id, log.id),
            files=_upload_files(filename="big.png", content_type="image/png", data=oversized),
        )
        assert res.status_code == 400
        assert "10mb" in res.json()["detail"].lower()

    async def test_upload_to_nonexistent_log_returns_404(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        with patch("app.services.site_photo.upload_file", return_value="site_photos/99999/photo.png"):
            res = await owner_client.post(
                site_photo_url(project.id, 99999),
                files=_upload_files(),
            )
        assert res.status_code == 404

    async def test_pdf_upload_allowed(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        with patch("app.services.site_photo.upload_file", return_value="site_photos/1/doc.pdf"):
            with patch("app.services.site_photo.generate_presigned_url", return_value="https://fake-url.com/doc.pdf"):
                res = await owner_client.post(
                    site_photo_url(project.id, log.id),
                    files=_upload_files(filename="doc.pdf", content_type="application/pdf", data=pdf_bytes),
                )
        assert res.status_code == 201
        assert res.json()["content_type"] == "application/pdf"

    async def test_uploaded_photo_appears_in_list(self, owner_client: AsyncClient, seed_users, test_session_factory):
        project = await create_project(test_session_factory, seed_users["owner"].id)
        log = await create_daily_log(test_session_factory, project.id, seed_users["owner"].id)
        with patch("app.services.site_photo.upload_file", return_value="site_photos/1/photo.png"):
            with patch("app.services.site_photo.generate_presigned_url", return_value="https://fake-url.com/photo.png"):
                upload_res = await owner_client.post(
                    site_photo_url(project.id, log.id),
                    files=_upload_files(),
                )
        assert upload_res.status_code == 201

        with patch("app.services.site_photo.generate_presigned_url", return_value="https://fake-url.com/photo.png"):
            list_res = await owner_client.get(site_photo_url(project.id, log.id))
        assert list_res.status_code == 200
        filenames = [p["filename"] for p in list_res.json()]
        assert "photo.png" in filenames
