from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

pytestmark = pytest.mark.asyncio


class TestHealthCheck:
    async def test_health_check_returns_healthy(self, health_client):
        response = await health_client.get("/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestDbHealthCheck:
    async def test_db_health_check_connected(self, health_client):
        response = await health_client.get("/health/db")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    async def test_db_health_check_disconnected(self, health_client):
        with patch("app.routers.health.AsyncSessionLocal") as mock_session:
            mock_session.side_effect = Exception("connection refused")
            response = await health_client.get("/health/db")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["database"] == "disconnected"


class TestRedisHealthCheck:
    async def test_redis_health_check_connected(self, health_client):
        with patch("app.routers.health.redis_client") as mock_redis:
            mock_redis.ping = AsyncMock(return_value=True)
            response = await health_client.get("/health/redis")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["redis"] == "connected"

    async def test_redis_health_check_disconnected(self, health_client):
        with patch("app.routers.health.redis_client") as mock_redis:
            mock_redis.ping = AsyncMock(side_effect=Exception("connection refused"))
            response = await health_client.get("/health/redis")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["redis"] == "disconnected"


class TestCeleryHealthCheck:
    async def test_celery_health_check_connected(self, health_client):
        with patch("app.routers.health.celery_app") as mock_celery:
            mock_inspector = MagicMock()
            mock_inspector.ping.return_value = {"worker1": {"ok": "pong"}}
            mock_celery.control.inspect.return_value = mock_inspector
            response = await health_client.get("/health/celery")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["celery"] == "connected"
            assert data["workers"] == 1

    async def test_celery_health_check_no_workers(self, health_client):
        with patch("app.routers.health.celery_app") as mock_celery:
            mock_inspector = MagicMock()
            mock_inspector.ping.return_value = None
            mock_celery.control.inspect.return_value = mock_inspector
            response = await health_client.get("/health/celery")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["celery"] == "no workers responding"

    async def test_celery_health_check_disconnected(self, health_client):
        with patch("app.routers.health.celery_app") as mock_celery:
            mock_celery.control.inspect.side_effect = Exception("broker unreachable")
            response = await health_client.get("/health/celery")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["celery"] == "disconnected"


class TestGroqHealthCheck:
    async def test_groq_health_check_connected(self, health_client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        real_get = httpx.AsyncClient.get

        async def fake_get(self, url, *args, **kwargs):
            if "groq.com" in str(url):
                return mock_response
            return await real_get(self, url, *args, **kwargs)

        with patch("httpx.AsyncClient.get", new=fake_get):
            response = await health_client.get("/health/groq")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["groq"]["groq"]["status"] == "ok"

    async def test_groq_health_check_bad_status(self, health_client):
        mock_response = MagicMock()
        mock_response.status_code = 401
        real_get = httpx.AsyncClient.get

        async def fake_get(self, url, *args, **kwargs):
            if "groq.com" in str(url):
                return mock_response
            return await real_get(self, url, *args, **kwargs)

        with patch("httpx.AsyncClient.get", new=fake_get):
            response = await health_client.get("/health/groq")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["groq"]["groq"]["status"] == "error"

    async def test_groq_health_check_disconnected(self, health_client):
        real_get = httpx.AsyncClient.get

        async def fake_get(self, url, *args, **kwargs):
            if "groq.com" in str(url):
                raise Exception("timeout")
            return await real_get(self, url, *args, **kwargs)

        with patch("httpx.AsyncClient.get", new=fake_get):
            response = await health_client.get("/health/groq")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["groq"]["groq"]["status"] == "error"


class TestS3HealthCheck:
    async def test_s3_health_check_connected(self, health_client):
        mock_client = MagicMock()
        mock_client.head_bucket.return_value = {}
        with patch("app.services.s3.get_s3_client", return_value=mock_client):
            response = await health_client.get("/health/s3")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["s3"] == "connected"

    async def test_s3_health_check_disconnected(self, health_client):
        with patch("app.services.s3.get_s3_client", side_effect=Exception("access denied")):
            response = await health_client.get("/health/s3")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert data["s3"] == "disconnected"
