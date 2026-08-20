from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.project import Project
from app.models.trace import LLMCall, Trace
from app.schemas.analytics import AnalyticsResponse, AnalyticsSummary, ModelUsage, TimeseriesPoint
from app.services.organizations import OrganizationError, OrganizationService

settings = get_settings()

RANGE_HOURS = {
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
    "90d": 24 * 90,
}


def resolve_window(
    range_key: str,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime, str, str]:
    now = datetime.now(timezone.utc)
    if range_key == "custom":
        if not start or not end:
            raise OrganizationError("Custom range requires start and end", status_code=400)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end <= start:
            raise OrganizationError("end must be after start", status_code=400)
        delta = end - start
        grain = "hour" if delta <= timedelta(hours=48) else "day"
        return start, end, grain, "custom"

    hours = RANGE_HOURS.get(range_key)
    if hours is None:
        raise OrganizationError("Invalid range. Use 24h, 7d, 30d, 90d, or custom.", status_code=400)
    grain = "hour" if range_key == "24h" else "day"
    return now - timedelta(hours=hours), now, grain, range_key


def _bucket_expr(column, grain: str):
    if settings.uses_sqlite:
        fmt = "%Y-%m-%d %H:00:00" if grain == "hour" else "%Y-%m-%d"
        return func.strftime(fmt, column)
    return func.date_trunc(grain, column)


def _parse_bucket(value: object, grain: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).replace(" ", "T")
    if grain == "day" and len(text) >= 10:
        return datetime.fromisoformat(text[:10]).replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iter_buckets(start: datetime, end: datetime, grain: str) -> list[datetime]:
    if grain == "hour":
        cursor = start.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
    else:
        cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(days=1)
    buckets: list[datetime] = []
    while cursor < end:
        buckets.append(cursor)
        cursor += step
    return buckets


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.orgs = OrganizationService(db)

    async def _project_ids(self, org_id: UUID, user_id: UUID, project_id: UUID | None) -> list[UUID]:
        await self.orgs.require_membership(org_id, user_id)
        if project_id:
            result = await self.db.execute(
                select(Project.id).where(
                    Project.id == project_id,
                    Project.organization_id == org_id,
                )
            )
            found = result.scalar_one_or_none()
            if not found:
                raise OrganizationError("Project not found", status_code=404)
            return [found]
        result = await self.db.execute(select(Project.id).where(Project.organization_id == org_id))
        return list(result.scalars().all())

    async def get_analytics(
        self,
        org_id: UUID,
        user_id: UUID,
        *,
        range_key: str = "7d",
        project_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> AnalyticsResponse:
        window_start, window_end, grain, label = resolve_window(range_key, start, end)
        project_ids = await self._project_ids(org_id, user_id, project_id)
        empty = AnalyticsResponse(
            range=label,
            start=window_start,
            end=window_end,
            grain=grain,
            summary=AnalyticsSummary(
                total_runs=0,
                success_count=0,
                error_count=0,
                success_rate=0,
                error_rate=0,
                avg_latency_ms=None,
                total_tokens=0,
                total_cost=Decimal("0"),
            ),
            timeseries=[
                TimeseriesPoint(timestamp=bucket) for bucket in _iter_buckets(window_start, window_end, grain)
            ],
            models=[],
        )
        if not project_ids:
            return empty

        filters = [
            Trace.project_id.in_(project_ids),
            Trace.start_time >= window_start,
            Trace.start_time < window_end,
        ]

        totals = await self.db.execute(
            select(
                func.count(Trace.id),
                func.coalesce(func.sum(case((Trace.status == "success", 1), else_=0)), 0),
                func.coalesce(func.sum(case((Trace.status == "error", 1), else_=0)), 0),
                func.avg(Trace.duration_ms),
                func.coalesce(func.sum(Trace.total_tokens), 0),
                func.coalesce(func.sum(Trace.total_cost), 0),
            ).where(*filters)
        )
        total_runs, success_count, error_count, avg_latency, total_tokens, total_cost = totals.one()
        total_runs = int(total_runs or 0)
        success_count = int(success_count or 0)
        error_count = int(error_count or 0)
        summary = AnalyticsSummary(
            total_runs=total_runs,
            success_count=success_count,
            error_count=error_count,
            success_rate=(success_count / total_runs) if total_runs else 0.0,
            error_rate=(error_count / total_runs) if total_runs else 0.0,
            avg_latency_ms=float(avg_latency) if avg_latency is not None else None,
            total_tokens=int(total_tokens or 0),
            total_cost=Decimal(str(total_cost or 0)),
        )

        bucket = _bucket_expr(Trace.start_time, grain)
        series_rows = await self.db.execute(
            select(
                bucket.label("bucket"),
                func.count(Trace.id),
                func.coalesce(func.sum(case((Trace.status == "success", 1), else_=0)), 0),
                func.coalesce(func.sum(case((Trace.status == "error", 1), else_=0)), 0),
                func.avg(Trace.duration_ms),
                func.coalesce(func.sum(Trace.total_tokens), 0),
                func.coalesce(func.sum(Trace.total_cost), 0),
            )
            .where(*filters)
            .group_by(bucket)
            .order_by(bucket)
        )
        by_key: dict[str, TimeseriesPoint] = {}
        for row in series_rows.all():
            ts = _parse_bucket(row[0], grain)
            key = ts.isoformat()
            by_key[key] = TimeseriesPoint(
                timestamp=ts,
                runs=int(row[1] or 0),
                successes=int(row[2] or 0),
                errors=int(row[3] or 0),
                avg_latency_ms=float(row[4]) if row[4] is not None else None,
                tokens=int(row[5] or 0),
                cost=Decimal(str(row[6] or 0)),
            )

        timeseries: list[TimeseriesPoint] = []
        for slot in _iter_buckets(window_start, window_end, grain):
            timeseries.append(by_key.get(slot.isoformat(), TimeseriesPoint(timestamp=slot)))

        model_rows = await self.db.execute(
            select(
                LLMCall.model,
                LLMCall.provider,
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.total_tokens), 0),
                func.coalesce(func.sum(LLMCall.estimated_cost), 0),
                func.avg(LLMCall.latency_ms),
            )
            .join(Trace, Trace.id == LLMCall.trace_id)
            .where(*filters)
            .group_by(LLMCall.model, LLMCall.provider)
            .order_by(func.count(LLMCall.id).desc())
        )
        models = [
            ModelUsage(
                model=row[0],
                provider=row[1],
                calls=int(row[2] or 0),
                tokens=int(row[3] or 0),
                cost=Decimal(str(row[4] or 0)),
                avg_latency_ms=float(row[5]) if row[5] is not None else None,
            )
            for row in model_rows.all()
        ]

        return AnalyticsResponse(
            range=label,
            start=window_start,
            end=window_end,
            grain=grain,
            summary=summary,
            timeseries=timeseries,
            models=models,
        )
