import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_owner
from app.core.limiter import limiter
from app.database import get_db
from app.models.user import User
from app.schemas.ai_query import AIQueryRequest, AIQueryResponse
from app.services.ai_query import create_query, get_queries, get_query
from app.tasks.ai_query import process_ai_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/query", response_model=AIQueryResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def submit_query(
    data: AIQueryRequest,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    query = await create_query(data, current_user, db)
    process_ai_query.delay(query.id)
    logger.info(f"AI_QUERY | query_id={query.id} | user_id={current_user.id} | task=queued")
    return query


@router.get("/query/{query_id}", response_model=AIQueryResponse)
@limiter.limit("30/minute")
async def get_query_status(
    query_id: int,
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    query = await get_query(query_id, current_user, db)
    if not query:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    return query


@router.get("/queries", response_model=list[AIQueryResponse])
@limiter.limit("30/minute")
async def list_queries(
    request: Request,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return await get_queries(current_user, db)
