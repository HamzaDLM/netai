"""add durable agent events and merge migration heads

Revision ID: e7a4c9d2f610
Revises: 9f1c2d4a6b77, d4b2a7f3c981
Create Date: 2026-08-17 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a4c9d2f610"
down_revision: Union[str, Sequence[str], None] = (
    "9f1c2d4a6b77",
    "d4b2a7f3c981",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=True),
        sa.Column("actor_name", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_event_run_id"),
        "agent_event",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_event_correlation_id"),
        "agent_event",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        "ux_agent_event_run_sequence",
        "agent_event",
        ["run_id", "event_sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_agent_event_run_sequence", table_name="agent_event")
    op.drop_index(op.f("ix_agent_event_correlation_id"), table_name="agent_event")
    op.drop_index(op.f("ix_agent_event_run_id"), table_name="agent_event")
    op.drop_table("agent_event")
