"""add user custom instructions

Revision ID: d4b2a7f3c981
Revises: 7b2d5f7f9d21
Create Date: 2026-05-01 11:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4b2a7f3c981"
down_revision: Union[str, Sequence[str], None] = "7b2d5f7f9d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("custom_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("custom_instructions")
