from __future__ import annotations

import pytest
from haystack.dataclasses import ChatMessage
from sqlalchemy import func, select

from app.api.models.chat import Conversation, ConversationSummary, Message, MessageRole
from app.services.conversation_context import build_conversation_context


async def _conversation_with_messages(session_factory, *, count: int) -> str:
    async with session_factory() as db:
        conversation = Conversation(title="Context", user_id=0)
        db.add(conversation)
        await db.flush()
        db.add_all(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.user if index % 2 == 0 else MessageRole.assistant,
                content=f"message {index}",
            )
            for index in range(count)
        )
        await db.commit()
        return conversation.id


@pytest.mark.anyio
async def test_context_compacts_everything_before_configured_recent_window(
    test_db_session_factory,
) -> None:
    conversation_id = await _conversation_with_messages(
        test_db_session_factory, count=6
    )

    async def summarize(_messages: list[ChatMessage]) -> dict[str, object]:
        return {"replies": [ChatMessage.from_assistant("messages zero through three")]}

    context = await build_conversation_context(
        conversation_id=conversation_id,
        generate=summarize,
        context_window=10_000,
        keep_recent=2,
        session_factory=test_db_session_factory,
    )

    assert context.compacted is True
    assert [message.text for message in context.messages] == [
        "Conversation summary (do not repeat verbatim; use as prior context):\n"
        "messages zero through three",
        "message 4",
        "message 5",
    ]
    async with test_db_session_factory() as db:
        active_count = await db.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation_id,
                Message.archived.is_(False),
            )
        )
        summary = (
            await db.execute(
                select(ConversationSummary).where(
                    ConversationSummary.conversation_id == conversation_id
                )
            )
        ).scalar_one()
    assert active_count == 2
    assert summary.content == "messages zero through three"


@pytest.mark.anyio
async def test_context_keeps_unsummarized_messages_when_summarization_fails(
    test_db_session_factory,
) -> None:
    conversation_id = await _conversation_with_messages(
        test_db_session_factory, count=5
    )

    async def empty_summary(_messages: list[ChatMessage]) -> dict[str, object]:
        return {"replies": []}

    context = await build_conversation_context(
        conversation_id=conversation_id,
        generate=empty_summary,
        context_window=10_000,
        keep_recent=2,
        session_factory=test_db_session_factory,
    )

    assert context.compacted is False
    assert [message.text for message in context.messages] == [
        "message 0",
        "message 1",
        "message 2",
        "message 3",
        "message 4",
    ]


@pytest.mark.anyio
async def test_context_ignores_empty_in_progress_assistant_placeholder(
    test_db_session_factory,
) -> None:
    async with test_db_session_factory() as db:
        conversation = Conversation(title="Running", user_id=0)
        db.add(conversation)
        await db.flush()
        db.add_all(
            (
                Message(
                    conversation_id=conversation.id,
                    role=MessageRole.user,
                    content="what hosts report problems in Zabbix?",
                ),
                Message(
                    conversation_id=conversation.id,
                    role=MessageRole.assistant,
                    content="",
                ),
            )
        )
        await db.commit()
        conversation_id = conversation.id

    async def unused_summary(_messages: list[ChatMessage]) -> dict[str, object]:
        raise AssertionError("a two-row running exchange must not be compacted")

    context = await build_conversation_context(
        conversation_id=conversation_id,
        generate=unused_summary,
        context_window=10_000,
        keep_recent=10,
        session_factory=test_db_session_factory,
    )

    assert [message.text for message in context.messages] == [
        "what hosts report problems in Zabbix?"
    ]
    assert len(context.message_sources) == 1
    assert context.message_sources[0]["source"] == "conversation_message"
    assert context.message_sources[0]["role"] == "user"
