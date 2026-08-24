"""add evaluation scenario enabled state

Revision ID: a8d1e6f3c540
Revises: f3a8c1e4d927
Create Date: 2026-08-24 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a8d1e6f3c540"
down_revision: str | Sequence[str] | None = "f3a8c1e4d927"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("eval_scenario") as batch_op:
        batch_op.add_column(
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("eval_scenario") as batch_op:
        batch_op.drop_column("enabled")
