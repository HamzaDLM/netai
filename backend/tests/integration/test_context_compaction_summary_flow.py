from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.models.chat import Conversation, ConversationSummary, Message
from app.workflows import context_manager


@pytest.mark.anyio
async def test_compact_conversation_context_creates_summary_and_archives_messages(
    test_db_session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr(context_manager, "SessionLocal", test_db_session_factory)
    monkeypatch.setattr(
        context_manager.llm,
        "run",
        lambda **kwargs: {"replies": [SimpleNamespace(text="compact summary")]},
    )

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

        compacted = await context_manager.compact_conversation_context(
            conversation_id=conversation.id,
            keep_recent=4,
        )
        assert compacted is True

        summaries = (
            (
                await db.execute(
                    context_manager.select(ConversationSummary).where(
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
                    context_manager.select(Message).where(
                        Message.conversation_id == conversation.id,
                        Message.archived.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(archived_count) >= 1
