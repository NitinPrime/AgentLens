from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.analytics import AnalyticsResponse
from app.services.analytics import AnalyticsService
from app.services.organizations import OrganizationError

router = APIRouter(tags=["analytics"])


def _http(exc: OrganizationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/organizations/{org_id}/analytics", response_model=AnalyticsResponse)
async def organization_analytics(
    org_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    range: str = Query(default="7d", alias="range"),
    project_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> AnalyticsResponse:
    try:
        return await AnalyticsService(db).get_analytics(
            org_id,
            current_user.id,
            range_key=range,
            project_id=project_id,
            start=start,
            end=end,
        )
    except OrganizationError as exc:
        raise _http(exc) from exc
