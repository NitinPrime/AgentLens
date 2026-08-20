from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EvaluatorType = Literal[
    "exact_match",
    "contains",
    "not_contains",
    "regex",
    "json_field_match",
    "numeric_tolerance",
    "similarity",
    "valid_json",
    "no_error",
    "latency_under",
    "cost_under",
    "llm_judge",
]

RunTarget = Literal["dataset", "traces"]


class EvaluatorTypeInfo(BaseModel):
    type: str
    title: str
    description: str
    requires_expected_output: bool
    default_threshold: float
    default_config: dict[str, Any]


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)


class DatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    item_count: int = 0
    created_at: datetime
    updated_at: datetime


class DatasetItemCreate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    input: Any | None = None
    expected_output: Any | None = None
    metadata: dict[str, Any] | None = None


class DatasetItemBulkCreate(BaseModel):
    items: list[DatasetItemCreate] = Field(min_length=1, max_length=1000)
    replace: bool = False


class DatasetItemResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    name: str | None = None
    input: Any | None = None
    expected_output: Any | None = None
    metadata: Any | None = None
    created_at: datetime


class EvaluatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    evaluator_type: EvaluatorType
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] | None = None
    threshold: float | None = Field(default=None, ge=0, le=1)
    is_active: bool = True


class EvaluatorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    config: dict[str, Any] | None = None
    threshold: float | None = Field(default=None, ge=0, le=1)
    is_active: bool | None = None


class EvaluatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    evaluator_type: str
    description: str | None = None
    config: Any | None = None
    threshold: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TraceSelector(BaseModel):
    agent_name: str | None = None
    status: str | None = None
    agent_version: str | None = None
    prompt_version: str | None = None
    model_version: str | None = None
    session_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=100, ge=1, le=2000)


class SubmittedOutput(BaseModel):
    dataset_item_id: UUID | None = None
    item_name: str | None = None
    output: Any | None = None
    trace_id: UUID | None = None
    status: str = "success"
    duration_ms: int | None = None
    cost: Decimal | None = None
    total_tokens: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] | None = None


class EvaluationRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target: RunTarget = "dataset"
    dataset_id: UUID | None = None
    dataset_name: str | None = Field(default=None, max_length=255)
    evaluator_ids: list[UUID] | None = None
    evaluator_names: list[str] | None = None
    outputs: list[SubmittedOutput] | None = None
    selector: TraceSelector | None = None
    agent_version: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)
    model_version: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] | None = None


class EvaluatorScore(BaseModel):
    evaluator_id: UUID | None = None
    evaluator_name: str
    evaluator_type: str
    count: int
    passed: int
    failed: int
    pass_rate: float
    avg_score: float


class FailureCategory(BaseModel):
    label: str
    count: int


class EvaluationResultResponse(BaseModel):
    id: UUID
    run_id: UUID
    evaluator_id: UUID | None = None
    evaluator_name: str
    evaluator_type: str
    dataset_item_id: UUID | None = None
    trace_id: UUID | None = None
    subject_key: str
    score: float
    passed: bool
    label: str | None = None
    reasoning: str | None = None
    output: Any | None = None
    expected_output: Any | None = None
    latency_ms: int | None = None
    cost: Decimal
    created_at: datetime


class EvaluationRunResponse(BaseModel):
    id: UUID
    project_id: UUID
    dataset_id: UUID | None = None
    dataset_name: str | None = None
    name: str
    target: str
    status: str
    agent_version: str | None = None
    prompt_version: str | None = None
    model_version: str | None = None
    total_items: int
    passed_count: int
    failed_count: int
    pass_rate: float
    avg_score: float | None = None
    total_cost: Decimal
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class EvaluationRunDetail(EvaluationRunResponse):
    evaluator_scores: list[EvaluatorScore] = Field(default_factory=list)
    failure_categories: list[FailureCategory] = Field(default_factory=list)
    skipped_evaluators: list[str] = Field(default_factory=list)
    results: list[EvaluationResultResponse] = Field(default_factory=list)


class MetricDelta(BaseModel):
    metric: str
    baseline: float | None = None
    candidate: float | None = None
    delta: float | None = None
    pct_change: float | None = None
    higher_is_better: bool
    regression: bool


class EvaluatorDelta(BaseModel):
    evaluator_name: str
    evaluator_type: str
    baseline_pass_rate: float | None = None
    candidate_pass_rate: float | None = None
    baseline_avg_score: float | None = None
    candidate_avg_score: float | None = None
    pass_rate_delta: float | None = None
    regression: bool


class SubjectChange(BaseModel):
    subject_key: str
    subject_name: str | None = None
    evaluator_name: str
    baseline_score: float
    candidate_score: float
    label: str | None = None
    reasoning: str | None = None
    dataset_item_id: UUID | None = None
    trace_id: UUID | None = None


class RunComparison(BaseModel):
    baseline: EvaluationRunResponse
    candidate: EvaluationRunResponse
    metrics: list[MetricDelta] = Field(default_factory=list)
    evaluator_deltas: list[EvaluatorDelta] = Field(default_factory=list)
    newly_failing: list[SubjectChange] = Field(default_factory=list)
    newly_passing: list[SubjectChange] = Field(default_factory=list)
    verdict: Literal["pass", "warn", "fail"]
    summary: str


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunResponse]
    total: int


class EvaluationResultListResponse(BaseModel):
    items: list[EvaluationResultResponse]
    total: int


class PromptVersionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=128)
    template: str = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=4000)
    is_active: bool = False
    metadata: dict[str, Any] | None = None


class PromptVersionResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    version: str
    template: str
    notes: str | None = None
    is_active: bool
    metadata: Any | None = None
    created_at: datetime
