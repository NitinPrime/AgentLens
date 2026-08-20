"""create traces spans llm_calls tool_calls events

Revision ID: 003
Revises: 002
Create Date: 2026-08-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_agent_project_name"),
    )
    op.create_index(op.f("ix_agents_project_id"), "agents", ["project_id"], unique=False)

    op.create_table(
        "traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("agent_version", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_traces_project_id"), "traces", ["project_id"], unique=False)
    op.create_index(op.f("ix_traces_agent_id"), "traces", ["agent_id"], unique=False)
    op.create_index(op.f("ix_traces_agent_name"), "traces", ["agent_name"], unique=False)
    op.create_index(op.f("ix_traces_session_id"), "traces", ["session_id"], unique=False)
    op.create_index(op.f("ix_traces_status"), "traces", ["status"], unique=False)
    op.create_index("ix_traces_project_start", "traces", ["project_id", "start_time"], unique=False)
    op.create_index("ix_traces_project_agent", "traces", ["project_id", "agent_name"], unique=False)
    op.create_index("ix_traces_project_status", "traces", ["project_id", "status"], unique=False)

    op.create_table(
        "spans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("parent_span_id", sa.Uuid(), nullable=True),
        sa.Column("span_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_span_id"], ["spans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_spans_trace_id"), "spans", ["trace_id"], unique=False)
    op.create_index(op.f("ix_spans_project_id"), "spans", ["project_id"], unique=False)
    op.create_index(op.f("ix_spans_span_type"), "spans", ["span_type"], unique=False)
    op.create_index("ix_spans_trace_start", "spans", ["trace_id", "start_time"], unique=False)
    op.create_index("ix_spans_parent", "spans", ["parent_span_id"], unique=False)

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("span_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=True),
        sa.Column("completion", sa.JSON(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["span_id"], ["spans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_calls_trace_id"), "llm_calls", ["trace_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_span_id"), "llm_calls", ["span_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_project_id"), "llm_calls", ["project_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_provider"), "llm_calls", ["provider"], unique=False)
    op.create_index(op.f("ix_llm_calls_model"), "llm_calls", ["model"], unique=False)

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("span_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["span_id"], ["spans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tool_calls_trace_id"), "tool_calls", ["trace_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_span_id"), "tool_calls", ["span_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_project_id"), "tool_calls", ["project_id"], unique=False)
    op.create_index(op.f("ix_tool_calls_name"), "tool_calls", ["name"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("span_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("body", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["span_id"], ["spans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_trace_id"), "events", ["trace_id"], unique=False)
    op.create_index(op.f("ix_events_span_id"), "events", ["span_id"], unique=False)
    op.create_index(op.f("ix_events_project_id"), "events", ["project_id"], unique=False)
    op.create_index("ix_events_trace_time", "events", ["trace_id", "timestamp"], unique=False)


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("tool_calls")
    op.drop_table("llm_calls")
    op.drop_table("spans")
    op.drop_table("traces")
    op.drop_table("agents")
