"""add conversation archived flag

Revision ID: 6e4f0ea79d33
Revises: a3ab223d0ba7
Create Date: 2026-04-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e4f0ea79d33"
down_revision: Union[str, Sequence[str], None] = "a3ab223d0ba7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("conversation", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "archived",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("conversation", schema=None) as batch_op:
        batch_op.alter_column("archived", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conversation", schema=None) as batch_op:
        batch_op.drop_column("archived")
