import secrets
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserCreate, UserUpdate

settings = get_settings()


class AuthService:
    def __init__(self, db: AsyncSession, redis_client: Any = None):
        self.db = db
        self.redis = redis_client

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, data: UserCreate) -> User:
        existing = await self.get_user_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=data.email.lower(),
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        from app.services.organizations import OrganizationService

        await OrganizationService(self.db).create_personal_organization(user)
        return user

    async def authenticate_user(self, email: str, password: str) -> User | None:
        user = await self.get_user_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    def create_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        user_id = verify_token(refresh_token, expected_type="refresh")

        if self.redis:
            is_blacklisted = await self.redis.get(f"blacklist:refresh:{refresh_token}")
            if is_blacklisted:
                raise ValueError("Token has been revoked")

        user = await self.get_user_by_id(UUID(user_id))
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")

        return self.create_tokens(user)

    async def logout(self, refresh_token: str) -> None:
        if not self.redis:
            return

        ttl_seconds = settings.refresh_token_expire_days * 24 * 60 * 60
        await self.redis.setex(f"blacklist:refresh:{refresh_token}", ttl_seconds, "1")

    async def request_password_reset(self, email: str) -> str | None:
        user = await self.get_user_by_email(email)
        if not user or not self.redis:
            return None

        token = secrets.token_urlsafe(32)
        ttl_seconds = settings.password_reset_token_expire_minutes * 60
        await self.redis.setex(f"password_reset:{token}", ttl_seconds, str(user.id))
        return token

    async def reset_password(self, token: str, new_password: str) -> User:
        if not self.redis:
            raise ValueError("Password reset unavailable")

        user_id = await self.redis.get(f"password_reset:{token}")
        if not user_id:
            raise ValueError("Invalid or expired reset token")

        user = await self.get_user_by_id(UUID(user_id.decode()))
        if not user:
            raise ValueError("User not found")

        user.hashed_password = get_password_hash(new_password)
        await self.db.flush()
        await self.redis.delete(f"password_reset:{token}")
        return user

    async def update_user(self, user: User, data: UserUpdate) -> User:
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.avatar_url is not None:
            user.avatar_url = data.avatar_url
        await self.db.flush()
        await self.db.refresh(user)
        return user
