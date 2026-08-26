from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.chat import (
    AgentRun,
    AgentRunStatus,
    AgentType,
    Conversation,
    Feedback,
    FeedbackRating,
    Message,
    MessageRole,
    ToolCall,
    ToolCallStatus,
)
from app.api.models.users import UserRole
from app.core.security import User as SecurityUser
from app.core.security import get_current_user
from app.main import app


@pytest.mark.anyio
async def test_admin_overview_reports_recent_active_usage(
    async_client: AsyncClient,
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=8)

    async with test_db_session_factory() as db:
        active_conversation = Conversation(title="Active", user_id=1, created_at=now)
        old_conversation = Conversation(title="Old", user_id=1, created_at=old)
        archived_conversation = Conversation(
            title="Archived", user_id=1, archived=True, created_at=now
        )
        db.add_all([active_conversation, old_conversation, archived_conversation])
        await db.flush()

        user_message = Message(
            conversation_id=active_conversation.id,
            role=MessageRole.user,
            content="Investigate edge-1",
            created_at=now,
        )
        assistant_message = Message(
            conversation_id=active_conversation.id,
            role=MessageRole.assistant,
            content="Investigation complete",
            created_at=now,
        )
        db.add_all(
            [
                user_message,
                assistant_message,
                Message(
                    conversation_id=active_conversation.id,
                    role=MessageRole.user,
                    content="Old question",
                    created_at=old,
                ),
                Message(
                    conversation_id=active_conversation.id,
                    role=MessageRole.user,
                    content="Archived question",
                    archived=True,
                    created_at=now,
                ),
                Message(
                    conversation_id=archived_conversation.id,
                    role=MessageRole.user,
                    content="Question in archived conversation",
                    created_at=now,
                ),
            ]
        )
        await db.flush()

        root_run_one = AgentRun(
            conversation_id=active_conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            agent_type=AgentType.orchestrator,
            agent_name="NetAI",
            depth=0,
            status=AgentRunStatus.completed,
            duration_ms=2000,
            created_at=now,
        )
        root_run_two = AgentRun(
            conversation_id=active_conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            agent_type=AgentType.orchestrator,
            agent_name="NetAI",
            depth=0,
            status=AgentRunStatus.completed,
            duration_ms=4000,
            created_at=now,
        )
        specialist_run = AgentRun(
            conversation_id=active_conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            agent_type=AgentType.specialist,
            agent_name="Zabbix",
            depth=1,
            status=AgentRunStatus.completed,
            duration_ms=10000,
            created_at=now,
        )
        db.add_all([root_run_one, root_run_two, specialist_run])
        await db.flush()

        for name, status in (
            ("healthy", ToolCallStatus.success),
            ("failed", ToolCallStatus.error),
            ("timed_out", ToolCallStatus.timeout),
        ):
            db.add(
                ToolCall(
                    run_id=specialist_run.id,
                    conversation_id=active_conversation.id,
                    tool_name=name,
                    input_params={},
                    status=status,
                    created_at=now,
                )
            )

        db.add_all(
            [
                Feedback(
                    message_id=assistant_message.id,
                    user_id=1,
                    rating=FeedbackRating.good,
                    created_at=now,
                ),
                Feedback(
                    message_id=assistant_message.id,
                    user_id=1,
                    rating=FeedbackRating.bad,
                    created_at=now,
                ),
            ]
        )
        await db.commit()

    response = await async_client.get("/api/v1/llm/admin/overview")

    assert response.status_code == 200
    overview = response.json()
    assert overview["conversations"] == 1
    assert overview["user_messages"] == 1
    assert overview["tool_calls_total"] == 3
    assert overview["tool_calls_failed"] == 2
    assert overview["average_latency_ms"] == pytest.approx(3000)
    assert overview["feedback_total"] == 2
    assert overview["negative_feedback"] == 1


@pytest.mark.anyio
async def test_admin_overview_rejects_regular_users(
    async_client: AsyncClient,
) -> None:
    async def regular_user() -> SecurityUser:
        return SecurityUser(id=2, username="viewer", role=UserRole.user)

    app.dependency_overrides[get_current_user] = regular_user
    try:
        response = await async_client.get("/api/v1/llm/admin/overview")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
