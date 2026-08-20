import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_dataset_project_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[list["DatasetItem"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DatasetItem(Base):
    __tablename__ = "dataset_items"
    __table_args__ = (Index("ix_dataset_items_dataset_created", "dataset_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    expected_output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dataset: Mapped[Dataset] = relationship(back_populates="items")


class Evaluator(Base):
    __tablename__ = "evaluators"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_evaluator_project_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    evaluator_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (Index("ix_evaluation_runs_project_created", "project_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target: Mapped[str] = mapped_column(String(32), nullable=False, default="dataset")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    agent_version: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        Index("ix_evaluation_results_run_evaluator", "run_id", "evaluator_id"),
        Index("ix_evaluation_results_run_item", "run_id", "dataset_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evaluators.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evaluator_name: Mapped[str] = mapped_column(String(255), nullable=False)
    evaluator_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("dataset_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("traces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject_key: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    expected_output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[EvaluationRun] = relationship(back_populates="results")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "name", "version", name="uq_prompt_project_name_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
