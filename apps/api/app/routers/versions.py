from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.versions import VersionComparison, VersionListResponse
from app.services.organizations import OrganizationError
from app.services.projects import ProjectService
from app.services.versions import VersionService

router = APIRouter(tags=["versions"])


def _http(exc: OrganizationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/projects/{project_id}/versions", response_model=VersionListResponse)
async def list_versions(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    dimension: str = Query(default="agent_version"),
    range: str = Query(default="30d", alias="range"),
    start: datetime | None = None,
    end: datetime | None = None,
) -> VersionListResponse:
    try:
        await ProjectService(db).get_project_for_user(project_id, current_user.id)
        return await VersionService(db).list_versions(
            project_id, dimension=dimension, range_key=range, start=start, end=end
        )
    except OrganizationError as exc:
        raise _http(exc) from exc


@router.get("/projects/{project_id}/versions/compare", response_model=VersionComparison)
async def compare_versions(
    project_id: UUID,
    baseline: str = Query(..., min_length=1),
    candidate: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    dimension: str = Query(default="agent_version"),
    range: str = Query(default="30d", alias="range"),
    start: datetime | None = None,
    end: datetime | None = None,
    max_success_rate_drop: float = Query(default=0.05, ge=0, le=1),
    max_latency_increase: float = Query(default=0.25, ge=0, le=10),
    max_cost_increase: float = Query(default=0.25, ge=0, le=10),
) -> VersionComparison:
    try:
        await ProjectService(db).get_project_for_user(project_id, current_user.id)
        return await VersionService(db).compare(
            project_id,
            dimension=dimension,
            baseline=baseline,
            candidate=candidate,
            range_key=range,
            start=start,
            end=end,
            max_success_rate_drop=max_success_rate_drop,
            max_latency_increase=max_latency_increase,
            max_cost_increase=max_cost_increase,
        )
    except OrganizationError as exc:
        raise _http(exc) from exc
