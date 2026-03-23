from fastapi import Request
from dataclasses import dataclass
from app.api.models.users import UserRole


@dataclass
class User:
    id: int
    username: str
    role: UserRole


# TODO: placeholder to implement after
async def get_current_user(_: Request) -> User:
    return User(
        id=0,
        username="testuser",
        role=UserRole.admin,
    )
