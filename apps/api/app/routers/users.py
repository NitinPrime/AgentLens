from fastapi import APIRouter, Depends

from app.dependencies import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import UserResponse, UserUpdate
from app.services.auth import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    return await auth_service.update_user(current_user, data)
