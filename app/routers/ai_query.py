from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from kombu.exceptions import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.ai_query import AIQueryRequest, AIQueryResponse
from app.services.ai_query import (
    create_query as _create_query,
)
from app.services.ai_query import (
    delete_all_queries as _delete_all_queries,
)
from app.services.ai_query import (
    delete_query as _delete_query,
)
from app.services.ai_query import (
    get_queries as _get_queries,
)
from app.services.ai_query import (
    get_query as _get_query,
)
from app.tasks.ai_query import process_ai_query

router = APIRouter(prefix="/ai", tags=["AI"])


# ==================== Tasks ====================
@router.post("/query", response_model=AIQueryResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_query(
    data: AIQueryRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    if not process_ai_query.app.control.ping(timeout=1.0):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI query service is currently unavailable. Please try again later.",
        )
    query = await _create_query(data, current_user, db)
    try:
        process_ai_query.delay(query.id)
    except OperationalError:
        await _delete_query(query.id, current_user, db)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI query service is currently unavailable. Please try again later.",
        )
    return query


# ==================== Services ====================
@router.get("/query/{query_id}", response_model=AIQueryResponse)
@limiter.limit("30/minute")
async def get_query(
    query_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    query = await _get_query(query_id, current_user, db)
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    return query


@router.get("/queries", response_model=list[AIQueryResponse])
@limiter.limit("30/minute")
async def get_queries(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await _get_queries(current_user, db, skip=skip, limit=limit)


@router.delete("/query/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_query(
    query_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    deleted = await _delete_query(query_id, current_user, db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")


@router.delete("/queries", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def delete_all_queries(
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    count = await _delete_all_queries(current_user, db)
    return {"deleted": count}
