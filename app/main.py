from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.limiter import configure_limiter

# from app.core.middleware import configure_middlewares
from app.core.logging import http_exception_handler, validation_exception_handler
from app.core.settings import settings
from app.routers import all_routers

app = FastAPI(**settings.app_config)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

# Apply middleware and limiter
# configure_middlewares(app)
configure_limiter(app)

API_PREFIX = "/api/v1"

for router in all_routers:
    app.include_router(router, prefix=API_PREFIX)
