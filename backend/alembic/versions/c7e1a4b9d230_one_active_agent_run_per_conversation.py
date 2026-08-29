"""enforce one active root agent run per conversation

Revision ID: c7e1a4b9d230
Revises: b9e6d2f4a731
Create Date: 2026-08-26 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7e1a4b9d230"
down_revision: str | Sequence[str] | None = "b9e6d2f4a731"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ux_agent_run_one_active_root_per_conversation",
        "agent_run",
        ["conversation_id"],
        unique=True,
        sqlite_where=sa.text("status = 'running' AND parent_run_id IS NULL"),
        postgresql_where=sa.text("status = 'running' AND parent_run_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_agent_run_one_active_root_per_conversation",
        table_name="agent_run",
    )
