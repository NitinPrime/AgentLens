from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import bus
from app.database import get_db
from app.dependencies import get_api_key, get_current_user
from app.models.project import ApiKey
from app.models.trace import Trace
from app.models.user import User
from app.schemas.traces import (
    EventIngest,
    EventResponse,
    LLMCallIngest,
    LLMCallResponse,
    SpanIngest,
    SpanResponse,
    ToolCallIngest,
    ToolCallResponse,
    TraceDetail,
    TraceIngest,
    TraceListResponse,
    TraceSummary,
)
from app.services.ingestion import (
    IngestionService,
    TraceQueryService,
    span_to_response,
    trace_to_detail,
    trace_to_summary,
)
from app.services.organizations import OrganizationError
from app.services.projects import ProjectService

ingest_router = APIRouter(tags=["ingestion"])
traces_router = APIRouter(tags=["traces"])


def _http(exc: OrganizationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _broadcast(project_id: UUID, event_type: str, payload: BaseModel) -> None:
    """Push an ingest event to any live dashboards watching this project.

    Published after a successful write but before the request-scoped commit, so
    a live tile can very occasionally show a row from a transaction that later
    rolls back. The trace explorer always reads from the database, so the
    persisted view stays authoritative.
    """

    bus.publish(project_id, event_type, payload.model_dump(mode="json"))


@ingest_router.post("/traces", response_model=TraceSummary)
async def ingest_trace(
    data: TraceIngest,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> TraceSummary:
    try:
        trace = await IngestionService(db, api_key).upsert_trace(data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    summary = trace_to_summary(trace)
    _broadcast(api_key.project_id, "trace", summary)
    return summary


@ingest_router.post("/spans", response_model=SpanResponse)
async def ingest_span(
    data: SpanIngest,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> SpanResponse:
    try:
        span = await IngestionService(db, api_key).upsert_span(data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    response = span_to_response(span)
    _broadcast(api_key.project_id, "span", response)
    return response


@ingest_router.post("/llm-calls", response_model=LLMCallResponse)
async def ingest_llm_call(
    data: LLMCallIngest,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> LLMCallResponse:
    try:
        call = await IngestionService(db, api_key).upsert_llm_call(data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    response = LLMCallResponse(
        id=call.id,
        trace_id=call.trace_id,
        span_id=call.span_id,
        provider=call.provider,
        model=call.model,
        messages=call.messages,
        completion=call.completion,
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        total_tokens=call.total_tokens,
        latency_ms=call.latency_ms,
        estimated_cost=call.estimated_cost,
        temperature=call.temperature,
        metadata=call.extra_metadata,
    )
    _broadcast(api_key.project_id, "llm_call", response)
    return response


@ingest_router.post("/tool-calls", response_model=ToolCallResponse)
async def ingest_tool_call(
    data: ToolCallIngest,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> ToolCallResponse:
    try:
        call = await IngestionService(db, api_key).upsert_tool_call(data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    response = ToolCallResponse(
        id=call.id,
        trace_id=call.trace_id,
        span_id=call.span_id,
        name=call.name,
        arguments=call.arguments,
        output=call.output,
        status=call.status,
        duration_ms=call.duration_ms,
        error=call.error,
        retry_count=call.retry_count,
        metadata=call.extra_metadata,
    )
    _broadcast(api_key.project_id, "tool_call", response)
    return response


@ingest_router.post("/events", response_model=EventResponse)
async def ingest_event(
    data: EventIngest,
    api_key: ApiKey = Depends(get_api_key),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    try:
        event = await IngestionService(db, api_key).create_event(data)
    except OrganizationError as exc:
        raise _http(exc) from exc
    response = EventResponse.model_validate(event)
    _broadcast(api_key.project_id, "event", response)
    return response


@traces_router.get("/projects/{project_id}/traces", response_model=TraceListResponse)
async def list_project_traces(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    agent_name: str | None = None,
) -> TraceListResponse:
    try:
        await ProjectService(db).get_project_for_user(project_id, current_user.id)
        items, total = await TraceQueryService(db).list_traces(
            project_id, limit=limit, offset=offset, status=status, agent_name=agent_name
        )
    except OrganizationError as exc:
        raise _http(exc) from exc
    return TraceListResponse(items=[trace_to_summary(item) for item in items], total=total)


@traces_router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace(
    trace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TraceDetail:
    result = await db.execute(select(Trace.project_id).where(Trace.id == trace_id))
    project_id = result.scalar_one_or_none()
    if not project_id:
        raise HTTPException(status_code=404, detail="Trace not found")
    try:
        await ProjectService(db).get_project_for_user(project_id, current_user.id)
        trace = await TraceQueryService(db).get_trace(project_id, trace_id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return trace_to_detail(trace)


@traces_router.get("/projects/{project_id}/traces/{trace_id}", response_model=TraceDetail)
async def get_project_trace(
    project_id: UUID,
    trace_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TraceDetail:
    try:
        await ProjectService(db).get_project_for_user(project_id, current_user.id)
        trace = await TraceQueryService(db).get_trace(project_id, trace_id)
    except OrganizationError as exc:
        raise _http(exc) from exc
    return trace_to_detail(trace)
