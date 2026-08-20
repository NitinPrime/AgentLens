from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    try:
        return await auth_service.create_user(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user = await auth_service.authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return auth_service.create_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        return await auth_service.refresh_tokens(data.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout", response_model=MessageResponse)
async def logout(
    data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
    _: User = Depends(get_current_user),
) -> MessageResponse:
    await auth_service.logout(data.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    token = await auth_service.request_password_reset(data.email)
    response = MessageResponse(
        message="If an account exists for that email, a reset link has been sent."
    )
    if token:
        response.message = (
            f"If an account exists for that email, a reset link has been sent. "
            f"[dev token: {token}]"
        )
    return response


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    try:
        await auth_service.reset_password(data.token, data.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Password reset successfully")
