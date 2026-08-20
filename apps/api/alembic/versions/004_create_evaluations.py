"""create datasets evaluators evaluation runs results prompt versions

Revision ID: 004
Revises: 003
Create Date: 2026-08-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_dataset_project_name"),
    )
    op.create_index(op.f("ix_datasets_project_id"), "datasets", ["project_id"], unique=False)

    op.create_table(
        "dataset_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("expected_output", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataset_items_dataset_id"), "dataset_items", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_dataset_items_project_id"), "dataset_items", ["project_id"], unique=False)
    op.create_index(
        "ix_dataset_items_dataset_created", "dataset_items", ["dataset_id", "created_at"], unique=False
    )

    op.create_table(
        "evaluators",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("evaluator_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_evaluator_project_name"),
    )
    op.create_index(op.f("ix_evaluators_project_id"), "evaluators", ["project_id"], unique=False)
    op.create_index(op.f("ix_evaluators_evaluator_type"), "evaluators", ["evaluator_type"], unique=False)

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("target", sa.String(length=32), nullable=False, server_default="dataset"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("agent_version", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_score", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_runs_project_id"), "evaluation_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_evaluation_runs_dataset_id"), "evaluation_runs", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_evaluation_runs_status"), "evaluation_runs", ["status"], unique=False)
    op.create_index(
        op.f("ix_evaluation_runs_agent_version"), "evaluation_runs", ["agent_version"], unique=False
    )
    op.create_index(
        "ix_evaluation_runs_project_created", "evaluation_runs", ["project_id", "created_at"], unique=False
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_id", sa.Uuid(), nullable=True),
        sa.Column("evaluator_name", sa.String(length=255), nullable=False),
        sa.Column("evaluator_type", sa.String(length=64), nullable=False),
        sa.Column("dataset_item_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.Uuid(), nullable=True),
        sa.Column("subject_key", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("expected_output", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluator_id"], ["evaluators.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dataset_item_id"], ["dataset_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evaluation_results_run_id"), "evaluation_results", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_evaluation_results_project_id"), "evaluation_results", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_results_evaluator_id"), "evaluation_results", ["evaluator_id"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_results_dataset_item_id"),
        "evaluation_results",
        ["dataset_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_results_trace_id"), "evaluation_results", ["trace_id"], unique=False
    )
    op.create_index(
        "ix_evaluation_results_run_evaluator", "evaluation_results", ["run_id", "evaluator_id"], unique=False
    )
    op.create_index(
        "ix_evaluation_results_run_item", "evaluation_results", ["run_id", "dataset_item_id"], unique=False
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", "version", name="uq_prompt_project_name_version"),
    )
    op.create_index(op.f("ix_prompt_versions_project_id"), "prompt_versions", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_table("prompt_versions")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluators")
    op.drop_table("dataset_items")
    op.drop_table("datasets")
