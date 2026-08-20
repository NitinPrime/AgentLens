from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import ApiKey, Project
from app.models.user import User
from app.schemas.workspace import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.organizations import OrganizationError
from app.services.projects import ProjectService

router = APIRouter(tags=["projects"])


def _http(exc: OrganizationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _key_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse.model_validate(api_key)


@router.get("/organizations/{org_id}/projects", response_model=list[ProjectResponse])
async def list_projects(
    org_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Project]:
    try:
        return await ProjectService(db).list_projects(org_id, current_user.id)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.post(
    "/organizations/{org_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    org_id: UUID,
    data: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    try:
        return await ProjectService(db).create_project(org_id, current_user.id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    try:
        return await ProjectService(db).get_project_for_user(project_id, current_user.id)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Project:
    try:
        return await ProjectService(db).update_project(project_id, current_user.id, data)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await ProjectService(db).delete_project(project_id, current_user.id)
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.get("/projects/{project_id}/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyResponse]:
    try:
        keys = await ProjectService(db).list_api_keys(project_id, current_user.id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return [_key_response(key) for key in keys]


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    project_id: UUID,
    data: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedResponse:
    try:
        api_key, secret = await ProjectService(db).create_api_key(project_id, current_user, data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return ApiKeyCreatedResponse(**_key_response(api_key).model_dump(), secret=secret)


@router.post(
    "/projects/{project_id}/api-keys/{key_id}/revoke",
    response_model=ApiKeyResponse,
)
async def revoke_api_key(
    project_id: UUID,
    key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyResponse:
    try:
        api_key = await ProjectService(db).revoke_api_key(project_id, key_id, current_user.id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return _key_response(api_key)
