from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.settings import settings

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)


def configure_limiter(app: FastAPI) -> None:

    limiter._enabled = settings.RATELIMIT_ENABLED
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
