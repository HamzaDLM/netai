"""add skills table

Revision ID: b5f3f4d8c2a1
Revises: 6e4f0ea79d33
Create Date: 2026-04-23 11:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5f3f4d8c2a1"
down_revision: Union[str, Sequence[str], None] = "6e4f0ea79d33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "skill",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_skill_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "ix_skill_user_created", ["user_id", "created_at"], unique=False
        )
        batch_op.create_index("ix_skill_user_name", ["user_id", "name"], unique=False)

    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.alter_column("enabled", server_default=None)
        batch_op.alter_column("archived", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.drop_index("ix_skill_user_name")
        batch_op.drop_index("ix_skill_user_created")
        batch_op.drop_index(batch_op.f("ix_skill_user_id"))
    op.drop_table("skill")
