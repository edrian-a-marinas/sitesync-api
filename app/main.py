import logging

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(name)s - %(message)s",
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.limiter import configure_limiter
from app.core.logging import http_exception_handler, validation_exception_handler
from app.core.middleware import configure_middlewares
from app.core.settings import settings
from app.routers import all_routers
from app.routers.health import router as health_router

app = FastAPI(**settings.app_config)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# Apply middleware and limiter
configure_middlewares(app)
configure_limiter(app)

API_PREFIX = "/api/v1"

for router in all_routers:
    app.include_router(router, prefix=API_PREFIX)

app.include_router(health_router)
