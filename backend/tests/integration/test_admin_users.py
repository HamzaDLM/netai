from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.chat import Conversation, Message, MessageRole
from app.api.models.users import User, UserRole
from app.core.security import User as SecurityUser
from app.core.security import get_current_user
from app.main import app


@pytest.mark.anyio
async def test_admin_users_bootstrap_reports_persisted_users_and_activity(
    async_client: AsyncClient,
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)
    earlier_activity = now - timedelta(hours=2)
    latest_activity = now - timedelta(minutes=20)

    async with test_db_session_factory() as db:
        alice = User(
            id=10,
            username="alice",
            role=UserRole.admin,
            created_at=now,
        )
        bob = User(
            id=11,
            username="bob",
            role=UserRole.user,
            created_at=old,
        )
        carol = User(
            id=12,
            username="carol",
            role=UserRole.superuser,
            created_at=now,
        )
        db.add_all([alice, bob, carol])
        await db.flush()

        active_conversation = Conversation(
            title="Active",
            user_id=alice.id,
            created_at=now,
        )
        archived_conversation = Conversation(
            title="Archived",
            user_id=alice.id,
            archived=True,
            created_at=now,
        )
        db.add_all([active_conversation, archived_conversation])
        await db.flush()

        db.add_all(
            [
                Message(
                    conversation_id=active_conversation.id,
                    role=MessageRole.user,
                    content="First question",
                    created_at=earlier_activity,
                ),
                Message(
                    conversation_id=active_conversation.id,
                    role=MessageRole.user,
                    content="Latest question",
                    created_at=latest_activity,
                ),
                Message(
                    conversation_id=active_conversation.id,
                    role=MessageRole.assistant,
                    content="Answer",
                    created_at=now,
                ),
                Message(
                    conversation_id=active_conversation.id,
                    role=MessageRole.user,
                    content="Archived message",
                    archived=True,
                    created_at=now,
                ),
                Message(
                    conversation_id=archived_conversation.id,
                    role=MessageRole.user,
                    content="Archived conversation question",
                    created_at=now,
                ),
            ]
        )
        await db.commit()

    response = await async_client.get("/api/v1/users/admin/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"] == {
        "registered_users": 3,
        "new_users_last_7_days": 2,
    }
    assert [item["username"] for item in payload["users"]] == [
        "alice",
        "bob",
        "carol",
    ]
    assert payload["users"][0]["role"] == "admin"
    assert payload["users"][0]["conversation_count"] == 1
    assert payload["users"][0]["user_message_count"] == 2
    assert (
        datetime.fromisoformat(payload["users"][0]["last_activity_at"])
        == latest_activity
    )
    assert payload["users"][1]["last_activity_at"] is None


@pytest.mark.anyio
async def test_admin_users_bootstrap_rejects_regular_users(
    async_client: AsyncClient,
) -> None:
    async def regular_user() -> SecurityUser:
        return SecurityUser(id=2, username="viewer", role=UserRole.user)

    app.dependency_overrides[get_current_user] = regular_user
    try:
        response = await async_client.get("/api/v1/users/admin/bootstrap")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
