from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import AsyncSessionDep, CheckUserSSODep
from app.api.models.chat import Conversation, Message, MessageRole
from app.api.models.users import User as UserModel
from app.api.models.users import UserRole
from app.api.schemas.users import (
    AdminUserResponse,
    AdminUsersBootstrapResponse,
    AdminUserStats,
)

router = APIRouter(prefix="/users", tags=["users"])


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@router.get("/admin/bootstrap", response_model=AdminUsersBootstrapResponse)
async def get_admin_users_bootstrap(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> AdminUsersBootstrapResponse:
    if user.role not in {UserRole.admin, UserRole.superuser}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    active_conversations = Conversation.archived.is_(False)
    active_messages = Message.archived.is_(False)
    last_activity_at = (
        select(func.max(Message.created_at))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == UserModel.id,
            active_conversations,
            active_messages,
            Message.role == MessageRole.user,
        )
        .correlate(UserModel)
        .scalar_subquery()
    )
    conversation_count = (
        select(func.count(Conversation.id))
        .where(
            Conversation.user_id == UserModel.id,
            active_conversations,
        )
        .correlate(UserModel)
        .scalar_subquery()
    )
    user_message_count = (
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == UserModel.id,
            active_conversations,
            active_messages,
            Message.role == MessageRole.user,
        )
        .correlate(UserModel)
        .scalar_subquery()
    )
    result = await db.execute(
        select(
            UserModel,
            last_activity_at.label("last_activity_at"),
            conversation_count.label("conversation_count"),
            user_message_count.label("user_message_count"),
        ).order_by(UserModel.username.asc(), UserModel.id.asc())
    )

    users = [
        AdminUserResponse(
            id=row.User.id,
            username=row.User.username,
            role=row.User.role,
            created_at=_as_utc(row.User.created_at),
            updated_at=_as_utc(row.User.updated_at),
            last_activity_at=(
                _as_utc(row.last_activity_at)
                if row.last_activity_at is not None
                else None
            ),
            conversation_count=int(row.conversation_count or 0),
            user_message_count=int(row.user_message_count or 0),
        )
        for row in result.all()
    ]
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    return AdminUsersBootstrapResponse(
        users=users,
        stats=AdminUserStats(
            registered_users=len(users),
            new_users_last_7_days=sum(
                _as_utc(item.created_at) >= seven_days_ago for item in users
            ),
        ),
    )
