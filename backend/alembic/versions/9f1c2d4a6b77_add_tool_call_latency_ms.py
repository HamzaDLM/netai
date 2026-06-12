"""add tool call latency ms

Revision ID: 9f1c2d4a6b77
Revises: c2f8c42aa9d1
Create Date: 2026-05-15 18:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f1c2d4a6b77"
down_revision: Union[str, Sequence[str], None] = "c2f8c42aa9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("tool_call", schema=None) as batch_op:
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tool_call", schema=None) as batch_op:
        batch_op.drop_column("latency_ms")
