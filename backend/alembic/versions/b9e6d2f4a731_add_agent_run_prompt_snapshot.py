"""add agent run prompt snapshot

Revision ID: b9e6d2f4a731
Revises: a8d1e6f3c540
Create Date: 2026-08-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b9e6d2f4a731"
down_revision: str | Sequence[str] | None = "a8d1e6f3c540"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_run") as batch_op:
        batch_op.add_column(sa.Column("prompt_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_run") as batch_op:
        batch_op.drop_column("prompt_snapshot")
