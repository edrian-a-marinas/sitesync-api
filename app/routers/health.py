from fastapi import APIRouter
from sqlalchemy import text

from app.database import AsyncSessionLocal

router = APIRouter(prefix="/health", tags=["AI"])


@router.get("/")
async def health_check():
    return {
        "status": "healthy",
    }


@router.get("/db")
async def db_connection_check():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception as e:
        return {
            "status": "error",
            "database": "disconnected",
            "detail": str(e),
        }
