"""add tool_source to toolcall

Revision ID: 5e2f8a9c1d2b
Revises: 21be56fe4e09
Create Date: 2026-03-19 10:25:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5e2f8a9c1d2b"
down_revision: Union[str, Sequence[str], None] = "21be56fe4e09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("toolcall", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tool_source", sa.String(length=50), nullable=True))

    # Best-effort backfill from namespaced tool names like "zabbix.get_host_status"
    op.execute(
        """
        UPDATE toolcall
        SET tool_source = CASE
            WHEN instr(tool_name, '.') > 0 THEN substr(tool_name, 1, instr(tool_name, '.') - 1)
            ELSE NULL
        END
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("toolcall", schema=None) as batch_op:
        batch_op.drop_column("tool_source")

