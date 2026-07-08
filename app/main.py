import logging

from fastapi import Depends, FastAPI  # remove depends after demo

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(name)s - %(message)s",
)
from contextlib import asynccontextmanager

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.demo import block_demo_writes  # DEMO FEATURE: remove this import if demo mode is retired
from app.core.limiter import configure_limiter
from app.core.logging import (
    check_connections,
    get_celery_label,
    get_db_label,
    get_frontend_label,
    get_mongo_label,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.middleware import configure_middlewares
from app.core.settings import settings
from app.routers import all_routers, auth_router
from app.routers.health import router as health_router

logger = logging.getLogger(__name__)

# DEMO - RUN "alembic downgrade 1094975a8b5d" if demo feature finished


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"APP | ratelimit_enabled={settings.RATELIMIT_ENABLED} | debug={settings.DEBUG} | env loaded")

    logger.info(
        f"Server | DB={get_db_label()} | frontend={get_frontend_label()} | celery={get_celery_label()} | mongo={get_mongo_label()} | env loaded"
    )

    conns = await check_connections()
    logger.info(
        f"Conn   | db={conns['db']} | broker={conns['broker']} | cache={conns['cache']} | celery={conns['celery']} | mongo={conns['mongo']} | webhook={conns['webhook']}"
    )

    yield


app = FastAPI(**settings.app_config, lifespan=lifespan)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# Apply middleware and limiter
configure_middlewares(app)
configure_limiter(app)

API_PREFIX = "/api/v1"
for router in all_routers:
    # DEMO FEATURE: auth_router excluded so login/register work without a token; remove this if-check if demo mode is retired
    if router is auth_router:
        app.include_router(router, prefix=API_PREFIX)
    else:
        app.include_router(router, prefix=API_PREFIX, dependencies=[Depends(block_demo_writes)])
app.include_router(health_router)
