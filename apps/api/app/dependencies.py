from typing import Any
from uuid import UUID

import redis.asyncio as redis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import verify_token
from app.core.token_store import MemoryTokenStore
from app.core.api_keys import looks_like_api_key
from app.database import AsyncSessionLocal, get_db
from app.models.project import ApiKey
from app.models.user import User
from app.services.auth import AuthService
from app.services.organizations import OrganizationError
from app.services.projects import ProjectService

settings = get_settings()
security = HTTPBearer(auto_error=False)

_redis_client: Any = None


async def get_redis() -> Any:
    global _redis_client
    if _redis_client is None:
        if settings.uses_memory_redis:
            _redis_client = MemoryTokenStore()
        else:
            _redis_client = redis.from_url(settings.redis_url, decode_responses=False)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        close = getattr(_redis_client, "aclose", None)
        if close is not None:
            await close()
        _redis_client = None


def get_session_factory() -> Any:
    """Session factory for handlers that must not hold a connection.

    Server-sent-event streams live for minutes, so they open a short session for
    the authorization check and close it before streaming instead of relying on
    a request-scoped session.
    """

    return AsyncSessionLocal


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    redis_client: Any = Depends(get_redis),
) -> AuthService:
    return AuthService(db=db, redis_client=redis_client)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = verify_token(credentials.credentials, expected_type="access")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await auth_service.get_user_by_id(UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def get_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    if credentials is None or not looks_like_api_key(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await ProjectService(db).authenticate_api_key(credentials.credentials)
    except OrganizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
