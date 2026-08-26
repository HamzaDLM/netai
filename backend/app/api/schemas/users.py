from datetime import datetime

from pydantic import BaseModel

from app.api.models.users import UserRole


class AdminUserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime | None
    conversation_count: int
    user_message_count: int


class AdminUserStats(BaseModel):
    registered_users: int
    new_users_last_7_days: int


class AdminUsersBootstrapResponse(BaseModel):
    users: list[AdminUserResponse]
    stats: AdminUserStats
