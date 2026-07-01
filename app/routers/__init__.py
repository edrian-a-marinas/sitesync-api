from app.routers.ai_query import router as ai_query_router
from app.routers.attendance import router as attendance_router
from app.routers.auth import router as auth_router
from app.routers.daily_log import router as daily_log_router
from app.routers.dashboard import router as dashboard_router
from app.routers.equipment import router as equipment_router
from app.routers.incident import router as incident_router
from app.routers.material import router as material_router
from app.routers.ml import router as ml_router
from app.routers.project import router as project_router
from app.routers.report import router as report_router
from app.routers.site_photo import router as site_photo_router
from app.routers.user import router as user_router
from app.routers.worker import router as worker_router

all_routers = [
    auth_router,
    user_router,
    project_router,
    daily_log_router,
    attendance_router,
    material_router,
    equipment_router,
    incident_router,
    dashboard_router,
    ai_query_router,
    report_router,
    ml_router,
    site_photo_router,
    worker_router,
]
