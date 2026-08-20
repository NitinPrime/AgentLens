from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.events import bus
from app.core.observability import prometheus_exposition, registry
from app.database import get_db
from app.dependencies import get_current_user
from app.models.evaluation import Dataset, DatasetItem, EvaluationRun, Evaluator
from app.models.project import Project
from app.models.trace import Event, LLMCall, Span, ToolCall, Trace
from app.models.user import User
from app.schemas.system import (
    RouteMetrics,
    StreamMetrics,
    SystemInfo,
    SystemMetrics,
    UsageResponse,
)
from app.services.organizations import OrganizationError, OrganizationService

router = APIRouter(tags=["system"])
settings = get_settings()


def _http(exc: OrganizationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/system/info", response_model=SystemInfo)
async def system_info(current_user: User = Depends(get_current_user)) -> SystemInfo:
    return SystemInfo(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database_backend="sqlite" if settings.uses_sqlite else "postgresql",
        token_store="memory" if settings.uses_memory_redis else "redis",
        judge_configured=bool(settings.openai_api_key),
        judge_model=settings.judge_model,
        uptime_seconds=round(registry.uptime_seconds, 3),
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_requests=settings.rate_limit_requests,
        rate_limit_window_seconds=settings.rate_limit_window_seconds,
    )


@router.get("/system/metrics", response_model=SystemMetrics)
async def system_metrics(current_user: User = Depends(get_current_user)) -> SystemMetrics:
    snapshot = registry.snapshot()
    return SystemMetrics(
        uptime_seconds=snapshot["uptime_seconds"],
        requests=snapshot["requests"],
        client_errors=snapshot["client_errors"],
        server_errors=snapshot["server_errors"],
        error_rate=snapshot["error_rate"],
        p50_ms=snapshot["p50_ms"],
        p95_ms=snapshot["p95_ms"],
        streams=StreamMetrics(**bus.stats()),
        routes=[RouteMetrics(**route) for route in snapshot["routes"]],
    )


@router.get("/system/metrics/prometheus", response_class=Response)
async def system_metrics_prometheus(current_user: User = Depends(get_current_user)) -> Response:
    body = prometheus_exposition(registry.snapshot())
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/organizations/{org_id}/usage", response_model=UsageResponse)
async def organization_usage(
    org_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    try:
        await OrganizationService(db).require_membership(org_id, current_user.id)
    except OrganizationError as exc:
        raise _http(exc) from exc

    project_ids = list(
        (
            await db.execute(select(Project.id).where(Project.organization_id == org_id))
        ).scalars().all()
    )

    if not project_ids:
        return UsageResponse(
            organization_id=str(org_id),
            projects=0,
            traces=0,
            spans=0,
            llm_calls=0,
            tool_calls=0,
            events=0,
            datasets=0,
            dataset_items=0,
            evaluators=0,
            evaluation_runs=0,
            traces_last_24h=0,
            tokens_last_24h=0,
            cost_last_24h=Decimal("0"),
        )

    async def count(model) -> int:
        result = await db.execute(
            select(func.count(model.id)).where(model.project_id.in_(project_ids))
        )
        return int(result.scalar_one())

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = await db.execute(
        select(
            func.count(Trace.id),
            func.coalesce(func.sum(Trace.total_tokens), 0),
            func.coalesce(func.sum(Trace.total_cost), 0),
        ).where(Trace.project_id.in_(project_ids), Trace.start_time >= since)
    )
    recent_count, recent_tokens, recent_cost = recent.one()

    bounds = await db.execute(
        select(func.min(Trace.start_time), func.max(Trace.start_time)).where(
            Trace.project_id.in_(project_ids)
        )
    )
    oldest, newest = bounds.one()

    return UsageResponse(
        organization_id=str(org_id),
        projects=len(project_ids),
        traces=await count(Trace),
        spans=await count(Span),
        llm_calls=await count(LLMCall),
        tool_calls=await count(ToolCall),
        events=await count(Event),
        datasets=await count(Dataset),
        dataset_items=await count(DatasetItem),
        evaluators=await count(Evaluator),
        evaluation_runs=await count(EvaluationRun),
        traces_last_24h=int(recent_count or 0),
        tokens_last_24h=int(recent_tokens or 0),
        cost_last_24h=Decimal(str(recent_cost or 0)),
        oldest_trace_at=oldest,
        newest_trace_at=newest,
    )
