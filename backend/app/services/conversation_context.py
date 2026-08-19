"""Conversation history loading and asynchronous context compaction."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from haystack.dataclasses import ChatMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.chat import ConversationSummary, Message, MessageRole
from app.db.session import SessionLocal
from app.prompts import SUMMARIZING_PROMPT

RECENT_MESSAGE_WINDOW = 10
COMPACTION_THRESHOLD_RATIO = 0.8

GenerateChat = Callable[[list[ChatMessage]], Awaitable[dict[str, object]]]


@dataclass(slots=True)
class BuiltContext:
    messages: list[ChatMessage]
    message_sources: list[dict[str, int | str | None]]
    estimated_tokens: int
    used_summary_id: int | None
    compacted: bool
    context_window: int
    used_percent: int
    left_tokens: int
    left_percent: int


def estimate_tokens(messages: list[ChatMessage]) -> int:
    """Estimate prompt usage for preflight compaction, not billing."""

    text = "\n".join(message.text or "" for message in messages)
    return max(1, len(text) // 4)


def _to_chat_message(message: Message) -> ChatMessage:
    role = (
        message.role.value
        if isinstance(message.role, MessageRole)
        else str(message.role)
    )
    if role == MessageRole.assistant.value:
        return ChatMessage.from_assistant(message.content)
    if role == MessageRole.system.value:
        return ChatMessage.from_system(message.content)
    return ChatMessage.from_user(message.content)


def format_messages_for_summary(messages: list[Message]) -> str:
    return "\n".join(
        f"[{message.id}] {message.role.value}: {message.content}"
        for message in messages
        if message.role != MessageRole.system
    ).strip()


async def _history(
    *,
    conversation_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[ConversationSummary | None, list[Message]]:
    async with session_factory() as db:
        summary_stmt = (
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(ConversationSummary.id.desc())
            .limit(1)
        )
        latest_summary = (await db.execute(summary_stmt)).scalar_one_or_none()
        messages_stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.archived.is_(False),
                Message.role != MessageRole.system,
            )
            .order_by(Message.id.asc())
        )
        if latest_summary is not None:
            messages_stmt = messages_stmt.where(
                Message.id > latest_summary.up_to_message_id
            )
        messages = list((await db.execute(messages_stmt)).scalars().all())
        return latest_summary, messages


def _summary_text(result: dict[str, object]) -> str:
    replies = result.get("replies")
    if not isinstance(replies, list) or not replies:
        return ""
    reply = replies[0]
    return (reply.text or "").strip() if isinstance(reply, ChatMessage) else ""


async def compact_conversation_context(
    *,
    conversation_id: str,
    generate: GenerateChat,
    keep_recent: int = RECENT_MESSAGE_WINDOW,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> bool:
    latest_summary, _ = await _history(
        conversation_id=conversation_id,
        session_factory=session_factory,
    )

    async with session_factory() as db:
        all_messages_stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.archived.is_(False),
                Message.role != MessageRole.system,
            )
            .order_by(Message.id.asc())
        )
        all_messages = list((await db.execute(all_messages_stmt)).scalars().all())

    if len(all_messages) <= keep_recent:
        return False
    cutoff_message_id = all_messages[-keep_recent - 1].id
    previous_cutoff = latest_summary.up_to_message_id if latest_summary else 0
    to_summarize = [
        message
        for message in all_messages
        if previous_cutoff < message.id <= cutoff_message_id
    ]
    messages_text = format_messages_for_summary(to_summarize)
    if not messages_text:
        return False

    if latest_summary is not None:
        user_prompt = (
            f"Previous summary:\n{latest_summary.content}\n\n"
            f"New messages:\n{messages_text}\n\n"
            "Update the summary to reflect the full conversation so far."
        )
    else:
        user_prompt = f"Summarize the following conversation:\n{messages_text}"

    result = await generate(
        [
            ChatMessage.from_system(SUMMARIZING_PROMPT),
            ChatMessage.from_user(user_prompt),
        ]
    )
    summary_content = _summary_text(result)
    if not summary_content:
        return False

    async with session_factory() as db:
        db.add(
            ConversationSummary(
                conversation_id=conversation_id,
                content=summary_content,
                up_to_message_id=cutoff_message_id,
            )
        )
        await db.execute(
            update(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.id <= cutoff_message_id,
            )
            .values(archived=True)
        )
        await db.commit()
    return True


def _materialize(
    latest_summary: ConversationSummary | None,
    recent_messages: list[Message],
    *,
    keep_recent: int,
) -> tuple[list[ChatMessage], list[dict[str, int | str | None]]]:
    messages: list[ChatMessage] = []
    sources: list[dict[str, int | str | None]] = []
    if latest_summary is not None:
        messages.append(
            ChatMessage.from_system(
                "Conversation summary (do not repeat verbatim; use as prior context):\n"
                f"{latest_summary.content}"
            )
        )
        sources.append(
            {
                "source": "conversation_summary",
                "summary_id": latest_summary.id,
                "up_to_message_id": latest_summary.up_to_message_id,
            }
        )

    tail = recent_messages[-keep_recent:] if keep_recent > 0 else recent_messages
    messages.extend(_to_chat_message(message) for message in tail)
    sources.extend(
        {
            "source": "conversation_message",
            "message_id": message.id,
            "role": message.role.value
            if isinstance(message.role, MessageRole)
            else str(message.role),
        }
        for message in tail
    )
    return messages, sources


async def build_conversation_context(
    *,
    conversation_id: str,
    generate: GenerateChat,
    context_window: int,
    keep_recent: int = RECENT_MESSAGE_WINDOW,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> BuiltContext:
    latest_summary, recent_messages = await _history(
        conversation_id=conversation_id,
        session_factory=session_factory,
    )
    messages, sources = _materialize(
        latest_summary, recent_messages, keep_recent=keep_recent
    )
    estimated_tokens = estimate_tokens(messages)
    compacted = False

    if estimated_tokens > int(context_window * COMPACTION_THRESHOLD_RATIO):
        compacted = await compact_conversation_context(
            conversation_id=conversation_id,
            generate=generate,
            keep_recent=keep_recent,
            session_factory=session_factory,
        )
        if compacted:
            latest_summary, recent_messages = await _history(
                conversation_id=conversation_id,
                session_factory=session_factory,
            )
            messages, sources = _materialize(
                latest_summary, recent_messages, keep_recent=keep_recent
            )
            estimated_tokens = estimate_tokens(messages)

    used_percent = (
        int(round((estimated_tokens / context_window) * 100))
        if context_window > 0
        else 0
    )
    used_percent = max(0, min(100, used_percent))
    return BuiltContext(
        messages=messages,
        message_sources=sources,
        estimated_tokens=estimated_tokens,
        used_summary_id=latest_summary.id if latest_summary else None,
        compacted=compacted,
        context_window=context_window,
        used_percent=used_percent,
        left_tokens=max(context_window - estimated_tokens, 0),
        left_percent=max(0, min(100, 100 - used_percent)),
    )
