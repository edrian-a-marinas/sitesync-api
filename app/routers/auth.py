import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth import login_user, register_user

from app.core.dependencies import require_owner_or_manager, get_current_user
from app.models.user import User


from fastapi.security import OAuth2PasswordRequestForm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner_or_manager),
):
    try:
        user = await register_user(data, db, request, created_by=current_user)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    try:
        token = await login_user(
            LoginRequest(email=form_data.username, password=form_data.password),
            db,
            request
        )
        return TokenResponse(access_token=token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))