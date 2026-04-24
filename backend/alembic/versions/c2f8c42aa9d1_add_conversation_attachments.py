"""add conversation attachments

Revision ID: c2f8c42aa9d1
Revises: b5f3f4d8c2a1
Create Date: 2026-04-24 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2f8c42aa9d1"
down_revision: Union[str, Sequence[str], None] = "b5f3f4d8c2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversation_attachment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("conversation_attachment", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_conversation_attachment_conversation_id"),
            ["conversation_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_conversation_attachment_conversation_active_created",
            ["conversation_id", "active", "created_at"],
            unique=False,
        )

    with op.batch_alter_table("conversation_attachment", schema=None) as batch_op:
        batch_op.alter_column("truncated", server_default=None)
        batch_op.alter_column("active", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conversation_attachment", schema=None) as batch_op:
        batch_op.drop_index("ix_conversation_attachment_conversation_active_created")
        batch_op.drop_index(batch_op.f("ix_conversation_attachment_conversation_id"))

    op.drop_table("conversation_attachment")
