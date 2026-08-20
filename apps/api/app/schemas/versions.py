from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evaluations import MetricDelta

VersionDimension = Literal["agent_version", "prompt_version", "model_version", "agent_name"]


class VersionStats(BaseModel):
    version: str
    runs: int
    success_count: int
    error_count: int
    success_rate: float
    error_rate: float
    avg_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    total_tokens: int
    avg_tokens: float | None = None
    total_cost: Decimal
    avg_cost: Decimal
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class VersionListResponse(BaseModel):
    dimension: str
    range: str
    start: datetime
    end: datetime
    versions: list[VersionStats] = Field(default_factory=list)


class VersionComparison(BaseModel):
    dimension: str
    range: str
    start: datetime
    end: datetime
    baseline: VersionStats
    candidate: VersionStats
    metrics: list[MetricDelta] = Field(default_factory=list)
    verdict: Literal["pass", "warn", "fail"]
    summary: str
