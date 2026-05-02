import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class SkillMarketplaceStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Skill(Base):
    __table_args__ = (
        Index("ix_skill_user_created", "user_id", "created_at"),
        Index("ix_skill_user_name", "user_id", "name"),
        Index("ix_skill_user_slug", "user_id", "slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    installed_from_listing_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )


class SkillMarketplaceListing(Base):
    __table_args__ = (
        Index("ix_skill_marketplace_listing_status", "status", "created_at"),
        Index("ix_skill_marketplace_listing_owner_skill", "owner_skill_id"),
        Index("ix_skill_marketplace_listing_slug", "slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id"),
        index=True,
        nullable=False,
    )
    owner_skill_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("skill.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SkillMarketplaceStatus] = mapped_column(
        Enum(SkillMarketplaceStatus),
        nullable=False,
        default=SkillMarketplaceStatus.pending,
    )
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user.id"),
        nullable=True,
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
