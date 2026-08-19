from __future__ import annotations

import pytest
from haystack.dataclasses import ChatMessage
from sqlalchemy import select

from app.api.models.chat import Conversation, ConversationSummary, Message
from app.services import conversation_context


@pytest.mark.anyio
async def test_compact_conversation_context_creates_summary_and_archives_messages(
    test_db_session_factory,
) -> None:
    async def generate(_messages: list[ChatMessage]) -> dict[str, object]:
        return {"replies": [ChatMessage.from_assistant("compact summary")]}

    async with test_db_session_factory() as db:
        conversation = Conversation(title="Compaction", user_id=1)
        db.add(conversation)
        await db.flush()

        for i in range(12):
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"message-{i}",
                )
            )
        await db.commit()

        compacted = await conversation_context.compact_conversation_context(
            conversation_id=conversation.id,
            generate=generate,
            keep_recent=4,
            session_factory=test_db_session_factory,
        )
        assert compacted is True

        summaries = (
            (
                await db.execute(
                    select(ConversationSummary).where(
                        ConversationSummary.conversation_id == conversation.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(summaries) == 1
        assert summaries[0].content == "compact summary"

        archived_count = (
            (
                await db.execute(
                    select(Message).where(
                        Message.conversation_id == conversation.id,
                        Message.archived.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(archived_count) >= 1
