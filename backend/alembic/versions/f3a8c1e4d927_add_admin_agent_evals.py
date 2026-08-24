"""add administrator agent evaluation tables

Revision ID: f3a8c1e4d927
Revises: e7a4c9d2f610
Create Date: 2026-08-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a8c1e4d927"
down_revision: str | Sequence[str] | None = "e7a4c9d2f610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_evaluator",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("deterministic", "llm_judge", name="evalevaluatorkind"),
            nullable=False,
        ),
        sa.Column(
            "rule",
            sa.Enum(
                "tool_trajectory",
                "completion_safety",
                "llm_judge",
                name="evalevaluatorrule",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("criteria", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("builtin", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eval_evaluator_archived_created",
        "eval_evaluator",
        ["archived", "created_at"],
    )
    op.create_table(
        "eval_scenario",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("owner_name", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("fixture", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("required_tools", sa.JSON(), nullable=False),
        sa.Column("forbidden_tools", sa.JSON(), nullable=False),
        sa.Column("expected_facts", sa.JSON(), nullable=False),
        sa.Column("evaluator_ids", sa.JSON(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eval_scenario_archived_created",
        "eval_scenario",
        ["archived", "created_at"],
    )
    op.create_table(
        "eval_run",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("scenario_id", sa.String(length=80), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "passed", "failed", name="evalrunstatus"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=120), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["scenario_id"], ["eval_scenario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eval_run_scenario_created",
        "eval_run",
        ["scenario_id", "created_at"],
    )
    op.create_index(
        "ix_eval_run_status_created",
        "eval_run",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_eval_run_status_created", table_name="eval_run")
    op.drop_index("ix_eval_run_scenario_created", table_name="eval_run")
    op.drop_table("eval_run")
    op.drop_index("ix_eval_scenario_archived_created", table_name="eval_scenario")
    op.drop_table("eval_scenario")
    op.drop_index("ix_eval_evaluator_archived_created", table_name="eval_evaluator")
    op.drop_table("eval_evaluator")
