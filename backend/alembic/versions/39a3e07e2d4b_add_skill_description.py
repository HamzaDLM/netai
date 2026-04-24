"""add skill description

Revision ID: 39a3e07e2d4b
Revises: c2f8c42aa9d1
Create Date: 2026-04-24 14:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "39a3e07e2d4b"
down_revision: Union[str, Sequence[str], None] = "c2f8c42aa9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "description",
                sa.String(length=240),
                nullable=False,
                server_default="",
            )
        )
        batch_op.alter_column("description", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.drop_column("description")
