from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SpanType = Literal["LLM", "TOOL", "RETRIEVAL", "AGENT", "CHAIN", "CUSTOM"]
RunStatus = Literal["running", "success", "error", "cancelled"]


class TraceIngest(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    agent_name: str | None = Field(default=None, max_length=255)
    session_id: str | None = Field(default=None, max_length=255)
    status: RunStatus = "running"
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    input: Any | None = None
    output: Any | None = None
    metadata: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    agent_version: str | None = None
    prompt_version: str | None = None
    model_version: str | None = None


class SpanIngest(BaseModel):
    id: UUID | None = None
    trace_id: UUID
    parent_span_id: UUID | None = None
    type: SpanType = "CUSTOM"
    name: str = Field(min_length=1, max_length=255)
    status: RunStatus = "running"
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: int | None = None
    input: Any | None = None
    output: Any | None = None
    metadata: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None


class LLMCallIngest(BaseModel):
    id: UUID | None = None
    trace_id: UUID
    span_id: UUID | None = None
    provider: str | None = None
    model: str = Field(min_length=1, max_length=128)
    messages: Any | None = None
    completion: Any | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None
    latency_ms: int | None = None
    temperature: float | None = None
    metadata: dict[str, Any] | None = None


class ToolCallIngest(BaseModel):
    id: UUID | None = None
    trace_id: UUID
    span_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    arguments: Any | None = None
    output: Any | None = None
    status: RunStatus = "running"
    duration_ms: int | None = None
    error: str | None = None
    retry_count: int = 0
    metadata: dict[str, Any] | None = None


class EventIngest(BaseModel):
    id: UUID | None = None
    trace_id: UUID
    span_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    body: Any | None = None
    timestamp: datetime | None = None


class LLMCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trace_id: UUID
    span_id: UUID | None
    provider: str
    model: str
    messages: Any | None = None
    completion: Any | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int | None
    estimated_cost: Decimal
    temperature: float | None
    metadata: Any | None = None


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trace_id: UUID
    span_id: UUID | None
    name: str
    arguments: Any | None = None
    output: Any | None = None
    status: str
    duration_ms: int | None
    error: str | None = None
    retry_count: int
    metadata: Any | None = None


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trace_id: UUID
    span_id: UUID | None
    name: str
    body: Any | None = None
    timestamp: datetime


class SpanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trace_id: UUID
    parent_span_id: UUID | None
    type: str
    name: str
    status: str
    start_time: datetime
    end_time: datetime | None
    duration_ms: int | None
    input: Any | None = None
    output: Any | None = None
    metadata: Any | None = None
    error_type: str | None = None
    error_message: str | None = None
    llm_call: LLMCallResponse | None = None
    tool_call: ToolCallResponse | None = None


class TraceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    agent_name: str | None
    session_id: str | None
    status: str
    start_time: datetime
    end_time: datetime | None
    duration_ms: int | None
    total_tokens: int
    total_cost: Decimal
    error_message: str | None = None
    agent_version: str | None = None
    prompt_version: str | None = None
    model_version: str | None = None


class TraceDetail(TraceSummary):
    input: Any | None = None
    output: Any | None = None
    metadata: Any | None = None
    error_type: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    spans: list[SpanResponse] = []
    events: list[EventResponse] = []


class TraceListResponse(BaseModel):
    items: list[TraceSummary]
    total: int
