from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.slugs import unique_slug
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.workspace import OrganizationCreate, OrganizationUpdate


class OrganizationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_organization(
        self,
        user: User,
        data: OrganizationCreate,
        role: str = "owner",
    ) -> Organization:
        org = Organization(
            name=data.name.strip(),
            slug=unique_slug(data.name),
            description=data.description,
        )
        self.db.add(org)
        await self.db.flush()
        member = OrganizationMember(
            organization_id=org.id,
            user_id=user.id,
            role=role,
        )
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(org)
        return org

    async def create_personal_organization(self, user: User) -> Organization:
        label = user.full_name or user.email.split("@")[0]
        return await self.create_organization(
            user,
            OrganizationCreate(name=f"{label}'s workspace"),
        )

    async def list_for_user(self, user_id: UUID) -> list[tuple[Organization, str]]:
        result = await self.db.execute(
            select(Organization, OrganizationMember.role)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.created_at.desc())
        )
        return [(org, role) for org, role in result.all()]

    async def get_membership(self, org_id: UUID, user_id: UUID) -> OrganizationMember | None:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_org(self, org_id: UUID) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.id == org_id))
        return result.scalar_one_or_none()

    async def require_membership(self, org_id: UUID, user_id: UUID) -> OrganizationMember:
        membership = await self.get_membership(org_id, user_id)
        if not membership:
            raise OrganizationError("Organization not found", status_code=404)
        return membership

    async def require_role(self, org_id: UUID, user_id: UUID, roles: set[str]) -> OrganizationMember:
        membership = await self.require_membership(org_id, user_id)
        if membership.role not in roles:
            raise OrganizationError("Insufficient permissions", status_code=403)
        return membership

    async def update_organization(
        self,
        org_id: UUID,
        user_id: UUID,
        data: OrganizationUpdate,
    ) -> Organization:
        await self.require_role(org_id, user_id, {"owner", "admin"})
        org = await self.get_org(org_id)
        if not org:
            raise OrganizationError("Organization not found", status_code=404)
        if data.name is not None:
            org.name = data.name.strip()
        if data.description is not None:
            org.description = data.description
        await self.db.flush()
        await self.db.refresh(org)
        return org

    async def list_members(self, org_id: UUID, user_id: UUID) -> list[OrganizationMember]:
        await self.require_membership(org_id, user_id)
        result = await self.db.execute(
            select(OrganizationMember)
            .options(selectinload(OrganizationMember.user))
            .where(OrganizationMember.organization_id == org_id)
            .order_by(OrganizationMember.created_at.asc())
        )
        return list(result.scalars().all())

    async def invite_member(self, org_id: UUID, actor_id: UUID, email: str, role: str) -> OrganizationMember:
        await self.require_role(org_id, actor_id, {"owner", "admin"})
        if role == "owner":
            actor = await self.get_membership(org_id, actor_id)
            if not actor or actor.role != "owner":
                raise OrganizationError("Only owners can grant owner role", status_code=403)

        user_result = await self.db.execute(select(User).where(User.email == email.lower()))
        user = user_result.scalar_one_or_none()
        if not user:
            raise OrganizationError("No user exists with that email", status_code=404)

        existing = await self.get_membership(org_id, user.id)
        if existing:
            raise OrganizationError("User is already a member", status_code=400)

        member = OrganizationMember(
            organization_id=org_id,
            user_id=user.id,
            role=role,
        )
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member
