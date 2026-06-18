import asyncio
import time

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.cache import redis_client
from app.core.celery import celery_app
from app.core.settings import settings
from app.database import AsyncSessionLocal

router = APIRouter(prefix="/health", tags=["AI"])


@router.get("/")
async def health_check():
    return {
        "status": "healthy",
    }


@router.get("/db")
async def db_connection_check():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception as e:
        return {
            "status": "error",
            "database": "disconnected",
            "detail": str(e),
        }


@router.get("/redis")
async def redis_health():
    try:
        start = time.monotonic()
        await redis_client.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "redis": "connected", "latency_ms": latency_ms}
    except Exception as e:
        return {"status": "error", "redis": "disconnected", "detail": str(e)}


@router.get("/celery")
async def celery_health():
    try:
        inspector = celery_app.control.inspect(timeout=2.0)
        result = await asyncio.get_event_loop().run_in_executor(None, inspector.ping)
        if not result:
            return {"status": "error", "celery": "no workers responding"}
        return {"status": "ok", "celery": "connected", "workers": len(result)}
    except Exception as e:
        return {"status": "error", "celery": "disconnected", "detail": str(e)}


@router.get("/groq")
async def groq_health():
    results = {}

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            )
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        results["groq"] = {
            "status": "ok" if response.status_code == 200 else "error",
            "http_status": response.status_code,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        results["groq"] = {"status": "error", "detail": str(e)}

    return {"status": "ok", "groq": results}


@router.get("/s3")
async def s3_health():
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
        return {"status": "error", "s3": "disconnected", "detail": str(e)}
