from fastapi import APIRouter

health_router = APIRouter()


@health_router.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
    }
