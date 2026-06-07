from app.routers.auth import router as auth_router
from app.routers.user import router as user_router
from app.routers.project import router as project_router

all_routers = [auth_router, user_router, project_router]