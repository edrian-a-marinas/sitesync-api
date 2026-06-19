import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.settings import settings

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"VALIDATION | ip={request.client.host} | path={request.url.path} | errors={len(exc.errors())}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTP | ip={request.client.host} | path={request.url.path} | status={exc.status_code} | detail={exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def get_db_label() -> str:
    url = settings.DATABASE_URL
    if "localhost" in url or "127.0.0.1" in url:
        return "DEV"
    return "PROD"


def get_redis_label() -> str:
    url = settings.REDIS_URL
    if "localhost" in url or "127.0.0.1" in url:
        return "DEV"
    return "PROD"


def get_cache_label() -> str:
    url = settings.REDIS_CACHE_URL
    if "localhost" in url or "127.0.0.1" in url:
        return "DEV"
    return "PROD"
