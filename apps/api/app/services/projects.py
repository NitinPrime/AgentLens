from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.api_keys import generate_api_key, hash_api_key, looks_like_api_key
from app.core.slugs import unique_slug
from app.models.project import ApiKey, Project
from app.models.user import User
from app.schemas.workspace import ApiKeyCreate, ProjectCreate, ProjectUpdate
from app.services.organizations import OrganizationError, OrganizationService


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.orgs = OrganizationService(db)

    async def create_project(self, org_id: UUID, user_id: UUID, data: ProjectCreate) -> Project:
        await self.orgs.require_membership(org_id, user_id)
        project = Project(
            organization_id=org_id,
            name=data.name.strip(),
            slug=unique_slug(data.name),
            description=data.description,
        )
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def list_projects(self, org_id: UUID, user_id: UUID) -> list[Project]:
        await self.orgs.require_membership(org_id, user_id)
        result = await self.db.execute(
            select(Project)
            .where(Project.organization_id == org_id)
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_project_for_user(self, project_id: UUID, user_id: UUID) -> Project:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise OrganizationError("Project not found", status_code=404)
        await self.orgs.require_membership(project.organization_id, user_id)
        return project

    async def update_project(self, project_id: UUID, user_id: UUID, data: ProjectUpdate) -> Project:
        project = await self.get_project_for_user(project_id, user_id)
        if data.name is not None:
            project.name = data.name.strip()
        if data.description is not None:
            project.description = data.description
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def delete_project(self, project_id: UUID, user_id: UUID) -> None:
        project = await self.get_project_for_user(project_id, user_id)
        await self.db.delete(project)
        await self.db.flush()

    async def create_api_key(
        self,
        project_id: UUID,
        user: User,
        data: ApiKeyCreate,
    ) -> tuple[ApiKey, str]:
        project = await self.get_project_for_user(project_id, user.id)
        secret, prefix, key_hash = generate_api_key()
        api_key = ApiKey(
            project_id=project.id,
            created_by_id=user.id,
            name=data.name.strip(),
            key_prefix=prefix,
            key_hash=key_hash,
        )
        self.db.add(api_key)
        await self.db.flush()
        await self.db.refresh(api_key)
        return api_key, secret

    async def list_api_keys(self, project_id: UUID, user_id: UUID) -> list[ApiKey]:
        await self.get_project_for_user(project_id, user_id)
        result = await self.db.execute(
            select(ApiKey)
            .where(ApiKey.project_id == project_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_api_key(self, project_id: UUID, key_id: UUID, user_id: UUID) -> ApiKey:
        await self.get_project_for_user(project_id, user_id)
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project_id)
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise OrganizationError("API key not found", status_code=404)
        if api_key.is_revoked:
            raise OrganizationError("API key is already revoked", status_code=400)
        api_key.is_revoked = True
        api_key.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(api_key)
        return api_key

    async def authenticate_api_key(self, secret: str) -> ApiKey:
        if not looks_like_api_key(secret):
            raise OrganizationError("Invalid API key", status_code=401)

        key_hash = hash_api_key(secret)
        result = await self.db.execute(
            select(ApiKey)
            .options(selectinload(ApiKey.project))
            .where(ApiKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()
        if not api_key or api_key.is_revoked:
            raise OrganizationError("Invalid API key", status_code=401)

        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        return api_key
