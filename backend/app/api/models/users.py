import enum

from sqlalchemy import Enum, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"
    superuser = "superuser"


class User(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column()
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    custom_instructions: Mapped[str | None] = mapped_column(Text)
