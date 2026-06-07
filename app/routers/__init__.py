from app.routers.auth import router as auth_router
from app.routers.user import router as user_router

all_routers = [auth_router, user_router]