import logging

from fastapi import FastAPI

from app.core.settings import settings
#from app.core.middleware import configure_middlewares
#from app.core.limiter import configure_limiter
#from app.core.redis import redis_client

#from app.routers.auth import router as auth_router
#from app.routers.equipment import router as equipment_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(**settings.fastapi_kwargs)

""" Later on redis — use lifespan.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.connect()
    yield
    await redis_client.disconnect()

app = FastAPI(**settings.fastapi_kwargs, lifespan=lifespan)
"""

# Apply middleware and limiter
#configure_middlewares(app)
#configure_limiter(app)

API_PREFIX = "/api/v1"

# Auth
#app.include_router(auth_router, prefix=API_PREFIX)

# App logic
#app.include_router(equipment_router, prefix=API_PREFIX)