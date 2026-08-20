from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    total_runs: int
    success_count: int
    error_count: int
    success_rate: float
    error_rate: float
    avg_latency_ms: float | None = None
    total_tokens: int
    total_cost: Decimal


class TimeseriesPoint(BaseModel):
    timestamp: datetime
    runs: int = 0
    successes: int = 0
    errors: int = 0
    avg_latency_ms: float | None = None
    tokens: int = 0
    cost: Decimal = Decimal("0")


class ModelUsage(BaseModel):
    model: str
    provider: str
    calls: int
    tokens: int
    cost: Decimal
    avg_latency_ms: float | None = None


class AnalyticsResponse(BaseModel):
    range: str
    start: datetime
    end: datetime
    grain: str
    summary: AnalyticsSummary
    timeseries: list[TimeseriesPoint] = Field(default_factory=list)
    models: list[ModelUsage] = Field(default_factory=list)
