from __future__ import annotations

from app.api.models.chat import Conversation, Message


async def create_conversation(
    *, db, title: str = "Test Conversation", user_id: int = 1
) -> Conversation:
    conversation = Conversation(title=title, user_id=user_id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def create_message(
    *, db, conversation_id: str, role: str, content: str
) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
