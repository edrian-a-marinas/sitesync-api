import asyncio
import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.cache import redis_client
from app.core.celery import celery_app
from app.core.mongo import get_mongo_client
from app.core.settings import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"VALIDATION | ip={request.client.host} | path={request.url.path} | errors={len(exc.errors())}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTP | ip={request.client.host} | path={request.url.path} | status={exc.status_code} | detail={exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def get_db_label() -> str:
    url = settings.DATABASE_URL
    if "localhost" in url or "127.0.0.1" in url or "@postgres" in url:
        return "DEV"
    return "PROD"


def get_frontend_label() -> str:
    url = settings.ALLOWED_ORIGINS
    if "localhost" in url or "127.0.0.1" in url:
        return "DEV"
    return "PROD"


def get_celery_label() -> str:
    if settings.AWS_REGION and settings.AWS_ACCOUNT_ID:
        return "PROD"
    return "DEV"


def get_mongo_label() -> str:
    url = settings.MONGO_URL
    if "localhost" in url or "127.0.0.1" in url:
        return "DEV"
    return "PROD"


async def check_connections() -> dict:
    results = {}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        results["db"] = "connected"
    except Exception:
        results["db"] = "unreachable"

    try:
        await redis_client.ping()
        results["broker"] = "connected"
        results["cache"] = "connected"
    except Exception:
        results["broker"] = "unreachable"
        results["cache"] = "unreachable"

    try:
        with celery_app.connection() as conn:
            await asyncio.get_event_loop().run_in_executor(None, conn.ensure_connection, None, 1)
        results["celery"] = "connected"
    except Exception:
        results["celery"] = "unreachable"

    try:
        await get_mongo_client().admin.command("ping")
        results["mongo"] = "connected"
    except Exception:
        results["mongo"] = "unreachable"
    return results
