"""add conversation summary table and archived flag

Revision ID: 7c9d2e4a1b3f
Revises: 5e2f8a9c1d2b
Create Date: 2026-03-21 11:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c9d2e4a1b3f"
down_revision: Union[str, Sequence[str], None] = "5e2f8a9c1d2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "archived",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("up_to_message_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("conversation_summaries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_conversation_summaries_conversation_id"),
            ["conversation_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_conversation_summaries_up_to_message_id"),
            ["up_to_message_id"],
            unique=False,
        )

    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.alter_column("archived", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conversation_summaries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_conversation_summaries_up_to_message_id"))
        batch_op.drop_index(batch_op.f("ix_conversation_summaries_conversation_id"))

    op.drop_table("conversation_summaries")

    with op.batch_alter_table("message", schema=None) as batch_op:
        batch_op.drop_column("archived")
