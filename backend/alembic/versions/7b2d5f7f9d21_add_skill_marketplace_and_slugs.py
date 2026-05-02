"""add skill marketplace and slugs

Revision ID: 7b2d5f7f9d21
Revises: 39a3e07e2d4b
Create Date: 2026-04-30 11:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b2d5f7f9d21"
down_revision: Union[str, Sequence[str], None] = "39a3e07e2d4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


skill_marketplace_status = sa.Enum(
    "pending",
    "approved",
    "rejected",
    name="skillmarketplacestatus",
)


def upgrade() -> None:
    """Upgrade schema."""
    skill_marketplace_status.create(op.get_bind(), checkfirst=True)

    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column("installed_from_listing_id", sa.Integer(), nullable=True)
        )

    op.execute(
        """
        UPDATE skill
        SET slug = lower(trim(replace(replace(replace(name, ' ', '-'), '/', '-'), '_', '-')))
        """
    )

    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.alter_column("slug", nullable=False)
        batch_op.create_index("ix_skill_user_slug", ["user_id", "slug"], unique=False)

    op.create_table(
        "skill_marketplace_listing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("owner_skill_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column(
            "description", sa.String(length=240), nullable=False, server_default=""
        ),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column(
            "status", skill_marketplace_status, nullable=False, server_default="pending"
        ),
        sa.Column("review_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_skill_id"], ["skill.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_skill_marketplace_listing_status",
        "skill_marketplace_listing",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_skill_marketplace_listing_owner_skill",
        "skill_marketplace_listing",
        ["owner_skill_id"],
        unique=False,
    )
    op.create_index(
        "ix_skill_marketplace_listing_slug",
        "skill_marketplace_listing",
        ["slug"],
        unique=False,
    )

    with op.batch_alter_table("skill_marketplace_listing", schema=None) as batch_op:
        batch_op.alter_column("description", server_default=None)
        batch_op.alter_column("status", server_default=None)
        batch_op.alter_column("review_notes", server_default=None)
        batch_op.alter_column("archived", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_skill_marketplace_listing_slug",
        table_name="skill_marketplace_listing",
    )
    op.drop_index(
        "ix_skill_marketplace_listing_owner_skill",
        table_name="skill_marketplace_listing",
    )
    op.drop_index(
        "ix_skill_marketplace_listing_status",
        table_name="skill_marketplace_listing",
    )
    op.drop_table("skill_marketplace_listing")

    with op.batch_alter_table("skill", schema=None) as batch_op:
        batch_op.drop_index("ix_skill_user_slug")
        batch_op.drop_column("installed_from_listing_id")
        batch_op.drop_column("slug")

    skill_marketplace_status.drop(op.get_bind(), checkfirst=True)
