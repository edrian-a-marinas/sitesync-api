import asyncio
import time

import httpx
import requests
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.cache import redis_client
from app.core.celery import celery_app
from app.core.mongo import get_mongo_client
from app.core.settings import settings
from app.database import AsyncSessionLocal

router = APIRouter(prefix="/health", tags=["AI"])


@router.get("/")
async def health_check():
    return {
        "status": "healthy",
    }


@router.get("/db")
async def db_connection_check(response: Response):
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected",
        }
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "error",
            "database": "disconnected",
            "detail": str(e),
        }


@router.get("/redis")
async def redis_health(response: Response):
    try:
        start = time.monotonic()
        await redis_client.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "redis": "connected", "latency_ms": latency_ms}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "redis": "disconnected", "detail": str(e)}


@router.get("/mongo")
async def mongo_health(response: Response):
    try:
        start = time.monotonic()
        await get_mongo_client().admin.command("ping")
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "mongo": "connected", "latency_ms": latency_ms}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "mongo": "disconnected", "detail": str(e)}


@router.get("/celery")
async def celery_health(response: Response):
    try:
        with celery_app.connection() as conn:
            await asyncio.get_event_loop().run_in_executor(None, conn.ensure_connection, None, 1)
        return {"status": "ok", "celery": "broker reachable"}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "celery": "disconnected", "detail": str(e)}


@router.get("/webhook")
async def webhook_health(response: Response):
    try:
        start = time.monotonic()
        res = requests.head(settings.WEBHOOK_URL, timeout=3)
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        if res.status_code >= 500:
            raise requests.RequestException(f"status_code={res.status_code}")
        return {"status": "ok", "webhook": "connected", "latency_ms": latency_ms}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "webhook": "disconnected", "detail": str(e)}


@router.get("/groq")
async def groq_health(response: Response):
    results = {}
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=5.0) as client:
            groq_response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            )
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        is_ok = groq_response.status_code == 200
        results["groq"] = {
            "status": "ok" if is_ok else "error",
            "http_status": groq_response.status_code,
            "latency_ms": latency_ms,
        }
        if not is_ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ok" if is_ok else "error", "groq": results}
    except Exception as e:
        results["groq"] = {"status": "error", "detail": str(e)}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "groq": results}


@router.get("/s3")
async def s3_health(response: Response):
    try:
        from app.services.s3 import get_s3_client

        def _check():
            client = get_s3_client()
            client.head_bucket(Bucket=settings.AWS_S3_BUCKET)

        start = time.monotonic()
        await asyncio.get_event_loop().run_in_executor(None, _check)
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "s3": "connected", "latency_ms": latency_ms}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "s3": "disconnected", "detail": str(e)}
