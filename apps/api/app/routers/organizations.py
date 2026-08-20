from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.workspace import (
    OrganizationCreate,
    OrganizationInvite,
    OrganizationMemberResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.organizations import OrganizationError, OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _org_response(org, role: str | None = None) -> OrganizationResponse:
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        role=role,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


def _raise(exc: OrganizationError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationResponse]:
    service = OrganizationService(db)
    rows = await service.list_for_user(current_user.id)
    if not rows:
        await service.create_personal_organization(current_user)
        rows = await service.list_for_user(current_user.id)
    return [_org_response(org, role) for org, role in rows]


@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    service = OrganizationService(db)
    org = await service.create_organization(current_user, data)
    return _org_response(org, "owner")


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    service = OrganizationService(db)
    try:
        membership = await service.require_membership(org_id, current_user.id)
        org = await service.get_org(membership.organization_id)
    except OrganizationError as exc:
        _raise(exc)
        raise
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return _org_response(org, membership.role)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: UUID,
    data: OrganizationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    service = OrganizationService(db)
    try:
        org = await service.update_organization(org_id, current_user.id, data)
        membership = await service.require_membership(org.id, current_user.id)
    except OrganizationError as exc:
        _raise(exc)
        raise
    return _org_response(org, membership.role)


@router.get("/{org_id}/members", response_model=list[OrganizationMemberResponse])
async def list_members(
    org_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationMemberResponse]:
    service = OrganizationService(db)
    try:
        members = await service.list_members(org_id, current_user.id)
    except OrganizationError as exc:
        _raise(exc)
        raise
    return [
        OrganizationMemberResponse(
            id=member.id,
            user_id=member.user_id,
            email=member.user.email if member.user else None,
            full_name=member.user.full_name if member.user else None,
            role=member.role,
            created_at=member.created_at,
        )
        for member in members
    ]


@router.post("/{org_id}/members", response_model=OrganizationMemberResponse, status_code=201)
async def invite_member(
    org_id: UUID,
    data: OrganizationInvite,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationMemberResponse:
    service = OrganizationService(db)
    try:
        member = await service.invite_member(org_id, current_user.id, data.email, data.role)
        members = await service.list_members(org_id, current_user.id)
    except OrganizationError as exc:
        _raise(exc)
        raise
    matched = next(m for m in members if m.id == member.id)
    return OrganizationMemberResponse(
        id=matched.id,
        user_id=matched.user_id,
        email=matched.user.email if matched.user else None,
        full_name=matched.user.full_name if matched.user else None,
        role=matched.role,
        created_at=matched.created_at,
    )
