import logging

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(name)s - %(message)s",
)
from contextlib import asynccontextmanager

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.limiter import configure_limiter
from app.core.logging import get_cache_label, get_db_label, get_redis_label, http_exception_handler, validation_exception_handler
from app.core.middleware import configure_middlewares
from app.core.settings import settings
from app.routers import all_routers
from app.routers.health import router as health_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"APP | ratelimit_enabled={settings.RATELIMIT_ENABLED} | debug={settings.DEBUG} | env loaded")

    logger.info(f"Server | DB={get_db_label()} | broker={get_redis_label()} | cache={get_cache_label()} | env loaded")
    yield


app = FastAPI(**settings.app_config, lifespan=lifespan)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# Apply middleware and limiter
configure_middlewares(app)
configure_limiter(app)

API_PREFIX = "/api/v1"

for router in all_routers:
    app.include_router(router, prefix=API_PREFIX)

app.include_router(health_router)
