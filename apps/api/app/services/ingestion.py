from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pricing import estimate_cost, infer_provider
from app.models.project import ApiKey
from app.models.trace import Agent, Event, LLMCall, Span, ToolCall, Trace
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
    TraceSummary,
)
from app.services.organizations import OrganizationError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_ms(start: datetime | None, end: datetime | None, explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    if start and end:
        return max(int((end - start).total_seconds() * 1000), 0)
    return None


class IngestionService:
    def __init__(self, db: AsyncSession, api_key: ApiKey):
        self.db = db
        self.project_id = api_key.project_id

    async def _get_trace(self, trace_id: UUID) -> Trace:
        result = await self.db.execute(
            select(Trace).where(Trace.id == trace_id, Trace.project_id == self.project_id)
        )
        trace = result.scalar_one_or_none()
        if not trace:
            raise OrganizationError("Trace not found", status_code=404)
        return trace

    async def _ensure_agent(self, name: str | None) -> Agent | None:
        if not name:
            return None
        result = await self.db.execute(
            select(Agent).where(Agent.project_id == self.project_id, Agent.name == name)
        )
        agent = result.scalar_one_or_none()
        if agent:
            return agent
        agent = Agent(project_id=self.project_id, name=name)
        self.db.add(agent)
        await self.db.flush()
        return agent

    async def upsert_trace(self, data: TraceIngest) -> Trace:
        trace_id = data.id or uuid4()
        result = await self.db.execute(
            select(Trace).where(Trace.id == trace_id, Trace.project_id == self.project_id)
        )
        trace = result.scalar_one_or_none()
        if trace is None:
            foreign = await self.db.execute(select(Trace.id).where(Trace.id == trace_id))
            if foreign.scalar_one_or_none():
                raise OrganizationError("Trace not found", status_code=404)
            agent = await self._ensure_agent(data.agent_name)
            trace = Trace(
                id=trace_id,
                project_id=self.project_id,
                agent_id=agent.id if agent else None,
                name=data.name,
                agent_name=data.agent_name,
                session_id=data.session_id,
                status=data.status,
                start_time=data.start_time or _now(),
                end_time=data.end_time,
                duration_ms=_duration_ms(data.start_time or _now(), data.end_time, data.duration_ms),
                input=data.input,
                output=data.output,
                extra_metadata=data.metadata,
                error_type=data.error_type,
                error_message=data.error_message,
                agent_version=data.agent_version,
                prompt_version=data.prompt_version,
                model_version=data.model_version,
            )
            self.db.add(trace)
        else:
            if data.agent_name:
                agent = await self._ensure_agent(data.agent_name)
                trace.agent_name = data.agent_name
                trace.agent_id = agent.id if agent else trace.agent_id
            trace.name = data.name
            if data.session_id is not None:
                trace.session_id = data.session_id
            trace.status = data.status
            if data.start_time is not None:
                trace.start_time = data.start_time
            if data.end_time is not None:
                trace.end_time = data.end_time
            if data.input is not None:
                trace.input = data.input
            if data.output is not None:
                trace.output = data.output
            if data.metadata is not None:
                trace.extra_metadata = data.metadata
            if data.error_type is not None:
                trace.error_type = data.error_type
            if data.error_message is not None:
                trace.error_message = data.error_message
            for field in ("agent_version", "prompt_version", "model_version"):
                value = getattr(data, field)
                if value is not None:
                    setattr(trace, field, value)
            trace.duration_ms = _duration_ms(trace.start_time, trace.end_time, data.duration_ms)

        await self.db.flush()
        await self.refresh_trace_aggregates(trace.id)
        await self.db.refresh(trace)
        return trace

    async def upsert_span(self, data: SpanIngest) -> Span:
        await self._get_trace(data.trace_id)
        span_id = data.id or uuid4()
        result = await self.db.execute(
            select(Span).where(Span.id == span_id, Span.project_id == self.project_id)
        )
        span = result.scalar_one_or_none()
        start = data.start_time or _now()
        if span is None:
            span = Span(
                id=span_id,
                trace_id=data.trace_id,
                project_id=self.project_id,
                parent_span_id=data.parent_span_id,
                span_type=data.type,
                name=data.name,
                status=data.status,
                start_time=start,
                end_time=data.end_time,
                duration_ms=_duration_ms(start, data.end_time, data.duration_ms),
                input=data.input,
                output=data.output,
                extra_metadata=data.metadata,
                error_type=data.error_type,
                error_message=data.error_message,
            )
            self.db.add(span)
        else:
            span.name = data.name
            span.span_type = data.type
            span.status = data.status
            if data.parent_span_id is not None:
                span.parent_span_id = data.parent_span_id
            if data.start_time is not None:
                span.start_time = data.start_time
            if data.end_time is not None:
                span.end_time = data.end_time
            if data.input is not None:
                span.input = data.input
            if data.output is not None:
                span.output = data.output
            if data.metadata is not None:
                span.extra_metadata = data.metadata
            if data.error_type is not None:
                span.error_type = data.error_type
            if data.error_message is not None:
                span.error_message = data.error_message
            span.duration_ms = _duration_ms(span.start_time, span.end_time, data.duration_ms)
        await self.db.flush()
        await self.refresh_trace_aggregates(data.trace_id)
        await self.db.refresh(span)
        return span

    async def upsert_llm_call(self, data: LLMCallIngest) -> LLMCall:
        await self._get_trace(data.trace_id)
        call_id = data.id or uuid4()
        total = data.total_tokens if data.total_tokens is not None else (data.input_tokens + data.output_tokens)
        cost = estimate_cost(data.model, data.input_tokens, data.output_tokens)
        provider = infer_provider(data.model, data.provider)
        result = await self.db.execute(
            select(LLMCall).where(LLMCall.id == call_id, LLMCall.project_id == self.project_id)
        )
        call = result.scalar_one_or_none()
        if call is None:
            call = LLMCall(
                id=call_id,
                trace_id=data.trace_id,
                span_id=data.span_id,
                project_id=self.project_id,
                provider=provider,
                model=data.model,
                messages=data.messages,
                completion=data.completion,
                input_tokens=data.input_tokens,
                output_tokens=data.output_tokens,
                total_tokens=total,
                latency_ms=data.latency_ms,
                estimated_cost=cost,
                temperature=data.temperature,
                extra_metadata=data.metadata,
            )
            self.db.add(call)
        else:
            call.provider = provider
            call.model = data.model
            if data.messages is not None:
                call.messages = data.messages
            if data.completion is not None:
                call.completion = data.completion
            call.input_tokens = data.input_tokens
            call.output_tokens = data.output_tokens
            call.total_tokens = total
            call.latency_ms = data.latency_ms
            call.estimated_cost = cost
            if data.temperature is not None:
                call.temperature = data.temperature
            if data.metadata is not None:
                call.extra_metadata = data.metadata
            if data.span_id is not None:
                call.span_id = data.span_id
        await self.db.flush()
        await self.refresh_trace_aggregates(data.trace_id)
        await self.db.refresh(call)
        return call

    async def upsert_tool_call(self, data: ToolCallIngest) -> ToolCall:
        await self._get_trace(data.trace_id)
        call_id = data.id or uuid4()
        result = await self.db.execute(
            select(ToolCall).where(ToolCall.id == call_id, ToolCall.project_id == self.project_id)
        )
        call = result.scalar_one_or_none()
        if call is None:
            call = ToolCall(
                id=call_id,
                trace_id=data.trace_id,
                span_id=data.span_id,
                project_id=self.project_id,
                name=data.name,
                arguments=data.arguments,
                output=data.output,
                status=data.status,
                duration_ms=data.duration_ms,
                error=data.error,
                retry_count=data.retry_count,
                extra_metadata=data.metadata,
            )
            self.db.add(call)
        else:
            call.name = data.name
            call.status = data.status
            if data.arguments is not None:
                call.arguments = data.arguments
            if data.output is not None:
                call.output = data.output
            if data.duration_ms is not None:
                call.duration_ms = data.duration_ms
            if data.error is not None:
                call.error = data.error
            call.retry_count = data.retry_count
            if data.metadata is not None:
                call.extra_metadata = data.metadata
            if data.span_id is not None:
                call.span_id = data.span_id
        await self.db.flush()
        await self.db.refresh(call)
        return call

    async def create_event(self, data: EventIngest) -> Event:
        await self._get_trace(data.trace_id)
        event = Event(
            id=data.id or uuid4(),
            trace_id=data.trace_id,
            span_id=data.span_id,
            project_id=self.project_id,
            name=data.name,
            body=data.body,
            timestamp=data.timestamp or _now(),
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def refresh_trace_aggregates(self, trace_id: UUID) -> None:
        token_row = await self.db.execute(
            select(
                func.coalesce(func.sum(LLMCall.input_tokens), 0),
                func.coalesce(func.sum(LLMCall.output_tokens), 0),
                func.coalesce(func.sum(LLMCall.total_tokens), 0),
                func.coalesce(func.sum(LLMCall.estimated_cost), 0),
            ).where(LLMCall.trace_id == trace_id, LLMCall.project_id == self.project_id)
        )
        input_tokens, output_tokens, total_tokens, total_cost = token_row.one()
        trace = await self._get_trace(trace_id)
        trace.input_tokens = int(input_tokens or 0)
        trace.output_tokens = int(output_tokens or 0)
        trace.total_tokens = int(total_tokens or 0)
        trace.total_cost = Decimal(str(total_cost or 0))
        if trace.start_time and trace.end_time:
            trace.duration_ms = _duration_ms(trace.start_time, trace.end_time, None)
        await self.db.flush()


class TraceQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_traces(
        self,
        project_id: UUID,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        agent_name: str | None = None,
    ) -> tuple[list[Trace], int]:
        filters = [Trace.project_id == project_id]
        if status:
            filters.append(Trace.status == status)
        if agent_name:
            filters.append(Trace.agent_name == agent_name)

        total = int(
            (await self.db.execute(select(func.count()).select_from(Trace).where(*filters))).scalar_one()
        )
        result = await self.db.execute(
            select(Trace)
            .where(*filters)
            .order_by(Trace.start_time.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_trace(self, project_id: UUID, trace_id: UUID) -> Trace:
        result = await self.db.execute(
            select(Trace)
            .options(
                selectinload(Trace.spans).selectinload(Span.llm_call),
                selectinload(Trace.spans).selectinload(Span.tool_call),
                selectinload(Trace.events),
            )
            .where(Trace.id == trace_id, Trace.project_id == project_id)
        )
        trace = result.scalar_one_or_none()
        if not trace:
            raise OrganizationError("Trace not found", status_code=404)
        return trace


def span_to_response(span: Span) -> SpanResponse:
    unloaded = inspect(span).unloaded
    llm_obj = None if "llm_call" in unloaded else span.llm_call
    tool_obj = None if "tool_call" in unloaded else span.tool_call
    llm = None
    if llm_obj:
        llm = LLMCallResponse(
            id=llm_obj.id,
            trace_id=llm_obj.trace_id,
            span_id=llm_obj.span_id,
            provider=llm_obj.provider,
            model=llm_obj.model,
            messages=llm_obj.messages,
            completion=llm_obj.completion,
            input_tokens=llm_obj.input_tokens,
            output_tokens=llm_obj.output_tokens,
            total_tokens=llm_obj.total_tokens,
            latency_ms=llm_obj.latency_ms,
            estimated_cost=llm_obj.estimated_cost,
            temperature=llm_obj.temperature,
            metadata=llm_obj.extra_metadata,
        )
    tool = None
    if tool_obj:
        tool = ToolCallResponse(
            id=tool_obj.id,
            trace_id=tool_obj.trace_id,
            span_id=tool_obj.span_id,
            name=tool_obj.name,
            arguments=tool_obj.arguments,
            output=tool_obj.output,
            status=tool_obj.status,
            duration_ms=tool_obj.duration_ms,
            error=tool_obj.error,
            retry_count=tool_obj.retry_count,
            metadata=tool_obj.extra_metadata,
        )
    return SpanResponse(
        id=span.id,
        trace_id=span.trace_id,
        parent_span_id=span.parent_span_id,
        type=span.span_type,
        name=span.name,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        duration_ms=span.duration_ms,
        input=span.input,
        output=span.output,
        metadata=span.extra_metadata,
        error_type=span.error_type,
        error_message=span.error_message,
        llm_call=llm,
        tool_call=tool,
    )


def trace_to_summary(trace: Trace) -> TraceSummary:
    return TraceSummary(
        id=trace.id,
        project_id=trace.project_id,
        name=trace.name,
        agent_name=trace.agent_name,
        session_id=trace.session_id,
        status=trace.status,
        start_time=trace.start_time,
        end_time=trace.end_time,
        duration_ms=trace.duration_ms,
        total_tokens=trace.total_tokens,
        total_cost=trace.total_cost,
        error_message=trace.error_message,
        agent_version=trace.agent_version,
        prompt_version=trace.prompt_version,
        model_version=trace.model_version,
    )


def trace_to_detail(trace: Trace) -> TraceDetail:
    summary = trace_to_summary(trace)
    spans = sorted(trace.spans, key=lambda item: item.start_time)
    events = sorted(trace.events, key=lambda item: item.timestamp)
    return TraceDetail(
        **summary.model_dump(),
        input=trace.input,
        output=trace.output,
        metadata=trace.extra_metadata,
        error_type=trace.error_type,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        spans=[span_to_response(span) for span in spans],
        events=[
            EventResponse(
                id=event.id,
                trace_id=event.trace_id,
                span_id=event.span_id,
                name=event.name,
                body=event.body,
                timestamp=event.timestamp,
            )
            for event in events
        ],
    )

