from app.routers.attendance import router as attendance_router
from app.routers.auth import router as auth_router
from app.routers.daily_log import router as daily_log_router
from app.routers.project import router as project_router
from app.routers.user import router as user_router

all_routers = [auth_router, user_router, project_router, daily_log_router, attendance_router]
