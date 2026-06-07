import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"VALIDATION | ip={request.client.host} | path={request.url.path} | errors={len(exc.errors())}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTP | ip={request.client.host} | path={request.url.path} | status={exc.status_code} | detail={exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
