from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SystemInfo(BaseModel):
    name: str
    version: str
    environment: str
    database_backend: str
    token_store: str
    judge_configured: bool
    judge_model: str
    uptime_seconds: float
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int


class RouteMetrics(BaseModel):
    route: str
    requests: int
    client_errors: int
    server_errors: int
    avg_ms: float | None = None
    p50_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float


class StreamMetrics(BaseModel):
    subscribers: int
    projects_watched: int
    events_published: int
    events_dropped: int


class SystemMetrics(BaseModel):
    uptime_seconds: float
    requests: int
    client_errors: int
    server_errors: int
    error_rate: float
    p50_ms: float | None = None
    p95_ms: float | None = None
    streams: StreamMetrics
    routes: list[RouteMetrics] = Field(default_factory=list)


class UsageResponse(BaseModel):
    organization_id: str
    projects: int
    traces: int
    spans: int
    llm_calls: int
    tool_calls: int
    events: int
    datasets: int
    dataset_items: int
    evaluators: int
    evaluation_runs: int
    traces_last_24h: int
    tokens_last_24h: int
    cost_last_24h: Decimal
    oldest_trace_at: datetime | None = None
    newest_trace_at: datetime | None = None
