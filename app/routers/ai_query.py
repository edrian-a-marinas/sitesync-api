from fastapi import APIRouter, Depends, HTTPException, Request, status
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
    get_queries as _get_queries,
)
from app.services.ai_query import (
    get_query as _get_query,
)
from app.tasks.ai_query import process_ai_query

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/query", response_model=AIQueryResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_query(
    data: AIQueryRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    query = await _create_query(data, current_user, db)
    process_ai_query.delay(query.id)
    return query


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
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await _get_queries(current_user, db)
