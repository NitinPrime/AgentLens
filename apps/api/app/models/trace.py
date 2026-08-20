import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_agent_project_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    traces: Mapped[list["Trace"]] = relationship(back_populates="agent")


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (
        Index("ix_traces_project_start", "project_id", "start_time"),
        Index("ix_traces_project_agent", "project_id", "agent_name"),
        Index("ix_traces_project_status", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    agent_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent: Mapped[Agent | None] = relationship(back_populates="traces")
    spans: Mapped[list["Span"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan"
    )
    llm_calls: Mapped[list["LLMCall"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan"
    )


class Span(Base):
    __tablename__ = "spans"
    __table_args__ = (
        Index("ix_spans_trace_start", "trace_id", "start_time"),
        Index("ix_spans_parent", "parent_span_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_span_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("spans.id", ondelete="SET NULL"), nullable=True
    )
    span_type: Mapped[str] = mapped_column(String(32), nullable=False, default="CUSTOM", index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    trace: Mapped[Trace] = relationship(back_populates="spans")
    llm_call: Mapped["LLMCall | None"] = relationship(back_populates="span", uselist=False)
    tool_call: Mapped["ToolCall | None"] = relationship(back_populates="span", uselist=False)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    span_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("spans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown", index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    messages: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    completion: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trace: Mapped[Trace] = relationship(back_populates="llm_calls")
    span: Mapped[Span | None] = relationship(back_populates="llm_call")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    span_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("spans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    arguments: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    output: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_metadata: Mapped[Any | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trace: Mapped[Trace] = relationship(back_populates="tool_calls")
    span: Mapped[Span | None] = relationship(back_populates="tool_call")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_trace_time", "trace_id", "timestamp"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    span_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("spans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trace: Mapped[Trace] = relationship(back_populates="events")
